import asyncio
import base64
import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

import jwt
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, Request, Response, status
from jwt import PyJWKClient
from jwt.exceptions import PyJWTError
from tortoise import connections

from gitlab_radar.config import settings
from gitlab_radar.database.models import AuthorizedUser, WebSession, WebSocketTicket

SESSION_COOKIE = 'radar_session'
CSRF_COOKIE = 'radar_csrf'
OAUTH_STATE_COOKIE = 'radar_oauth_state'
OAUTH_VERIFIER_COOKIE = 'radar_oauth_verifier'
OAUTH_RETURN_COOKIE = 'radar_oauth_return'
WEBSOCKET_TICKET_TTL = timedelta(seconds=30)

_OIDC_METADATA: dict[str, Any] | None = None
_OIDC_METADATA_LOCK = asyncio.Lock()
_JWK_CLIENTS: dict[str, PyJWKClient] = {}


async def oidc_metadata() -> dict[str, Any]:
    global _OIDC_METADATA  # noqa: PLW0603
    if _OIDC_METADATA is not None:
        return _OIDC_METADATA
    async with _OIDC_METADATA_LOCK:
        if _OIDC_METADATA is None:
            url = f'{settings.auth.internal_issuer}/.well-known/openid-configuration'
            _OIDC_METADATA = await asyncio.to_thread(_request_json, url)
    return _OIDC_METADATA


async def exchange_authorization_code(code: str, redirect_uri: str, verifier: str) -> dict[str, Any]:
    metadata = await oidc_metadata()
    return await _post_token_request(
        _internal_endpoint(metadata['token_endpoint']),
        {
            'grant_type': 'authorization_code',
            'client_id': settings.auth.client_id,
            'client_secret': settings.auth.client_secret.get_secret_value(),
            'redirect_uri': redirect_uri,
            'code': code,
            'code_verifier': verifier,
        },
    )


async def create_web_session(response: Response, tokens: dict[str, Any]) -> None:
    session_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    max_age = _session_max_age(tokens)
    await WebSession.filter(expires_at__lte=datetime.now(UTC)).delete()
    await WebSession.create(
        token_hash=_hash(session_token),
        encrypted_tokens=_encrypt_tokens(tokens),
        csrf_hash=_hash(csrf_token),
        expires_at=datetime.now(UTC) + timedelta(seconds=max_age),
    )
    secure = settings.application.public_url.scheme == 'https'
    response.set_cookie(
        SESSION_COOKIE,
        session_token,
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite='lax',
        path='/',
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        max_age=max_age,
        secure=secure,
        samesite='lax',
        path='/',
    )


async def clear_web_session(request: Request, response: Response) -> dict[str, Any]:
    session_token = request.cookies.get(SESSION_COOKIE)
    tokens: dict[str, Any] = {}
    if session_token:
        session = await WebSession.filter(token_hash=_hash(session_token)).first()
        if session is not None:
            try:
                tokens = _decrypt_tokens(session.encrypted_tokens)
            except (InvalidToken, json.JSONDecodeError):
                tokens = {}
            await session.delete()
    response.delete_cookie(SESSION_COOKIE, path='/', httponly=True, samesite='lax')
    response.delete_cookie(CSRF_COOKIE, path='/', samesite='lax')
    return tokens


async def verify_access_token(token: str) -> dict[str, Any]:
    try:
        metadata = await oidc_metadata()
        jwks_url = _internal_endpoint(metadata['jwks_uri'])
        jwk_client = _JWK_CLIENTS.setdefault(jwks_url, PyJWKClient(jwks_url, cache_keys=True, lifespan=300))
        signing_key = await asyncio.to_thread(jwk_client.get_signing_key_from_jwt, token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=['RS256'],
            issuer=settings.auth.normalized_issuer,
            options={'require': ['exp', 'iat', 'iss'], 'verify_aud': False},
        )
        _validate_authorized_party(payload)
    except (KeyError, PyJWTError) as error:
        raise _unauthorized() from error
    return payload


async def require_authenticated_access(request: Request, response: Response) -> dict[str, Any]:
    session, tokens = await _web_session(request)
    if session is None:
        raise _unauthorized()
    _verify_csrf(request, session)
    access_token = await _access_token(session, tokens)
    payload = await verify_access_token(access_token)
    preferred_username = payload.get('preferred_username')
    if not isinstance(preferred_username, str) or not preferred_username:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='В токене отсутствует preferred_username')
    user, _ = await AuthorizedUser.get_or_create(
        preferred_username=preferred_username,
        defaults={'is_admin': preferred_username in settings.auth.allowed_preferred_usernames},
    )
    if user.is_blocked:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Пользователь заблокирован')
    return {**payload, 'is_admin': user.is_admin or preferred_username in settings.auth.allowed_preferred_usernames}


async def require_management_access(request: Request, response: Response) -> dict[str, Any]:
    payload = await require_authenticated_access(request, response)
    if not payload['is_admin']:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Требуются права администратора')
    return payload


async def authenticated_access_dependency(request: Request, response: Response) -> dict[str, Any]:
    claims = await require_authenticated_access(request, response)
    claims['visibility_group'] = request.headers.get('X-Radar-Visibility-Group')
    return claims


async def optional_authenticated_access_dependency(request: Request, response: Response) -> dict[str, Any]:
    if not request.cookies.get(SESSION_COOKIE):
        return {}
    try:
        return await authenticated_access_dependency(request, response)
    except HTTPException:
        return {}


async def management_access_dependency(request: Request, response: Response) -> dict[str, Any]:
    return await require_management_access(request, response)


async def issue_websocket_ticket() -> str:
    now = datetime.now(UTC)
    await WebSocketTicket.filter(expires_at__lte=now).delete()
    ticket = secrets.token_urlsafe(32)
    await WebSocketTicket.create(token_hash=_hash(ticket), expires_at=now + WEBSOCKET_TICKET_TTL)
    return ticket


async def consume_websocket_ticket(ticket: str) -> bool:
    rows = await connections.get('default').execute_query_dict(
        'DELETE FROM "websocketticket" WHERE "token_hash" = $1 AND "expires_at" > NOW() RETURNING "token_hash"',
        [_hash(ticket)],
    )
    return bool(rows)


async def _web_session(request: Request) -> tuple[WebSession | None, dict[str, Any]]:
    session_token = request.cookies.get(SESSION_COOKIE)
    if not session_token:
        return None, {}
    session = await WebSession.filter(
        token_hash=_hash(session_token),
        expires_at__gt=datetime.now(UTC),
    ).first()
    if session is None:
        return None, {}
    try:
        return session, _decrypt_tokens(session.encrypted_tokens)
    except (InvalidToken, json.JSONDecodeError):
        await session.delete()
        return None, {}


async def _access_token(session: WebSession, tokens: dict[str, Any]) -> str:
    access_token = tokens.get('access_token')
    if isinstance(access_token, str) and not _token_expires_soon(access_token):
        return access_token
    refresh_token = tokens.get('refresh_token')
    if not isinstance(refresh_token, str):
        raise _unauthorized()
    metadata = await oidc_metadata()
    refreshed = await _post_token_request(
        _internal_endpoint(metadata['token_endpoint']),
        {
            'grant_type': 'refresh_token',
            'client_id': settings.auth.client_id,
            'client_secret': settings.auth.client_secret.get_secret_value(),
            'refresh_token': refresh_token,
        },
    )
    tokens.update(refreshed)
    session.encrypted_tokens = _encrypt_tokens(tokens)
    await session.save(update_fields=['encrypted_tokens'])
    return tokens['access_token']


async def _post_token_request(url: str, values: dict[str, str]) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(_request_json, url, values)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail='Keycloak отклонил авторизацию') from error


def _request_json(url: str, values: dict[str, str] | None = None) -> dict[str, Any]:
    data = urlencode(values).encode() if values is not None else None
    request = UrlRequest(url, data=data, headers={'Accept': 'application/json'})
    if data is not None:
        request.add_header('Content-Type', 'application/x-www-form-urlencoded')
    with urlopen(request, timeout=10) as response:  # noqa: S310
        return json.load(response)


def _verify_csrf(request: Request, session: WebSession) -> None:
    if request.method not in {'POST', 'PUT', 'PATCH', 'DELETE'}:
        return
    token = request.headers.get('X-CSRF-Token')
    if not token or not secrets.compare_digest(_hash(token), session.csrf_hash):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Не удалось проверить CSRF-токен')


def _session_max_age(tokens: dict[str, Any]) -> int:
    value = tokens.get('refresh_expires_in', tokens.get('expires_in', 300))
    return max(int(value), 1)


def _encrypt_tokens(tokens: dict[str, Any]) -> str:
    return _fernet().encrypt(json.dumps(tokens, separators=(',', ':')).encode()).decode()


def _decrypt_tokens(value: str) -> dict[str, Any]:
    return json.loads(_fernet().decrypt(value.encode()))


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.auth.session_secret.get_secret_value().encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def public_oidc_endpoint(value: str) -> str:
    if value.startswith(settings.auth.internal_issuer):
        return settings.auth.normalized_issuer + value.removeprefix(settings.auth.internal_issuer)
    return value


def _internal_endpoint(value: str) -> str:
    if value.startswith(settings.auth.normalized_issuer):
        return settings.auth.internal_issuer + value.removeprefix(settings.auth.normalized_issuer)
    return value


def _token_expires_soon(token: str) -> bool:
    try:
        payload = jwt.decode(token, options={'verify_signature': False})
        return int(payload['exp']) <= int(datetime.now(UTC).timestamp()) + 30
    except (KeyError, TypeError, ValueError, PyJWTError):
        return True


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _validate_authorized_party(payload: dict[str, Any]) -> None:
    if payload.get('azp') != settings.auth.client_id:
        raise PyJWTError


def _unauthorized() -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Требуется авторизация')

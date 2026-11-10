import asyncio
import base64
import hashlib
import json
import secrets
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import jwt
from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from jwt.exceptions import PyJWTError
from tortoise import connections

from gitlab_radar.config import settings
from gitlab_radar.config.auth import KeycloakNotConfiguredError
from gitlab_radar.database.models import AuthorizedUser, WebSocketTicket, WebSession

bearer_scheme = HTTPBearer(auto_error=False)
_JWK_CLIENT = PyJWKClient(settings.auth.jwks_url, cache_keys=True, lifespan=300) if settings.auth.required else None
WEBSOCKET_TICKET_TTL = timedelta(seconds=30)
SESSION_TTL = timedelta(days=30)
SESSION_COOKIE = 'radar_session'
CSRF_COOKIE = 'radar_csrf'
OAUTH_STATE_COOKIE = 'radar_oauth_state'
OAUTH_VERIFIER_COOKIE = 'radar_oauth_verifier'


def _fernet() -> Fernet:
    secret = (settings.auth.session_secret or '').encode()
    key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
    return Fernet(key)


def _encrypt_tokens(tokens: dict[str, Any]) -> str:
    return _fernet().encrypt(json.dumps(tokens).encode()).decode()


def _decrypt_tokens(value: str) -> dict[str, Any]:
    try:
        return json.loads(_fernet().decrypt(value.encode()))
    except (InvalidToken, ValueError, TypeError) as error:
        raise HTTPException(status_code=401, detail='Сессия недействительна') from error


def _post_token_request(data: dict[str, str]) -> dict[str, Any]:
    body = urllib.parse.urlencode(data).encode()
    request = urllib.request.Request(
        settings.auth.token_url,
        data=body,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read())
    except Exception as error:
        raise HTTPException(status_code=401, detail='Keycloak отклонил авторизацию или обновление сессии') from error


async def exchange_authorization_code(code: str, verifier: str) -> dict[str, Any]:
    data = {
        'grant_type': 'authorization_code',
        'client_id': settings.auth.client_id or '',
        'client_secret': settings.auth.client_secret or '',
        'redirect_uri': f'{str(settings.application.public_url).rstrip("/")}/api/auth/callback',
        'code': code,
        'code_verifier': verifier,
    }
    return await asyncio.to_thread(_post_token_request, data)


async def refresh_session_tokens(tokens: dict[str, Any]) -> dict[str, Any]:
    data = {
        'grant_type': 'refresh_token',
        'client_id': settings.auth.client_id or '',
        'client_secret': settings.auth.client_secret or '',
        'refresh_token': tokens['refresh_token'],
    }
    refreshed = await asyncio.to_thread(_post_token_request, data)
    return {**tokens, **refreshed}


async def create_web_session(tokens: dict[str, Any]) -> tuple[str, str]:
    await WebSession.filter(expires_at__lte=datetime.now(UTC)).delete()
    claims = await verify_access_token(tokens['access_token'])
    username = claims.get('preferred_username')
    if not isinstance(username, str) or not username:
        raise HTTPException(status_code=403, detail='В токене отсутствует preferred_username')
    user, _ = await AuthorizedUser.get_or_create(
        preferred_username=username,
        defaults={'is_admin': username in settings.auth.allowed_preferred_usernames},
    )
    if user.is_blocked:
        raise HTTPException(status_code=403, detail='Пользователь заблокирован')
    session_id = secrets.token_urlsafe(48)
    csrf_token = secrets.token_urlsafe(32)
    await WebSession.create(
        token_hash=hashlib.sha256(session_id.encode()).hexdigest(),
        encrypted_tokens=_encrypt_tokens(tokens),
        csrf_hash=hashlib.sha256(csrf_token.encode()).hexdigest(),
        expires_at=datetime.now(UTC) + SESSION_TTL,
    )
    return session_id, csrf_token


async def revoke_web_session(session_id: str | None) -> None:
    if session_id:
        await WebSession.filter(token_hash=hashlib.sha256(session_id.encode()).hexdigest()).delete()


async def verify_access_token(token: str) -> dict[str, Any]:
    try:
        signing_key = await asyncio.to_thread(_get_jwk_client().get_signing_key_from_jwt, token)
        payload = _decode_access_token(token, signing_key.key)
    except PyJWTError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Требуется авторизация',
            headers={'WWW-Authenticate': 'Bearer'},
        ) from error
    return payload


async def _session_claims(request: Request) -> dict[str, Any]:
    session_id = request.cookies.get(SESSION_COOKIE)
    if not session_id:
        raise HTTPException(status_code=401, detail='Требуется авторизация')
    session = await WebSession.get_or_none(
        token_hash=hashlib.sha256(session_id.encode()).hexdigest(),
        expires_at__gt=datetime.now(UTC),
    )
    if session is None:
        raise HTTPException(status_code=401, detail='Сессия истекла')
    tokens = _decrypt_tokens(session.encrypted_tokens)
    try:
        claims = await verify_access_token(tokens['access_token'])
    except HTTPException:
        if not tokens.get('refresh_token'):
            await session.delete()
            raise
        tokens = await refresh_session_tokens(tokens)
        claims = await verify_access_token(tokens['access_token'])
        session.encrypted_tokens = _encrypt_tokens(tokens)
        session.expires_at = datetime.now(UTC) + SESSION_TTL
        await session.save(update_fields=['encrypted_tokens', 'expires_at'])
    username = claims.get('preferred_username')
    if not isinstance(username, str) or not username:
        raise HTTPException(status_code=403, detail='В токене отсутствует preferred_username')
    user, _ = await AuthorizedUser.get_or_create(
        preferred_username=username,
        defaults={'is_admin': username in settings.auth.allowed_preferred_usernames},
    )
    if user.is_blocked:
        await session.delete()
        raise HTTPException(status_code=403, detail='Пользователь заблокирован')
    if request.method.upper() not in {'GET', 'HEAD', 'OPTIONS'}:
        csrf_cookie = request.cookies.get(CSRF_COOKIE, '')
        csrf_header = request.headers.get('X-CSRF-Token', '')
        if not csrf_cookie or not secrets.compare_digest(csrf_cookie, csrf_header):
            raise HTTPException(status_code=403, detail='Не пройдена CSRF-проверка')
        if not secrets.compare_digest(
            session.csrf_hash, hashlib.sha256(csrf_cookie.encode()).hexdigest()
        ):
            raise HTTPException(status_code=403, detail='Не пройдена CSRF-проверка')
    return {
        **claims,
        'is_admin': user.is_admin or username in settings.auth.allowed_preferred_usernames,
    }


async def require_authenticated_access(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = None,
    development_username: str | None = None,
) -> dict[str, Any]:
    if not settings.auth.required:
        preferred_username = (development_username or settings.auth.development_username).strip()
        if not preferred_username:
            preferred_username = settings.auth.development_username
        if len(preferred_username) > 255:
            raise HTTPException(status_code=400, detail='Слишком длинное имя пользователя')
        is_development_admin = preferred_username == settings.auth.development_username
        user, _ = await AuthorizedUser.get_or_create(
            preferred_username=preferred_username,
            defaults={'is_admin': is_development_admin},
        )
        if is_development_admin and user.is_blocked:
            user.is_blocked = False
            await user.save(update_fields=['is_blocked'])
        if user.is_blocked:
            raise HTTPException(status_code=403, detail='Пользователь заблокирован')
        return {
            'preferred_username': preferred_username,
            'is_admin': is_development_admin or user.is_admin,
            'development': True,
        }
    if credentials is not None:
        payload = await verify_access_token(credentials.credentials)
        username = payload.get('preferred_username')
        if not isinstance(username, str) or not username:
            raise HTTPException(status_code=403, detail='В токене отсутствует preferred_username')
        user, _ = await AuthorizedUser.get_or_create(
            preferred_username=username,
            defaults={'is_admin': username in settings.auth.allowed_preferred_usernames},
        )
        if user.is_blocked:
            raise HTTPException(status_code=403, detail='Пользователь заблокирован')
        return {**payload, 'is_admin': user.is_admin or username in settings.auth.allowed_preferred_usernames}
    return await _session_claims(request)


async def require_management_access(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = None,
    development_username: str | None = None,
) -> dict[str, Any]:
    payload = await require_authenticated_access(request, credentials, development_username)
    if not payload['is_admin']:
        raise HTTPException(status_code=403, detail='Требуются права администратора')
    return payload


async def authenticated_access_dependency(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    development_username: Annotated[str | None, Header(alias='X-Radar-Development-User')] = None,
    visibility_group: Annotated[str | None, Header(alias='X-Radar-Visibility-Group')] = None,
) -> dict[str, Any]:
    claims = await require_authenticated_access(request, credentials, development_username)
    claims['visibility_group'] = visibility_group
    return claims


async def management_access_dependency(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    development_username: Annotated[str | None, Header(alias='X-Radar-Development-User')] = None,
) -> dict[str, Any]:
    return await require_management_access(request, credentials, development_username)


async def issue_websocket_ticket() -> str:
    now = datetime.now(UTC)
    await WebSocketTicket.filter(expires_at__lte=now).delete()
    ticket = secrets.token_urlsafe(32)
    await WebSocketTicket.create(token_hash=_ticket_hash(ticket), expires_at=now + WEBSOCKET_TICKET_TTL)
    return ticket


async def consume_websocket_ticket(ticket: str) -> bool:
    rows = await connections.get('default').execute_query_dict(
        'DELETE FROM "websocketticket" WHERE "token_hash" = $1 AND "expires_at" > NOW() RETURNING "token_hash"',
        [_ticket_hash(ticket)],
    )
    return bool(rows)


def _ticket_hash(ticket: str) -> str:
    return hashlib.sha256(ticket.encode()).hexdigest()


def _get_jwk_client() -> PyJWKClient:
    if _JWK_CLIENT is None:
        raise KeycloakNotConfiguredError
    return _JWK_CLIENT


def _validate_authorized_party(payload: dict[str, Any]) -> None:
    if payload.get('azp') != settings.auth.client_id:
        raise PyJWTError


def _decode_access_token(token: str, key: object) -> dict[str, Any]:
    payload = jwt.decode(
        token,
        key,
        algorithms=['RS256'],
        issuer=settings.auth.issuer,
        options={'require': ['exp', 'iat', 'iss'], 'verify_aud': False},
    )
    _validate_authorized_party(payload)
    return payload

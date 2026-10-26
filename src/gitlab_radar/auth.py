import asyncio
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from jwt.exceptions import PyJWTError
from tortoise import connections

from gitlab_radar.config import settings
from gitlab_radar.config.auth import KeycloakNotConfiguredError
from gitlab_radar.database.models import AuthorizedUser, WebSocketTicket

bearer_scheme = HTTPBearer(auto_error=False)
_JWK_CLIENT = PyJWKClient(settings.auth.jwks_url, cache_keys=True, lifespan=300) if settings.auth.required else None
WEBSOCKET_TICKET_TTL = timedelta(seconds=30)


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


async def require_authenticated_access(
    credentials: HTTPAuthorizationCredentials | None = None,
) -> dict[str, Any]:
    if not settings.auth.required:
        return {'is_admin': True}
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Требуется авторизация',
            headers={'WWW-Authenticate': 'Bearer'},
        )
    payload = await verify_access_token(credentials.credentials)
    preferred_username = payload.get('preferred_username')
    if not isinstance(preferred_username, str) or not preferred_username:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='В токене отсутствует preferred_username')
    user, _ = await AuthorizedUser.get_or_create(
        preferred_username=preferred_username,
        defaults={'is_admin': preferred_username in settings.auth.allowed_preferred_usernames},
    )
    if user.is_blocked:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Пользователь заблокирован')
    return {
        **payload,
        'is_admin': user.is_admin or preferred_username in settings.auth.allowed_preferred_usernames,
    }


async def require_management_access(
    credentials: HTTPAuthorizationCredentials | None = None,
) -> dict[str, Any]:
    payload = await require_authenticated_access(credentials)
    if not payload['is_admin']:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Требуются права администратора')
    return payload


async def authenticated_access_dependency(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> dict[str, Any]:
    return await require_authenticated_access(credentials)


async def management_access_dependency(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> dict[str, Any]:
    return await require_management_access(credentials)


async def issue_websocket_ticket() -> str:
    now = datetime.now(UTC)
    await WebSocketTicket.filter(expires_at__lte=now).delete()
    ticket = secrets.token_urlsafe(32)
    await WebSocketTicket.create(
        token_hash=_ticket_hash(ticket),
        expires_at=now + WEBSOCKET_TICKET_TTL,
    )
    return ticket


async def consume_websocket_ticket(ticket: str) -> bool:
    rows = await connections.get('default').execute_query_dict(
        'DELETE FROM "websocketticket" '
        'WHERE "token_hash" = $1 AND "expires_at" > NOW() '
        'RETURNING "token_hash"',
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

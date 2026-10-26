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
from gitlab_radar.database.models import WebSocketTicket

bearer_scheme = HTTPBearer(auto_error=False)
_jwk_client = PyJWKClient(settings.auth.jwks_url, cache_keys=True, lifespan=300)
WEBSOCKET_TICKET_TTL = timedelta(seconds=30)


async def verify_access_token(token: str) -> dict[str, Any]:
    try:
        signing_key = await asyncio.to_thread(_jwk_client.get_signing_key_from_jwt, token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=['RS256'],
            audience=settings.auth.client_id,
            issuer=settings.auth.issuer,
            options={'require': ['exp', 'iat', 'iss']},
        )
    except PyJWTError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Требуется авторизация',
            headers={'WWW-Authenticate': 'Bearer'},
        ) from error


async def require_management_access(
    credentials: HTTPAuthorizationCredentials | None = None,
) -> dict[str, Any]:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Требуется авторизация',
            headers={'WWW-Authenticate': 'Bearer'},
        )
    return await verify_access_token(credentials.credentials)


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

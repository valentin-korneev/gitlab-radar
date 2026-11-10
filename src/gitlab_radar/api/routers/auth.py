import base64
import hashlib
import re
import secrets
from typing import Annotated, Any
from urllib.parse import urlencode

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse

from gitlab_radar.auth import (
    OAUTH_RETURN_COOKIE,
    OAUTH_STATE_COOKIE,
    OAUTH_VERIFIER_COOKIE,
    authenticated_access_dependency,
    clear_web_session,
    create_web_session,
    exchange_authorization_code,
    issue_websocket_ticket,
    oidc_metadata,
    public_oidc_endpoint,
)
from gitlab_radar.config import settings

router = APIRouter()
_ROUTE_PATTERN = re.compile(r'^[a-z-]+$')


@router.get('/config')
async def auth_config() -> dict[str, str]:
    return {'login_url': '/api/auth/login', 'logout_url': '/api/auth/logout'}


@router.get('/login')
async def login(return_to: str = Query(default='dashboard')) -> RedirectResponse:
    metadata = await oidc_metadata()
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    parameters = urlencode(
        {
            'client_id': settings.auth.client_id,
            'redirect_uri': _callback_url(),
            'response_type': 'code',
            'scope': 'openid profile email',
            'state': state,
            'code_challenge': challenge,
            'code_challenge_method': 'S256',
        },
    )
    authorization_endpoint = public_oidc_endpoint(metadata['authorization_endpoint'])
    response = RedirectResponse(f'{authorization_endpoint}?{parameters}')
    secure = settings.application.public_url.scheme == 'https'
    response.set_cookie(OAUTH_STATE_COOKIE, state, max_age=600, httponly=True, secure=secure, samesite='lax')
    response.set_cookie(OAUTH_VERIFIER_COOKIE, verifier, max_age=600, httponly=True, secure=secure, samesite='lax')
    response.set_cookie(
        OAUTH_RETURN_COOKIE,
        return_to if _ROUTE_PATTERN.fullmatch(return_to) else 'dashboard',
        max_age=600,
        httponly=True,
        secure=secure,
        samesite='lax',
    )
    return response


@router.get('/callback')
async def callback(
    code: str,
    state: str,
    expected_state: Annotated[str | None, Cookie(alias=OAUTH_STATE_COOKIE)] = None,
    verifier: Annotated[str | None, Cookie(alias=OAUTH_VERIFIER_COOKIE)] = None,
    return_to: Annotated[str | None, Cookie(alias=OAUTH_RETURN_COOKIE)] = None,
) -> RedirectResponse:
    if not expected_state or not secrets.compare_digest(state, expected_state) or not verifier:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Не удалось проверить ответ авторизации')
    tokens = await exchange_authorization_code(code, _callback_url(), verifier)
    route = return_to if return_to and _ROUTE_PATTERN.fullmatch(return_to) else 'dashboard'
    response = RedirectResponse(f'{str(settings.application.public_url).rstrip("/")}/#{route}')
    await create_web_session(response, tokens)
    for name in (OAUTH_STATE_COOKIE, OAUTH_VERIFIER_COOKIE, OAUTH_RETURN_COOKIE):
        response.delete_cookie(name, path='/', httponly=True, samesite='lax')
    return response


@router.get('/logout')
async def logout(request: Request) -> RedirectResponse:
    target = str(settings.application.public_url).rstrip('/') + '/'
    parameters = {'client_id': settings.auth.client_id, 'post_logout_redirect_uri': target}
    response = RedirectResponse(target)
    tokens = await clear_web_session(request, response)
    if id_token := tokens.get('id_token'):
        parameters['id_token_hint'] = id_token
    try:
        metadata = await oidc_metadata()
    except (OSError, ValueError):
        return response
    endpoint = metadata.get('end_session_endpoint')
    if endpoint:
        endpoint = public_oidc_endpoint(endpoint)
    response.headers['location'] = f'{endpoint}?{urlencode(parameters)}' if endpoint else target
    return response


@router.get('/session')
async def auth_session(
    claims: Annotated[dict[str, Any], Depends(authenticated_access_dependency)],
) -> dict[str, Any]:
    return claims


@router.post('/websocket-ticket', dependencies=[Depends(authenticated_access_dependency)])
async def websocket_ticket() -> dict[str, str]:
    return {'ticket': await issue_websocket_ticket()}


def _callback_url() -> str:
    return f'{str(settings.application.public_url).rstrip("/")}/api/auth/callback'

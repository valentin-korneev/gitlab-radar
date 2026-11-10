import base64
import hashlib
import secrets
from typing import Annotated, Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from gitlab_radar.auth import (
    CSRF_COOKIE,
    OAUTH_STATE_COOKIE,
    OAUTH_VERIFIER_COOKIE,
    SESSION_COOKIE,
    authenticated_access_dependency,
    create_web_session,
    exchange_authorization_code,
    issue_websocket_ticket,
    revoke_web_session,
)
from gitlab_radar.config import settings

router = APIRouter()


def _cookie_options() -> dict[str, Any]:
    return {
        'httponly': True,
        'secure': str(settings.application.public_url).startswith('https://'),
        'samesite': 'lax',
        'path': '/',
    }


@router.get('/config')
async def auth_config() -> dict[str, str | bool]:
    if not settings.auth.required:
        return {'required': False, 'development_username': settings.auth.development_username}
    return {'required': True}


@router.get('/login')
async def login() -> RedirectResponse:
    if not settings.auth.required:
        return RedirectResponse('/')
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    callback = f'{str(settings.application.public_url).rstrip("/")}/api/auth/callback'
    query = urlencode({
        'client_id': settings.auth.client_id,
        'redirect_uri': callback,
        'response_type': 'code',
        'scope': 'openid profile email',
        'state': state,
        'code_challenge': challenge,
        'code_challenge_method': 'S256',
    })
    response = RedirectResponse(f'{settings.auth.authorization_url}?{query}', status_code=302)
    response.set_cookie(OAUTH_STATE_COOKIE, state, max_age=300, **_cookie_options())
    response.set_cookie(OAUTH_VERIFIER_COOKIE, verifier, max_age=300, **_cookie_options())
    return response


@router.get('/callback')
async def callback(request: Request) -> RedirectResponse:
    if request.query_params.get('error'):
        raise HTTPException(status_code=401, detail='Авторизация в Keycloak отменена')
    state = request.query_params.get('state', '')
    expected_state = request.cookies.get(OAUTH_STATE_COOKIE, '')
    verifier = request.cookies.get(OAUTH_VERIFIER_COOKIE, '')
    code = request.query_params.get('code', '')
    if not state or not expected_state or not secrets.compare_digest(state, expected_state) or not verifier or not code:
        raise HTTPException(status_code=400, detail='Не удалось проверить ответ авторизации')
    tokens = await exchange_authorization_code(code, verifier)
    session_id, csrf_token = await create_web_session(tokens)
    destination = f'{str(settings.application.public_url).rstrip("/")}/'
    response = RedirectResponse(destination, status_code=303)
    response.set_cookie(SESSION_COOKIE, session_id, max_age=30 * 24 * 3600, **_cookie_options())
    response.set_cookie(CSRF_COOKIE, csrf_token, max_age=30 * 24 * 3600, httponly=False,
                        secure=str(settings.application.public_url).startswith('https://'),
                        samesite='lax', path='/')
    response.delete_cookie(OAUTH_STATE_COOKIE, path='/')
    response.delete_cookie(OAUTH_VERIFIER_COOKIE, path='/')
    return response


@router.post('/logout')
async def logout(request: Request) -> Response:
    session_id = request.cookies.get(SESSION_COOKIE)
    csrf_cookie = request.cookies.get(CSRF_COOKIE, '')
    csrf_header = request.headers.get('X-CSRF-Token', '')
    if not csrf_cookie or not secrets.compare_digest(csrf_cookie, csrf_header):
        raise HTTPException(status_code=403, detail='Не пройдена CSRF-проверка')
    await revoke_web_session(session_id)
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE, path='/')
    response.delete_cookie(CSRF_COOKIE, path='/')
    return response


@router.get('/session')
async def auth_session(
    claims: Annotated[dict[str, Any], Depends(authenticated_access_dependency)],
) -> dict[str, Any]:
    return claims


@router.post('/websocket-ticket')
async def websocket_ticket(
    claims: Annotated[dict[str, Any], Depends(authenticated_access_dependency)],
) -> dict[str, str]:
    return {'ticket': await issue_websocket_ticket()}

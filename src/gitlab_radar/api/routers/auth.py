from typing import Annotated, Any

from fastapi import APIRouter, Depends

from gitlab_radar.auth import authenticated_access_dependency, issue_websocket_ticket
from gitlab_radar.config import settings

router = APIRouter()


@router.get('/config')
async def auth_config() -> dict[str, str | bool]:
    if not settings.auth.required:
        return {'required': False}
    return {
        'required': True,
        'issuer': settings.auth.issuer,
        'client_id': settings.auth.client_id or '',
        'redirect_uri': f'{str(settings.application.public_url).rstrip("/")}/',
    }


@router.get('/session')
async def auth_session(
    claims: Annotated[dict[str, Any], Depends(authenticated_access_dependency)],
) -> dict[str, Any]:
    return claims


@router.post('/websocket-ticket', dependencies=[Depends(authenticated_access_dependency)])
async def websocket_ticket() -> dict[str, str]:
    return {'ticket': await issue_websocket_ticket()}

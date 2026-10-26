from typing import Annotated, Any

from fastapi import APIRouter, Depends

from gitlab_radar.auth import issue_websocket_ticket, management_access_dependency
from gitlab_radar.config import settings

router = APIRouter()


@router.get('/config')
async def auth_config() -> dict[str, str]:
    return {
        'issuer': settings.auth.issuer,
        'client_id': settings.auth.client_id,
        'redirect_uri': f'{str(settings.application.public_url).rstrip("/")}/',
    }


@router.get('/session')
async def auth_session(
    claims: Annotated[dict[str, Any], Depends(management_access_dependency)],
) -> dict[str, Any]:
    return claims


@router.post('/websocket-ticket', dependencies=[Depends(management_access_dependency)])
async def websocket_ticket() -> dict[str, str]:
    return {'ticket': await issue_websocket_ticket()}

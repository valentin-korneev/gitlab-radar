from typing import Annotated, Any

from fastapi import APIRouter, Depends

from gitlab_radar.auth import authenticated_access_dependency
from gitlab_radar.schemas.dashboard import Dashboard
from gitlab_radar.services.dashboard import build_dashboard

router = APIRouter()


@router.get('/')
async def get_dashboard(
    claims: Annotated[dict[str, Any], Depends(authenticated_access_dependency)],
) -> Dashboard:
    return await build_dashboard(claims.get('preferred_username'), claims.get('visibility_group'))

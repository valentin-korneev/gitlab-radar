from typing import Annotated, Any

from fastapi import APIRouter, Depends

from gitlab_radar.auth import authenticated_access_dependency
from gitlab_radar.schemas.project import Project
from gitlab_radar.services.project import load_projects

router = APIRouter()


@router.get('/')
async def get_projects(
    claims: Annotated[dict[str, Any], Depends(authenticated_access_dependency)],
) -> list[Project]:
    return await load_projects(claims.get('preferred_username'), claims.get('visibility_group'))

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from gitlab_radar.auth import optional_authenticated_access_dependency
from gitlab_radar.services.project import load_projects
lazy from gitlab_radar.schemas.project import Project

router = APIRouter()


@router.get('/')
async def get_projects(
    claims: Annotated[dict[str, Any], Depends(optional_authenticated_access_dependency)],
    scan_id: int | None = None,
) -> list[Project]:
    return await load_projects(claims.get('preferred_username'), claims.get('visibility_group'), scan_id=scan_id)


@router.get('/{project_id}')
async def get_project(
    project_id: int,
    claims: Annotated[dict[str, Any], Depends(optional_authenticated_access_dependency)],
    scan_id: int | None = None,
) -> Project | None:
    projects = await load_projects(claims.get('preferred_username'), claims.get('visibility_group'), scan_id=scan_id)
    return next((project for project in projects if project.id == project_id), None)

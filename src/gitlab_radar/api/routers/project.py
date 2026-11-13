from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from gitlab_radar.auth import optional_authenticated_access_dependency
from gitlab_radar.domain.scanning import ScanResultsArchivedError
from gitlab_radar.services.project import load_projects
lazy from gitlab_radar.schemas.project import Project

router = APIRouter()


@router.get('/')
async def get_projects(
    claims: Annotated[dict[str, Any], Depends(optional_authenticated_access_dependency)],
    scan_id: int | None = None,
    project_ids: Annotated[list[int] | None, Query(max_length=100)] = None,
) -> list[Project]:
    return await _load_projects(
        claims.get('preferred_username'), claims.get('visibility_group'), scan_id=scan_id, project_ids=project_ids
    )


@router.get('/{project_id}')
async def get_project(
    project_id: int,
    claims: Annotated[dict[str, Any], Depends(optional_authenticated_access_dependency)],
    scan_id: int | None = None,
) -> Project | None:
    projects = await _load_projects(
        claims.get('preferred_username'), claims.get('visibility_group'), scan_id=scan_id, project_ids=[project_id]
    )
    return next((project for project in projects if project.id == project_id), None)


async def _load_projects(
    username: str | None,
    visibility_group: str | None,
    *,
    scan_id: int | None,
    project_ids: list[int] | None,
) -> list[Project]:
    try:
        return await load_projects(username, visibility_group, scan_id=scan_id, project_ids=project_ids)
    except ScanResultsArchivedError as error:
        raise HTTPException(status_code=410, detail=str(error)) from error

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from gitlab_radar.auth import authenticated_access_dependency
from gitlab_radar.schemas.dependency import DependencySource, DependencyUsage
from gitlab_radar.services.dependency import build_dependency_catalog

router = APIRouter()


@router.get('/')
async def get_dependencies(
    claims: Annotated[dict[str, Any], Depends(authenticated_access_dependency)],
    source: DependencySource = DependencySource.PYTHON,
) -> list[DependencyUsage]:
    return await build_dependency_catalog(
        source=source,
        preferred_username=claims.get('preferred_username'),
        visibility_group=claims.get('visibility_group'),
    )

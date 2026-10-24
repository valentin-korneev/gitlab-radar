from fastapi import APIRouter

from gitlab_radar.schemas.dependency import DependencyUsage
from gitlab_radar.services.dependency import build_dependency_catalog

router = APIRouter()


@router.get('/')
async def get_dependencies() -> list[DependencyUsage]:
    return await build_dependency_catalog()

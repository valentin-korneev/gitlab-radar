from fastapi import APIRouter

from gitlab_radar.schemas.project import Project
from gitlab_radar.services.project import load_projects

router = APIRouter()


@router.get('/')
async def get_projects() -> list[Project]:
    return await load_projects()

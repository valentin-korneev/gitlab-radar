from fastapi import APIRouter

from gitlab_radar.services.project import ProjectService

router = APIRouter()

@router.get('/')
async def get_projects() -> list:
    project_service = ProjectService()
    return project_service.get_projects()

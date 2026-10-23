from fastapi import APIRouter

from gitlab_radar.services.project import ProjectService
lazy from gitlab_radar.schemas.project import Project

router = APIRouter()


@router.get('/')
def get_projects() -> list[Project]:
    project_service = ProjectService()
    return project_service.get_projects()

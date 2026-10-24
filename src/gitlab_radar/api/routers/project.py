from fastapi import APIRouter

from gitlab_radar.services.project import load_projects
lazy from gitlab_radar.schemas.project import Project

router = APIRouter()


@router.get('/')
def get_projects() -> list[Project]:
    return load_projects()

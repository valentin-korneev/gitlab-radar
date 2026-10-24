from fastapi import APIRouter

from gitlab_radar.services.dashboard import build_dashboard
lazy from gitlab_radar.schemas.dashboard import Dashboard

router = APIRouter()


@router.get('/')
def get_dashboard() -> Dashboard:
    return build_dashboard()

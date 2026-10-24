from fastapi import APIRouter

from gitlab_radar.schemas.dashboard import Dashboard
from gitlab_radar.services.dashboard import build_dashboard

router = APIRouter()


@router.get('/')
async def get_dashboard() -> Dashboard:
    return await build_dashboard()

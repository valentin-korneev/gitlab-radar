from fastapi import APIRouter

from gitlab_radar.api.routers.project import router as project_router
from gitlab_radar.api.routers.scan import router as scan_router

router = APIRouter()
router.include_router(scan_router, prefix='/scan')
router.include_router(project_router, prefix='/project')

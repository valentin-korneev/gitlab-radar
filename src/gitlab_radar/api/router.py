from fastapi import APIRouter

from gitlab_radar.api.routers.application_parameter import router as application_parameter_router
from gitlab_radar.api.routers.auth import router as auth_router
from gitlab_radar.api.routers.authorized_user import router as authorized_user_router
from gitlab_radar.api.routers.company_requirement import router as company_requirement_router
from gitlab_radar.api.routers.company_requirement_group import router as company_requirement_group_router
from gitlab_radar.api.routers.dashboard import router as dashboard_router
from gitlab_radar.api.routers.dependency import router as dependency_router
from gitlab_radar.api.routers.project import router as project_router
from gitlab_radar.api.routers.scan import router as scan_router
from gitlab_radar.api.routers.visibility import admin_router as admin_visibility_router
from gitlab_radar.api.routers.visibility import router as visibility_router

router = APIRouter()
router.include_router(auth_router, prefix='/auth')
router.include_router(authorized_user_router, prefix='/authorized-user')
router.include_router(application_parameter_router, prefix='/application-parameter')
router.include_router(company_requirement_router, prefix='/company-requirement')
router.include_router(company_requirement_group_router, prefix='/company-requirement-group')
router.include_router(dashboard_router, prefix='/dashboard')
router.include_router(dependency_router, prefix='/dependency')
router.include_router(scan_router, prefix='/scan')
router.include_router(project_router, prefix='/project')
router.include_router(visibility_router, prefix='/visibility')
router.include_router(admin_visibility_router, prefix='/visibility/admin')

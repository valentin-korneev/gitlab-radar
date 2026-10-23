from fastapi import APIRouter
from fastapi.responses import FileResponse

from gitlab_radar.config import settings

router = APIRouter(include_in_schema=False)


@router.get('/', response_class=FileResponse)
def index() -> FileResponse:
    return FileResponse(settings.application.web_dir / 'index.html')

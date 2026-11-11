from uuid import uuid4

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from gitlab_radar.config import settings

router = APIRouter(include_in_schema=False)
STATIC_VERSION = uuid4().hex


@router.get('/', response_class=HTMLResponse)
def index() -> HTMLResponse:
    content = (settings.application.web_dir / 'index.html').read_text(encoding='utf-8').replace(
        '/static/',
        f'/static/{STATIC_VERSION}/',
    )
    return HTMLResponse(content, headers={'Cache-Control': 'no-store'})

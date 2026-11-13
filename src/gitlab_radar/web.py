import hashlib
import re

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from gitlab_radar.config import settings

router = APIRouter(include_in_schema=False)


def _static_version() -> str:
    digest = hashlib.sha256()
    directory = settings.application.web_dir / 'static'
    for path in sorted(directory.rglob('*')):
        if path.is_file():
            name = path.relative_to(directory).as_posix().encode()
            content = path.read_bytes()
            digest.update(len(name).to_bytes(8, 'big'))
            digest.update(name)
            digest.update(len(content).to_bytes(8, 'big'))
            digest.update(content)
    return digest.hexdigest()[:16]


STATIC_VERSION = _static_version()


@router.get('/', response_class=HTMLResponse)
def index() -> HTMLResponse:
    content = (settings.application.web_dir / 'index.html').read_text(encoding='utf-8')
    content = re.sub(
        r'(/static/[^\s"\'<>]+)',
        lambda match: f'{match[1]}?v={STATIC_VERSION}',
        content,
    )
    return HTMLResponse(content, headers={'Cache-Control': 'no-store'})

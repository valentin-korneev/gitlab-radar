import hashlib
import json
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
    module_root = settings.application.web_dir / 'static' / 'js'
    module_urls = (
        f'/static/js/{path.relative_to(module_root).as_posix()}' for path in sorted(module_root.rglob('*.js'))
    )
    modules = {url: f'{url}?v={STATIC_VERSION}' for url in module_urls}
    import_map = json.dumps({'imports': modules}, ensure_ascii=False).replace('<', r'\u003c')
    content = content.replace(
        '<script type="module"',
        f'<script type="importmap">{import_map}</script>\n  <script type="module"',
        1,
    )
    return HTMLResponse(content, headers={'Cache-Control': 'no-store'})

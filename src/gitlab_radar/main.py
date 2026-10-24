from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from gitlab_radar.api.router import router as api_router
from gitlab_radar.config import settings
from gitlab_radar.config.logging import configure_logging
from gitlab_radar.database import database_lifespan
from gitlab_radar.tasks.scan import scan_task
from gitlab_radar.web import router as web_router

configure_logging()


@asynccontextmanager
async def application_lifespan(application: FastAPI) -> AsyncIterator[None]:
    async with database_lifespan(application):
        try:
            yield
        finally:
            await scan_task.stop()


app = FastAPI(lifespan=application_lifespan)
app.include_router(api_router, prefix='/api')
app.include_router(web_router)
app.mount('/static', StaticFiles(directory=settings.application.web_dir / 'static'), name='static')


def start() -> None:
    uvicorn.run(
        'gitlab_radar.main:app',
        host=settings.application.host,
        port=settings.application.port,
        reload=settings.application.reload,
        workers=1,
    )

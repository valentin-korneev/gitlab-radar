import uvicorn
from fastapi import FastAPI

from gitlab_radar.api.router import router as api_router
from gitlab_radar.config import settings

app = FastAPI()
app.include_router(api_router, prefix='/api')


def start() -> None:
    uvicorn.run(
        'gitlab_radar.main:app',
        host=settings.application.host,
        port=settings.application.port,
        reload=settings.application.reload,
    )

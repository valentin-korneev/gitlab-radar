from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from tortoise.contrib.fastapi import RegisterTortoise
from fastapi import FastAPI

from gitlab_radar.config import settings
from gitlab_radar.database.fixtures import load_database_fixtures
from gitlab_radar.database.models import ScanRun
from gitlab_radar.schemas.scan import ScanState


def _database_url(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    return f'sqlite://{path}'


@asynccontextmanager
async def database_lifespan(app: FastAPI) -> AsyncIterator[None]:
    registration = RegisterTortoise(
        app=app,
        db_url=_database_url(settings.application.database_path),
        modules={'models': ['gitlab_radar.database.models']},
        generate_schemas=True,
        use_tz=True,
        timezone='UTC',
    )
    async with registration:
        await load_database_fixtures()
        await ScanRun.filter(state=ScanState.RUNNING).update(
            state=ScanState.FAILED,
            completed_at=datetime.now(UTC),
            error='Приложение было остановлено до завершения сканирования',
        )
        yield

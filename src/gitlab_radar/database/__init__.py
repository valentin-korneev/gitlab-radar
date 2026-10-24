from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from tortoise import Tortoise
from tortoise.contrib.fastapi import RegisterTortoise
lazy from fastapi import FastAPI

from gitlab_radar.config import settings
from gitlab_radar.database.models import ScanRun
from gitlab_radar.database.repository import import_legacy_snapshot
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
        await _ensure_database_columns()
        await ScanRun.filter(state=ScanState.RUNNING).update(
            state=ScanState.FAILED,
            completed_at=datetime.now(UTC),
            error='Приложение было остановлено до завершения сканирования',
        )
        await import_legacy_snapshot()
        yield


async def _ensure_database_columns() -> None:
    connection = Tortoise.get_connection('default')
    columns = await connection.execute_query_dict('PRAGMA table_info("scanrun")')
    if not any(column.get('name') == 'gitlab_requests' for column in columns):
        await connection.execute_query(
            'ALTER TABLE "scanrun" ADD COLUMN "gitlab_requests" INT NOT NULL DEFAULT 0',
        )
    project_columns = await connection.execute_query_dict('PRAGMA table_info("projectsnapshot")')
    if not any(column.get('name') == 'analysis_version' for column in project_columns):
        await connection.execute_query(
            'ALTER TABLE "projectsnapshot" ADD COLUMN "analysis_version" INT NOT NULL DEFAULT 1',
        )

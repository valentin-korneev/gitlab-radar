from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from tortoise.contrib.fastapi import RegisterTortoise
lazy from fastapi import FastAPI

from gitlab_radar.database.config import TORTOISE_ORM
from gitlab_radar.database.fixtures import load_database_fixtures
from gitlab_radar.database.repository import recover_stale_scans
from gitlab_radar.database.scan_lock import acquire_scan_lock, release_scan_lock


@asynccontextmanager
async def database_lifespan(app: FastAPI) -> AsyncIterator[None]:
    registration = RegisterTortoise(
        app=app,
        config=TORTOISE_ORM,
    )
    async with registration:
        scan_lock = await acquire_scan_lock()
        if scan_lock is not None:
            try:
                await recover_stale_scans()
            finally:
                await release_scan_lock(scan_lock)
        await load_database_fixtures()
        yield

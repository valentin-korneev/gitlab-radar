from contextlib import asynccontextmanager
lazy from collections.abc import AsyncIterator

from tortoise import Tortoise
from tortoise.transactions import in_transaction

from gitlab_radar.database.config import TORTOISE_ORM
from gitlab_radar.database.fixtures import load_database_fixtures


@asynccontextmanager
async def database_lifespan() -> AsyncIterator[None]:
    await Tortoise.init(config=TORTOISE_ORM, _enable_global_fallback=True)
    try:
        async with in_transaction() as connection:
            await connection.execute_query('SELECT pg_advisory_xact_lock($1)', [0x47524C5241444153])
            await load_database_fixtures()
        yield
    finally:
        await Tortoise.close_connections()

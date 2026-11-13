from asyncpg import Connection, connect

from gitlab_radar.config import settings

SCAN_LOCK_ID = 0x47524C5241444152


async def acquire_scan_lock() -> Connection | None:
    connection = await connect(
        timeout=5,
        command_timeout=5,
        server_settings={'application_name': 'gitlab-radar-scanner-lock'},
        host=settings.database.host,
        port=settings.database.port,
        database=settings.database.database,
        user=settings.database.user,
        password=settings.database.password.get_secret_value(),
    )
    try:
        acquired = await connection.fetchval('SELECT pg_try_advisory_lock($1)', SCAN_LOCK_ID)
    except BaseException:
        await connection.close()
        raise
    if acquired:
        return connection
    await connection.close()
    return None


async def release_scan_lock(connection: Connection) -> None:
    if connection.is_closed():
        return
    try:
        await connection.close(timeout=5)
    except TimeoutError, OSError:
        connection.terminate()

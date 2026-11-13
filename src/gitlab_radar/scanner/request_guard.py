import asyncio
from collections.abc import Callable
from datetime import UTC, datetime

from asyncpg import PostgresError
from tortoise.exceptions import BaseORMException

from gitlab_radar.database.models import ScanRun
from gitlab_radar.domain.scanning import StopSignal
from gitlab_radar.schemas.scan import ScanState


async def _check(scan: ScanRun, signal: StopSignal) -> None:
    current = await ScanRun.filter(id=scan.id, owner_token=scan.owner_token).first()
    if (
        current is None
        or current.state not in {ScanState.RUNNING, ScanState.STOPPING}
        or (current.lease_expires_at is None or current.lease_expires_at <= datetime.now(UTC))
    ):
        signal.stop('Владение заданием потеряно', lost=True)
    elif current.stop_requested_at is not None or current.state == ScanState.STOPPING:
        signal.stop()
    signal.check()


def request_guard(scan: ScanRun, signal: StopSignal) -> Callable[[], None]:
    loop = asyncio.get_running_loop()

    def check() -> None:
        signal.check()
        operation = asyncio.run_coroutine_threadsafe(_check(scan, signal), loop)
        try:
            operation.result(timeout=5)
        except TimeoutError, OSError, PostgresError, BaseORMException, RuntimeError:
            operation.cancel()
            signal.stop('Не удалось проверить разрешение на запрос GitLab', lost=True)
            signal.check()

    return check

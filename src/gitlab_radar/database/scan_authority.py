from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID
lazy from collections.abc import Iterator

lazy from tortoise.backends.base.client import BaseDBAsyncClient

from gitlab_radar.database.models import ScanRun
from gitlab_radar.domain.scanning import OwnershipLostError, ScanInterruptedError, StopSignal
from gitlab_radar.schemas.scan import ScanState

LEASE_SECONDS = 90


@dataclass(frozen=True, slots=True)
class ScanAuthority:
    scan_id: int
    token: UUID
    signal: StopSignal


_AUTHORITY: ContextVar[ScanAuthority | None] = ContextVar('scan_authority', default=None)


@contextmanager
def scan_authority(authority: ScanAuthority) -> Iterator[None]:
    token = _AUTHORITY.set(authority)
    try:
        yield
    finally:
        _AUTHORITY.reset(token)


async def assert_scan_owner(scan_id: int, connection: BaseDBAsyncClient) -> ScanRun:
    authority = _AUTHORITY.get()
    if authority is None or authority.scan_id != scan_id:
        msg = 'Нет полномочий для записи результатов задания'
        raise OwnershipLostError(msg)
    authority.signal.check()
    now = datetime.now(UTC)
    scan = (
        await ScanRun.filter(
            id=scan_id,
            owner_token=authority.token,
            lease_expires_at__gt=now,
            state__in=[ScanState.RUNNING, ScanState.STOPPING],
        )
        .using_db(connection)
        .select_for_update()
        .first()
    )
    if scan is None:
        msg = 'Владение заданием потеряно'
        authority.signal.stop(msg, lost=True)
        raise OwnershipLostError(msg)
    if scan.stop_requested_at is not None or scan.state == ScanState.STOPPING:
        authority.signal.stop()
        raise ScanInterruptedError(authority.signal.reason)
    await (
        ScanRun.filter(id=scan_id)
        .using_db(connection)
        .update(
            lease_expires_at=now + timedelta(seconds=LEASE_SECONDS),
        )
    )
    return scan

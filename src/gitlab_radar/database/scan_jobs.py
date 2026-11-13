from datetime import UTC, datetime, timedelta
from uuid import uuid4

from tortoise.transactions import in_transaction

from gitlab_radar.database.models import ScanRun
from gitlab_radar.database.scan_authority import LEASE_SECONDS, assert_scan_owner
from gitlab_radar.database.scan_repository import delete_scan_files, fail_pending_items
from gitlab_radar.schemas.scan import ScanPhase, ScanSource, ScanState

ACTIVE_STATES = (ScanState.RUNNING, ScanState.STOPPING)


async def enqueue_scan(requested_by: str | None = None) -> ScanRun | None:
    async with in_transaction() as connection:
        # Serialize manual submissions even when there is no row to lock yet.
        await connection.execute_query('SELECT pg_advisory_xact_lock($1)', [0x47524C5241444154])
        if await ScanRun.filter(state__in=(ScanState.QUEUED, *ACTIVE_STATES)).using_db(connection).exists():
            return None
        return await ScanRun.create(
            state=ScanState.QUEUED,
            phase=ScanPhase.IDLE,
            requested_by=requested_by,
            source=ScanSource.MANUAL,
            using_db=connection,
        )


async def request_stop(scan_id: int) -> ScanRun | None:
    async with in_transaction() as connection:
        scan = await ScanRun.filter(id=scan_id).using_db(connection).select_for_update().first()
        if scan is None:
            return None
        now = datetime.now(UTC)
        if scan.state == ScanState.QUEUED:
            scan.state = ScanState.CANCELLED
            scan.completed_at = now
            scan.stop_requested_at = now
        elif scan.state == ScanState.RUNNING:
            scan.state = ScanState.STOPPING
            scan.stop_requested_at = now
        await scan.save(using_db=connection, update_fields=['state', 'completed_at', 'stop_requested_at'])
        return scan


async def active_scan() -> ScanRun | None:
    scan = await ScanRun.filter(state__in=ACTIVE_STATES).order_by('id').first()
    if scan is None:
        scan = await ScanRun.filter(state=ScanState.QUEUED).order_by('id').first()
    return scan or await ScanRun.all().order_by('-id').first()


async def claim_next() -> ScanRun | None:
    async with in_transaction() as connection:
        if await ScanRun.filter(state__in=ACTIVE_STATES).using_db(connection).exists():
            return None
        scan = (
            await ScanRun.filter(state=ScanState.QUEUED).using_db(connection).select_for_update().order_by('id').first()
        )
        if scan is None:
            return None
        now = datetime.now(UTC)
        scan.state = ScanState.RUNNING
        scan.phase = ScanPhase.COLLECTING
        scan.started_at = now
        scan.owner_token = uuid4()
        scan.heartbeat_at = now
        scan.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
        await scan.save(
            using_db=connection,
            update_fields=[
                'state',
                'phase',
                'started_at',
                'owner_token',
                'heartbeat_at',
                'lease_expires_at',
            ],
        )
        return scan


async def heartbeat(scan: ScanRun) -> ScanRun | None:
    now = datetime.now(UTC)
    await ScanRun.filter(id=scan.id, owner_token=scan.owner_token, state__in=ACTIVE_STATES).update(
        heartbeat_at=now,
        lease_expires_at=now + timedelta(seconds=LEASE_SECONDS),
    )
    return await ScanRun.filter(id=scan.id, owner_token=scan.owner_token).first()


async def update_progress(scan: ScanRun, values: dict[str, object]) -> None:
    async with in_transaction() as connection:
        await assert_scan_owner(scan.id, connection)
        await ScanRun.filter(id=scan.id, owner_token=scan.owner_token).using_db(connection).update(**values)
    for key, value in values.items():
        setattr(scan, key, value)


async def finish_scan(scan: ScanRun, state: ScanState, error: str | None = None) -> bool:
    async with in_transaction() as connection:
        current = (
            await ScanRun.filter(id=scan.id, owner_token=scan.owner_token)
            .using_db(
                connection,
            )
            .select_for_update()
            .first()
        )
        if current is None:
            return False
        if current.state in ACTIVE_STATES:
            await fail_pending_items(scan.id, error or 'Сканирование остановлено')
            await delete_scan_files(scan.id)
            await (
                ScanRun.filter(id=scan.id)
                .using_db(connection)
                .update(
                    state=state,
                    error=error,
                    current_project=None,
                    completed_at=datetime.now(UTC),
                )
            )
        await (
            ScanRun.filter(id=scan.id)
            .using_db(connection)
            .update(
                owner_token=None,
                lease_expires_at=None,
                errors=scan.errors,
            )
        )
    return True


async def recover_expired_scans() -> None:
    now = datetime.now(UTC)
    candidates = await ScanRun.filter(state__in=ACTIVE_STATES).order_by('id')
    for candidate in candidates:
        async with in_transaction() as connection:
            scan = await ScanRun.get(id=candidate.id).using_db(connection).select_for_update()
            if scan.state not in ACTIVE_STATES or (scan.lease_expires_at and scan.lease_expires_at > now):
                continue
            state = ScanState.CANCELLED if scan.stop_requested_at else ScanState.FAILED
            error = 'Исполнитель остановился до завершения задания'
            await fail_pending_items(scan.id, error)
            await delete_scan_files(scan.id)
            await (
                ScanRun.filter(id=scan.id)
                .using_db(connection)
                .update(
                    state=state,
                    completed_at=now,
                    error=error,
                    current_project=None,
                    owner_token=None,
                    lease_expires_at=None,
                )
            )

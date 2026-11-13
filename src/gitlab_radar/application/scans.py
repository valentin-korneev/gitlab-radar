from gitlab_radar.database.models import ScanRun
from gitlab_radar.database.scan_jobs import active_scan, enqueue_scan, request_stop
from gitlab_radar.schemas.scan import ScanState, ScanStatus


async def scan_status(scan: ScanRun | None = None) -> ScanStatus:
    if scan is None:
        scan = await active_scan()
    if scan is None:
        return ScanStatus()
    status = ScanStatus.model_validate(scan, from_attributes=True)
    return status.model_copy(update={'queue_count': await ScanRun.filter(state=ScanState.QUEUED).count()})


async def request_scan(username: str | None) -> ScanStatus | None:
    scan = await enqueue_scan(username)
    return await scan_status(scan) if scan is not None else None


async def stop_scan(scan_id: int) -> ScanStatus | None:
    scan = await request_stop(scan_id)
    return await scan_status(scan) if scan is not None else None

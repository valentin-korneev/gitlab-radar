import asyncio
import logging
from time import monotonic

lazy from asyncpg import Connection

from gitlab_radar.clients.gitlab import ScanGitLab
from gitlab_radar.database.models import ScanRun
from gitlab_radar.database.package_history import backfill_package_history
from gitlab_radar.database.scan_authority import ScanAuthority, scan_authority
from gitlab_radar.database.scan_jobs import claim_next, finish_scan, heartbeat, recover_expired_scans
from gitlab_radar.database.scan_lock import acquire_scan_lock, release_scan_lock
from gitlab_radar.database.scan_retention import archive_old_results
from gitlab_radar.database.scan_schedules import enqueue_due_schedule
from gitlab_radar.domain.scanning import ScanInterruptedError, StopSignal
from gitlab_radar.scanner.pipeline import SCAN_ERRORS, ScanPipeline
from gitlab_radar.scanner.request_guard import request_guard
from gitlab_radar.schemas.scan import ScanState
from gitlab_radar.services.application_parameters import application_parameter_values

logger = logging.getLogger(__name__)
POLL_SECONDS = 1


def _failure(error: BaseException | None) -> BaseException | None:
    if isinstance(error, BaseExceptionGroup):
        return next((failure for child in error.exceptions if (failure := _failure(child)) is not None), None)
    return None if isinstance(error, (ScanInterruptedError, asyncio.CancelledError)) else error


class ScannerWorker:
    def __init__(self) -> None:
        self._shutdown = asyncio.Event()
        self._signal: StopSignal | None = None
        self._lock_connection: Connection | None = None
        self._task: asyncio.Task[None] | None = None
        self._next_maintenance = 0.0

    async def start(self) -> None:
        if self._task is None:
            self._shutdown = asyncio.Event()
            self._task = asyncio.create_task(self.serve(), name='gitlab-radar-worker')

    async def stop(self) -> None:
        self._shutdown.set()
        if self._signal is not None:
            self._signal.stop('Сканирование остановлено вместе с исполнителем')
        if self._task is not None:
            try:
                await asyncio.shield(self._task)
            except asyncio.CancelledError:
                await asyncio.gather(self._task, return_exceptions=True)
                raise
            finally:
                self._task = None

    async def serve(self) -> None:
        while not self._shutdown.is_set():
            connection = None
            try:
                connection = await acquire_scan_lock()
                if connection is not None:
                    await self._serve_owned(connection)
            except SCAN_ERRORS:
                logger.exception('Исполнитель временно недоступен')
            finally:
                if connection is not None:
                    await release_scan_lock(connection)
                self._lock_connection = None
            await self._wait()

    async def _serve_owned(self, connection: Connection) -> None:
        self._lock_connection = connection
        connection.add_termination_listener(self._connection_lost)
        while not self._shutdown.is_set() and not connection.is_closed():
            await connection.fetchval('SELECT 1')
            await recover_expired_scans()
            await enqueue_due_schedule()
            scan = await claim_next()
            if scan is not None and not await self._execute(scan, connection):
                return
            if scan is not None or monotonic() >= self._next_maintenance:
                history_work = await backfill_package_history()
                parameters = await application_parameter_values()
                archive_work = await archive_old_results(int(parameters['retained_scan_count']))
                self._next_maintenance = monotonic() + (POLL_SECONDS if history_work or archive_work else 30)
            if scan is None:
                await self._wait()

    def _connection_lost(self, _connection: Connection) -> None:
        if _connection is self._lock_connection and self._signal is not None:
            self._signal.stop('Потеряна блокировка исполнителя', lost=True)

    async def _wait(self) -> None:
        try:
            await asyncio.wait_for(self._shutdown.wait(), timeout=POLL_SECONDS)
        except TimeoutError:
            return

    async def _monitor(self, scan: ScanRun, connection: Connection, execution: asyncio.Task[None]) -> None:
        while not execution.done():
            if not connection.is_closed():
                try:
                    await connection.fetchval('SELECT 1')
                except SCAN_ERRORS:
                    self._signal.stop('Потеряна блокировка исполнителя', lost=True)
            else:
                self._signal.stop('Потеряна блокировка исполнителя', lost=True)
            current = await heartbeat(scan)
            if current is None:
                self._signal.stop('Владение заданием потеряно', lost=True)
                return
            if current.state == ScanState.COMPLETED:
                return
            if current.stop_requested_at is not None:
                self._signal.stop()
            await asyncio.wait({execution}, timeout=POLL_SECONDS)

    async def _execute(self, scan: ScanRun, connection: Connection) -> bool:
        signal = StopSignal()
        self._signal = signal
        if connection.is_closed():
            signal.stop('Потеряна блокировка исполнителя', lost=True)
        client = ScanGitLab(signal, before_request=request_guard(scan, signal))
        pipeline = ScanPipeline(client, signal)
        try:
            with scan_authority(ScanAuthority(scan.id, scan.owner_token, signal)):
                execution = asyncio.create_task(pipeline.run(scan), name=f'gitlab-radar-job-{scan.id}')
                monitor = asyncio.create_task(self._monitor(scan, connection, execution))
                await self._drain(execution, monitor, signal)
                failure = _failure(execution.exception()) if not execution.cancelled() else None
                await self._finish(scan, pipeline, signal, failure)
                return not signal.ownership_lost
        finally:
            client.session.close()
            self._signal = None

    async def _drain(self, execution: asyncio.Task[None], monitor: asyncio.Task[None], signal: StopSignal) -> None:
        try:
            await asyncio.wait({execution, monitor}, return_when=asyncio.FIRST_COMPLETED)
            if monitor.done() and monitor.exception() is not None:
                signal.stop('Не удалось подтвердить владение заданием', lost=True)
        except asyncio.CancelledError:
            self._shutdown.set()
            signal.stop('Исполнитель останавливается')
        finally:
            await asyncio.gather(execution, monitor, return_exceptions=True)

    @staticmethod
    async def _finish(scan: ScanRun, pipeline: ScanPipeline, signal: StopSignal, failure: BaseException | None) -> None:
        if failure is not None:
            logger.error(
                'Задание %d завершилось с ошибкой', scan.id, exc_info=(type(failure), failure, failure.__traceback__)
            )
        if signal.ownership_lost or failure is not None:
            state = ScanState.FAILED
            error = signal.reason if signal.ownership_lost else f'Ошибка исполнителя ({type(failure).__name__})'
        elif signal.event.is_set():
            state, error = ScanState.CANCELLED, signal.reason
        else:
            state, error = ScanState.COMPLETED, None
        scan.errors = list(pipeline.errors)
        await finish_scan(scan, state, error)

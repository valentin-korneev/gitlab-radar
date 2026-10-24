import logging
from datetime import UTC, datetime
from threading import Lock, Thread

from gitlab_radar.schemas.scan import ScanState, ScanStatus
from gitlab_radar.services.project import refresh_projects

logger = logging.getLogger(__name__)


class ScanTask:
    def __init__(self) -> None:
        self._lock = Lock()
        self._status = ScanStatus()
        self._thread: Thread | None = None

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._status.state is ScanState.RUNNING

    def start(self) -> bool:
        with self._lock:
            if self._status.state is ScanState.RUNNING:
                logger.warning('Запуск отклонён: сканирование уже выполняется')
                return False
            self._status = ScanStatus(state=ScanState.RUNNING, started_at=datetime.now(UTC))
            thread = Thread(target=self, name='gitlab-radar-scan', daemon=True)
            self._thread = thread

        try:
            thread.start()
        except RuntimeError as error:
            with self._lock:
                self._status.state = ScanState.FAILED
                self._status.completed_at = datetime.now(UTC)
                self._status.error = str(error)
            logger.exception('Не удалось запустить поток сканирования')
            raise

        logger.info('Сканирование поставлено на выполнение')
        return True

    def status(self) -> ScanStatus:
        with self._lock:
            return self._status.model_copy(deep=True)

    def _update_progress(self, processed: int, total: int) -> None:
        with self._lock:
            self._status.processed_projects = processed
            self._status.total_projects = total
        logger.info('Прогресс сканирования: %d/%d проектов', processed, total)

    def __call__(self) -> None:
        logger.info('Сканирование проектов запущено')
        try:
            projects, errors = refresh_projects(self._update_progress)
        except Exception as error:
            with self._lock:
                self._status.state = ScanState.FAILED
                self._status.completed_at = datetime.now(UTC)
                self._status.error = str(error)
            logger.exception('Сканирование проектов завершилось из-за ошибки')
        else:
            completed_at = datetime.now(UTC)
            with self._lock:
                started_at = self._status.started_at
                self._status.state = ScanState.COMPLETED
                self._status.completed_at = completed_at
                self._status.projects_count = len(projects)
                self._status.processed_projects = len(projects)
                self._status.total_projects = len(projects)
                self._status.errors = errors
            duration = (completed_at - started_at).total_seconds() if started_at else 0
            logger.info(
                'Сканирование завершено: проектов %d, ошибок %d, длительность %.2f секунды',
                len(projects),
                len(errors),
                duration,
            )


scan_task = ScanTask()

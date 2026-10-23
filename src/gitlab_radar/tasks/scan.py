import logging
from datetime import UTC, datetime
from threading import Lock

from gitlab_radar.schemas.scan import ScanState, ScanStatus
from gitlab_radar.services.project import ProjectService

logger = logging.getLogger(__name__)


class ScanTask:
    def __init__(self) -> None:
        self._lock = Lock()
        self._status = ScanStatus()

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._status.state is ScanState.RUNNING

    def reserve(self) -> bool:
        with self._lock:
            if self._status.state is ScanState.RUNNING:
                return False
            self._status = ScanStatus(state=ScanState.RUNNING, started_at=datetime.now(UTC))
            return True

    def status(self) -> ScanStatus:
        with self._lock:
            return self._status.model_copy(deep=True)

    def __call__(self) -> None:
        logger.info('Сканирование проектов запущено')
        try:
            project_service = ProjectService()
            projects = project_service.refresh_projects()
        except Exception as error:
            with self._lock:
                self._status.state = ScanState.FAILED
                self._status.completed_at = datetime.now(UTC)
                self._status.error = str(error)
            logger.exception('Сканирование проектов завершилось из-за ошибки')
        else:
            with self._lock:
                self._status.state = ScanState.COMPLETED
                self._status.completed_at = datetime.now(UTC)
                self._status.projects_count = len(projects)
            logger.info('Сканирование проектов завершено')


scan_task = ScanTask()

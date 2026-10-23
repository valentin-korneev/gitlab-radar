import logging
from threading import Lock

from gitlab_radar.services.project import ProjectService

logger = logging.getLogger(__name__)


class ScanTask:
    def __init__(self) -> None:
        self._lock = Lock()
        self._is_running = False

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._is_running

    def reserve(self) -> bool:
        with self._lock:
            if self._is_running:
                return False
            self._is_running = True
            return True

    def __call__(self) -> None:
        logger.info('Сканирование проектов запущено')
        try:
            project_service = ProjectService()
            project_service.refresh_projects()
        except Exception:
            logger.exception('Сканирование проектов завершилось из-за ошибки')
            raise
        else:
            logger.info('Сканирование проектов завершено')
        finally:
            with self._lock:
                self._is_running = False


scan_task = ScanTask()

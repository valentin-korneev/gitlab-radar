import asyncio

from gitlab_radar.services.project import ProjectService


class ScanTask:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    @property
    def is_running(self) -> bool:
        return self._lock.locked()

    async def __call__(self) -> None:
        if self.is_running:
            return

        async with self._lock:
            project_service = ProjectService()
            project_service.refresh_projects()

scan_task = ScanTask()

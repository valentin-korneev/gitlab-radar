from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, computed_field


class ScanState(StrEnum):
    IDLE = 'idle'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'


class ScanPhase(StrEnum):
    IDLE = 'idle'
    COLLECTING = 'collecting'
    ANALYZING = 'analyzing'
    PUBLISHING = 'publishing'
    COMPLETED = 'completed'


SCAN_STATE_TITLES = {
    ScanState.IDLE: 'Ожидание',
    ScanState.RUNNING: 'Выполняется',
    ScanState.COMPLETED: 'Завершено',
    ScanState.FAILED: 'Ошибка',
}


class ScanStatus(BaseModel):
    id: int | None = None
    state: ScanState = ScanState.IDLE
    phase: ScanPhase = ScanPhase.IDLE
    started_at: datetime | None = None
    completed_at: datetime | None = None
    projects_count: int = 0
    total_steps: int = 0
    completed_steps: int = 0
    collected_projects: int = 0
    analyzed_projects: int = 0
    reused_projects: int = 0
    skipped_projects: int = 0
    gitlab_requests: int = 0
    current_project: str | None = None
    error: str | None = None
    errors: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def state_title(self) -> str:
        return SCAN_STATE_TITLES[self.state]

    @computed_field
    @property
    def progress_percentage(self) -> float:
        if not self.total_steps:
            return 0.0
        return round(self.completed_steps / self.total_steps * 100, 1)

    @computed_field
    @property
    def duration_seconds(self) -> float:
        if not self.started_at:
            return 0.0
        end = self.completed_at or datetime.now(UTC)
        return round((end - self.started_at).total_seconds(), 1)

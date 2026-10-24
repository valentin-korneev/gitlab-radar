from enum import StrEnum
lazy from datetime import UTC, datetime

from pydantic import BaseModel, Field, computed_field


class ScanState(StrEnum):
    IDLE = 'idle'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'


SCAN_STATE_TITLES = {
    ScanState.IDLE: 'Ожидание',
    ScanState.RUNNING: 'Выполняется',
    ScanState.COMPLETED: 'Завершено',
    ScanState.FAILED: 'Ошибка',
}


class ScanStatus(BaseModel):
    state: ScanState = ScanState.IDLE
    started_at: datetime | None = None
    completed_at: datetime | None = None
    projects_count: int = 0
    total_projects: int = 0
    processed_projects: int = 0
    error: str | None = None
    errors: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def state_title(self) -> str:
        return SCAN_STATE_TITLES[self.state]

    @computed_field
    @property
    def progress_percentage(self) -> float:
        if not self.total_projects:
            return 0.0
        return round(self.processed_projects / self.total_projects * 100, 1)

    @computed_field
    @property
    def duration_seconds(self) -> float:
        if not self.started_at:
            return 0.0
        end = self.completed_at or datetime.now(UTC)
        return round((end - self.started_at).total_seconds(), 1)

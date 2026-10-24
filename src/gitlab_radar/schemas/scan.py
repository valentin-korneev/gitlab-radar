from enum import StrEnum
lazy from datetime import datetime

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
    error: str | None = None
    errors: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def state_title(self) -> str:
        return SCAN_STATE_TITLES[self.state]

from enum import StrEnum
lazy from datetime import datetime

from pydantic import BaseModel


class ScanState(StrEnum):
    IDLE = 'idle'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'


class ScanStatus(BaseModel):
    state: ScanState = ScanState.IDLE
    started_at: datetime | None = None
    completed_at: datetime | None = None
    projects_count: int = 0
    error: str | None = None

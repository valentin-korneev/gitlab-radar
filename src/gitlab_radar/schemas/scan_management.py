from datetime import datetime, time
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, field_validator

from gitlab_radar.schemas.project import AnalysisDiagnostic
from gitlab_radar.schemas.scan import ScanItemState, ScanSource, ScanState, ScanStatus
from gitlab_radar.schemas.scan_options import ScanOptions


class SchedulePayload(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    enabled: bool = False
    time_of_day: time
    weekdays: list[Annotated[int, Field(ge=0, le=6)]] = Field(
        default_factory=lambda: list(range(7)), min_length=1, max_length=7
    )
    options: ScanOptions = Field(default_factory=ScanOptions)

    @field_validator('time_of_day')
    @classmethod
    def validate_time(cls, value: time) -> time:
        if value.tzinfo is not None or value.second or value.microsecond:
            message = 'Укажите время с точностью до минуты без часового пояса'
            raise ValueError(message)
        return value

    @field_validator('weekdays')
    @classmethod
    def validate_weekdays(cls, value: list[int]) -> list[int]:
        return sorted(set(value))


class ScheduleStatus(SchedulePayload):
    id: int
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    created_at: datetime


class ScheduleEnabled(BaseModel):
    enabled: bool


class ScanItemSummary(BaseModel):
    id: int
    project_id: int
    project_path: str
    ref: str
    state: ScanItemState
    error: str | None = None
    scanned_at: datetime | None = None
    result_id: int | None = None


class ScanItemDetail(ScanItemSummary):
    revision: str | None = None
    analysis_fingerprint: str
    diagnostics: list[AnalysisDiagnostic] = Field(default_factory=list)


class ScanItemsPage(BaseModel):
    items: list[ScanItemSummary]
    cursor: int
    has_more: bool


class ScanHistoryPage(BaseModel):
    items: list[ScanStatus]
    cursor: int | None
    has_more: bool


class ScanHistoryQuery(BaseModel):
    before: int | None = Field(default=None, ge=1)
    limit: int = Field(default=30, ge=1, le=100)
    state: ScanState | None = None
    source: ScanSource | None = None
    schedule_id: int | None = Field(default=None, ge=1)

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from gitlab_radar.schemas.scan import ScanItemState, ScanState, ScanTargetKind


class PackageChangeKind(StrEnum):
    ADDED = 'added'
    REMOVED = 'removed'
    UPDATED = 'updated'


class TargetSummary(BaseModel):
    id: int
    kind: ScanTargetKind
    ref: str
    is_default: bool


class ProjectHistoryQuery(BaseModel):
    target_id: int | None = Field(default=None, ge=1)
    before: int | None = Field(default=None, ge=1)
    limit: int = Field(default=30, ge=1, le=100)


class ProjectObservation(BaseModel):
    id: int
    scan_id: int
    state: ScanItemState
    revision: str | None
    scanned_at: datetime | None
    created_at: datetime
    error: str | None
    results_archived: bool
    history_recorded: bool
    observed_languages: list[str]
    baseline_languages: list[str]
    added_packages: int
    removed_packages: int
    updated_packages: int


class ProjectHistoryPage(BaseModel):
    target: TargetSummary
    items: list[ProjectObservation]
    cursor: int | None
    has_more: bool


class PackageChangeQuery(BaseModel):
    target_id: int | None = Field(default=None, ge=1)
    after: str = Field(default='', pattern=r'^(?:[0-9a-f]{64})?$')
    limit: int = Field(default=50, ge=1, le=100)
    language: str | None = Field(default=None, max_length=100)
    name: str | None = Field(default=None, max_length=1000)
    module_path: str | None = Field(default=None, max_length=1000)


class PackageChange(BaseModel):
    package_key: str
    language: str
    module_path: str
    scope: str
    name: str
    kind: PackageChangeKind
    before_versions: list[str | None]
    after_versions: list[str | None]


class PackageChangesPage(BaseModel):
    items: list[PackageChange]
    cursor: str
    has_more: bool
    history_recorded: bool
    observed_languages: list[str]
    baseline_languages: list[str]


class PackagePeriodSummary(BaseModel):
    package_key: str
    language: str
    module_path: str
    scope: str
    name: str
    versions: list[str | None]
    scan_from_id: int
    scan_to_id: int
    closed_in_id: int | None
    baseline: bool


class PackagePeriodsPage(BaseModel):
    items: list[PackagePeriodSummary]
    cursor: int | None
    has_more: bool


class ScanChartPoint(BaseModel):
    id: int
    created_at: datetime
    duration_seconds: float
    state: ScanState
    successful: int = 0
    partial: int = 0
    failed: int = 0
    skipped: int = 0


class PackageInventoryPage(BaseModel):
    items: list[PackagePeriodSummary]
    cursor: str
    has_more: bool

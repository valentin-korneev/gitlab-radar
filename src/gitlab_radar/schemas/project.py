from __future__ import annotations

from enum import StrEnum
lazy from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from gitlab_radar.schemas.dependency import Dependency, DependencyGroup
lazy from gitlab_radar.schemas.technology import PackageManager


class ProjectLanguage(BaseModel):
    code: str
    name: str
    percentage: float
    analysis_status: str = 'pending'
    analyzer_version: str | None = None
    error: str | None = None


class ProjectFramework(BaseModel):
    code: str
    name: str
    language: str


class ProjectDataStatus(StrEnum):
    CURRENT = 'current'
    STALE = 'stale'
    MISSING = 'missing'


class ProjectSubproject(BaseModel):
    path: str
    language: str = 'python'
    package_manager: PackageManager
    runtime_version: str | None = None
    python_version: str | None = None
    python_constraint: str | None = None
    python_version_source: str | None = None
    dependencies: list[Dependency] = Field(default_factory=list)
    optional_dependencies: list[DependencyGroup] = Field(default_factory=list)
    transitive_dependencies: list[Dependency] = Field(default_factory=list)
    configured_tools: list[str] = Field(default_factory=list)
    package_registries: list[str] = Field(default_factory=list)
    container_images: list[ContainerImage] = Field(default_factory=list)
    has_docker: bool = False
    company_compliance_percentage: float = 0.0
    company_rule_results: dict[str, bool] = Field(default_factory=dict)


class GitLabComponent(BaseModel):
    name: str
    version: str | None = None


class ProjectHook(BaseModel):
    id: int
    url: str
    name: str | None = None
    description: str | None = None
    events: list[str] = Field(default_factory=list)
    enable_ssl_verification: bool = True
    alert_status: str | None = None


class ContainerSource(StrEnum):
    DOCKERFILE = 'dockerfile'
    COMPOSE = 'compose'


class ContainerImage(BaseModel):
    registry: str
    image: str
    version: str | None = None
    source: ContainerSource
    file_path: str

    @field_validator('registry', 'image', 'version', mode='before')
    @classmethod
    def strip_reference_quotes(cls, value: object) -> object:
        return value.strip().strip('"\'') if isinstance(value, str) else value


class Project(BaseModel):
    model_config = ConfigDict(extra='ignore')

    id: int
    name: str
    path_with_namespace: str
    default_branch: str | None
    web_url: str
    last_activity_at: datetime | None
    scanned_at: datetime | None = None
    data_status: ProjectDataStatus = ProjectDataStatus.CURRENT
    package_manager: PackageManager | None = None
    languages: list[ProjectLanguage] = Field(default_factory=list)
    frameworks: list[ProjectFramework] = Field(default_factory=list)
    is_empty: bool = False
    subprojects: list[ProjectSubproject] = Field(default_factory=list)
    has_docker: bool = False
    has_gitlab_ci: bool = False
    gitlab_ci_components: list[GitLabComponent] = Field(default_factory=list)
    webhooks: list[ProjectHook] = Field(default_factory=list)
    webhooks_accessible: bool = False
    gitlab_access_level: int = 0
    package_registries: list[str] = Field(default_factory=list)
    container_images: list[ContainerImage] = Field(default_factory=list)
    company_compliance_percentage: float = 0.0
    company_rule_results: dict[str, bool] = Field(default_factory=dict)
    revision: str | None = None
    scan_error: str | None = None

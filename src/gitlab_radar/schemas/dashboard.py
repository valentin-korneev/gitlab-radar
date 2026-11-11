from pydantic import BaseModel, Field


class LanguageOption(BaseModel):
    code: str
    name: str
    oldest_current_version: str | None = None


class TechnologyUsage(BaseModel):
    name: str
    projects_count: int
    languages: list[str] = Field(default_factory=list)


class LanguageStatistics(LanguageOption):
    projects_count: int
    percentage: float
    enabled: bool
    oldest_current_version: str | None = None


class LanguageTechnologyStatistics(LanguageOption):
    projects_count: int
    package_managers: list[TechnologyUsage] = Field(default_factory=list)
    versions: list[TechnologyUsage] = Field(default_factory=list)


class DependencyLevelStatistics(BaseModel):
    level: str
    title: str
    by_language: dict[str, int] = Field(default_factory=dict)
    total: int


class DependencyCountStatistics(BaseModel):
    languages: list[LanguageOption] = Field(default_factory=list)
    levels: list[DependencyLevelStatistics] = Field(default_factory=list)


class CompanyRequirement(BaseModel):
    code: str
    title: str
    description: str
    matching_projects: int
    total_projects: int
    compliance_percentage: float


class DependencyStatistics(BaseModel):
    name: str
    language: str
    projects_count: int


class FrameworkStatistics(BaseModel):
    code: str
    name: str
    language: str
    projects_count: int


class DataQualityStatistics(BaseModel):
    unknown_package_manager: int
    unknown_language_version: int
    projects_without_subprojects: int
    analysis_errors: int


class LastScanStatistics(BaseModel):
    completed_at: str | None
    duration_seconds: float
    errors_count: int
    reused_projects: int
    skipped_projects: int
    gitlab_requests: int


class TechnologyTarget(BaseModel):
    languages: list[TechnologyUsage]
    dependencies: list[TechnologyUsage]
    images: list[TechnologyUsage]
    registries: list[TechnologyUsage]


class Dashboard(BaseModel):
    projects_count: int
    empty_projects_count: int
    subprojects_count: int
    docker_projects_count: int
    gitlab_ci_projects_count: int
    languages: list[LanguageStatistics]
    enabled_languages: list[LanguageOption]
    language_technologies: list[LanguageTechnologyStatistics]
    dependency_counts: DependencyCountStatistics
    top_dependencies: list[DependencyStatistics]
    frameworks: list[FrameworkStatistics]
    company_requirements: list[CompanyRequirement]
    technology_target: TechnologyTarget
    registries: list[TechnologyUsage]
    data_quality: DataQualityStatistics
    last_scan: LastScanStatistics | None = None

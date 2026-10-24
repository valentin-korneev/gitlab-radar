from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from gitlab_radar.schemas.dependency import Dependency, DependencyGroup
from gitlab_radar.schemas.technology import PackageManager


class ProjectSubproject(BaseModel):
    path: str
    package_manager: PackageManager
    python_version: str | None = None
    python_constraint: str | None = None
    python_version_source: str | None = None
    dependencies: list[Dependency] = Field(default_factory=list)
    optional_dependencies: list[DependencyGroup] = Field(default_factory=list)
    transitive_dependencies: list[Dependency] = Field(default_factory=list)
    configured_tools: list[str] = Field(default_factory=list)
    has_docker: bool = False
    company_compliance_percentage: float = 0.0
    company_rule_results: dict[str, bool] = Field(default_factory=dict)


class GitLabComponent(BaseModel):
    name: str
    version: str | None = None


class Project(BaseModel):
    model_config = ConfigDict(extra='ignore')

    id: int
    name: str
    path_with_namespace: str
    default_branch: str | None
    web_url: str
    last_activity_at: datetime | None
    package_manager: PackageManager | None = None
    subprojects: list[ProjectSubproject] = Field(default_factory=list)
    has_docker: bool = False
    has_gitlab_ci: bool = False
    gitlab_ci_components: list[GitLabComponent] = Field(default_factory=list)
    company_compliance_percentage: float = 0.0
    company_rule_results: dict[str, bool] = Field(default_factory=dict)
    revision: str | None = None
    scan_error: str | None = None

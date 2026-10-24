from pydantic import BaseModel

lazy from gitlab_radar.schemas.technology import PackageManager


class PackageManagerStatistics(BaseModel):
    package_manager: PackageManager
    title: str
    projects_count: int
    percentage: float


class CompanyRequirement(BaseModel):
    code: str
    title: str
    description: str
    matching_projects: int
    total_projects: int
    compliance_percentage: float


class DependencyStatistics(BaseModel):
    name: str
    projects_count: int


class DependencyCountStatistics(BaseModel):
    total: int
    direct: int
    optional: int
    transitive: int


class PythonVersionStatistics(BaseModel):
    version: str
    projects_count: int


class Dashboard(BaseModel):
    projects_count: int
    docker_projects_count: int
    gitlab_ci_projects_count: int
    package_managers: list[PackageManagerStatistics]
    dependency_counts: DependencyCountStatistics
    python_versions: list[PythonVersionStatistics]
    top_dependencies: list[DependencyStatistics]
    company_requirements: list[CompanyRequirement]

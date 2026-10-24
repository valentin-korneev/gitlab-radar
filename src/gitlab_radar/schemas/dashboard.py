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


class Dashboard(BaseModel):
    projects_count: int
    package_managers: list[PackageManagerStatistics]
    top_dependencies: list[DependencyStatistics]
    company_requirements: list[CompanyRequirement]

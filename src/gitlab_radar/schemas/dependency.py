from enum import StrEnum

from pydantic import BaseModel, Field


class DependencyLevel(StrEnum):
    DIRECT = 'direct'
    OPTIONAL = 'optional'
    TRANSITIVE = 'transitive'


class Dependency(BaseModel):
    name: str
    version: str | None = None


class DependencyGroup(BaseModel):
    name: str
    dependencies: list[Dependency] = Field(default_factory=list)


class DependencyProject(BaseModel):
    id: int
    name: str
    path_with_namespace: str
    subproject_path: str
    web_url: str


class DependencyVersionUsage(BaseModel):
    version: str | None = None
    projects: list[DependencyProject] = Field(default_factory=list)


class DependencyUsage(BaseModel):
    name: str
    level: DependencyLevel
    projects_count: int
    versions: list[DependencyVersionUsage] = Field(default_factory=list)

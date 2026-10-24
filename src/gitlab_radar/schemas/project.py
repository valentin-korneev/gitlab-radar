lazy from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

lazy from gitlab_radar.schemas.technology import PackageManager


class ProjectSubproject(BaseModel):
    path: str
    package_manager: PackageManager


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

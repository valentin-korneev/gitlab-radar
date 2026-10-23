lazy from datetime import datetime

from pydantic import BaseModel, ConfigDict


class Project(BaseModel):
    model_config = ConfigDict(extra='ignore')

    id: int
    name: str
    path_with_namespace: str
    default_branch: str | None
    web_url: str
    last_activity_at: datetime | None

from typing import Annotated

from pydantic import BaseModel, StringConstraints

BlacklistPattern = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class ProjectBlacklistRulePayload(BaseModel):
    pattern: BlacklistPattern


class ProjectBlacklistRule(ProjectBlacklistRulePayload):
    id: int

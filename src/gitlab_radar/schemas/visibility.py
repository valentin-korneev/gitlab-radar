from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

VisibilityAction = Literal['include', 'exclude']
VisibilityName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
VisibilityPattern = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class VisibilityRulePayload(BaseModel):
    action: VisibilityAction
    pattern: VisibilityPattern


class VisibilityRule(VisibilityRulePayload):
    id: int


class UserVisibilityGroupPayload(BaseModel):
    name: VisibilityName
    rules: list[VisibilityRulePayload] = Field(default_factory=list)


class UserVisibilityGroup(UserVisibilityGroupPayload):
    id: int
    is_default: bool
    rules: list[VisibilityRule]


class DefaultVisibilityGroupUpdate(BaseModel):
    group_id: int | None = None


class AdminVisibilityPolicyPayload(BaseModel):
    name: VisibilityName
    rules: list[VisibilityRulePayload] = Field(default_factory=list)


class AdminVisibilityPolicy(AdminVisibilityPolicyPayload):
    id: int
    rules: list[VisibilityRule]


class AdminUserVisibilityPayload(BaseModel):
    policy_ids: list[int] = Field(default_factory=list)
    rules: list[VisibilityRulePayload] = Field(default_factory=list)


class AdminUserVisibility(AdminUserVisibilityPayload):
    preferred_username: str
    rules: list[VisibilityRule]

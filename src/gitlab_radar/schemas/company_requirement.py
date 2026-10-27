from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class RequirementSource(StrEnum):
    PYTHON_VERSION = 'python_version'
    PACKAGE_MANAGER = 'package_manager'
    DEPENDENCY = 'dependency'
    TOOL = 'tool'
    DEPENDENCY_AND_TOOL = 'dependency_and_tool'
    CI_COMPONENT = 'ci_component'
    WEBHOOK = 'webhook'
    PACKAGE_REGISTRY = 'package_registry'
    CONTAINER_REGISTRY = 'container_registry'


class RequirementOperator(StrEnum):
    GREATER_THAN = 'greater_than'
    GREATER_THAN_OR_EQUAL = 'greater_than_or_equal'
    EQUALS = 'equals'
    NOT_EQUALS = 'not_equals'
    CONTAINS = 'contains'
    NOT_CONTAINS = 'not_contains'
    ALL_CONTAIN_ANY = 'all_contain_any'


class RequirementLogic(StrEnum):
    AND = 'and'
    OR = 'or'


class RequirementCondition(BaseModel):
    source: RequirementSource
    operator: RequirementOperator
    values: list[str] = Field(min_length=1)
    empty_result: bool = False


class RequirementConditionGroup(BaseModel):
    logic: RequirementLogic = RequirementLogic.AND
    items: list[RequirementCondition | RequirementConditionGroup] = Field(min_length=1)


class CompanyRequirementBase(BaseModel):
    code: str = Field(min_length=1, max_length=100, pattern=r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
    title: str = Field(min_length=1, max_length=200)
    group_id: int = Field(gt=0)
    description: str = ''
    condition: RequirementConditionGroup
    enabled: bool = True
    sort_order: int = 0


class CompanyRequirementCreate(CompanyRequirementBase):
    pass


class CompanyRequirementUpdate(CompanyRequirementBase):
    pass


class CompanyRequirementEnabled(BaseModel):
    enabled: bool


class CompanyRequirementMove(BaseModel):
    group_id: int = Field(gt=0)


class CompanyRequirementOrder(BaseModel):
    group_id: int = Field(gt=0)
    requirement_ids: list[int] = Field(min_length=1)


class CompanyRequirement(CompanyRequirementBase):
    id: int


class CompanyRequirementGroupBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = ''
    sort_order: int = 0


class CompanyRequirementGroupCreate(CompanyRequirementGroupBase):
    pass


class CompanyRequirementGroupUpdate(CompanyRequirementGroupBase):
    pass


class CompanyRequirementGroup(CompanyRequirementGroupBase):
    id: int


class CompanyRequirementGroupOrder(BaseModel):
    group_ids: list[int] = Field(min_length=1)


class RequirementOption(BaseModel):
    value: str
    title: str
    default_operator: str | None = None
    default_values: list[str] = Field(default_factory=list)


class RequirementCatalog(BaseModel):
    sources: list[RequirementOption]
    operators: list[RequirementOption]

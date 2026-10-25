from enum import StrEnum

from pydantic import BaseModel, Field


class ParameterValueType(StrEnum):
    STRING = 'string'
    VERSION = 'version'
    INTEGER = 'integer'
    PERCENTAGE_RANGE = 'percentage_range'


class ApplicationParameter(BaseModel):
    key: str
    title: str
    description: str = ''
    value: str
    value_type: ParameterValueType
    min_value: int | None = None
    max_value: int | None = None
    sort_order: int = 0


class ApplicationParameterUpdate(BaseModel):
    values: dict[str, str] = Field(min_length=1)

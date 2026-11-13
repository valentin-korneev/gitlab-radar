from pydantic import BaseModel, Field, PositiveInt, field_validator


class ScanOptions(BaseModel):
    project_ids: list[PositiveInt] | None = Field(default=None, min_length=1, max_length=1000)
    force_analysis: bool = False

    @field_validator('project_ids')
    @classmethod
    def validate_project_ids(cls, value: list[int] | None) -> list[int] | None:
        if value is not None:
            return sorted(set(value))
        return value

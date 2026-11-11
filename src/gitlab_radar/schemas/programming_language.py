from pydantic import BaseModel, Field


class ProgrammingLanguage(BaseModel):
    id: int
    code: str
    name: str
    enabled: bool
    oldest_current_version: str | None = None
    analyzer_key: str | None = None
    analyzer_version: str | None = None
    package_managers: list[str] = Field(default_factory=list)


class ProgrammingLanguageEnabled(BaseModel):
    enabled: bool


class ProgrammingLanguageVersion(BaseModel):
    oldest_current_version: str | None = Field(default=None, max_length=50)


class ProgrammingFramework(BaseModel):
    id: int
    code: str
    name: str
    enabled: bool
    language_code: str
    language_name: str
    language_enabled: bool
    dependency_names: list[str] = Field(default_factory=list)


class ProgrammingFrameworkEnabled(BaseModel):
    enabled: bool

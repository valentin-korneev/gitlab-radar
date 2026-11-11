from dataclasses import dataclass
from typing import Protocol

from gitlab_radar.schemas.project import Project, ProjectSubproject


@dataclass(frozen=True, slots=True)
class FileSelection:
    path: str
    analyzer_key: str
    role: str
    language_code: str | None = None


class LanguageAnalyzer(Protocol):
    key: str
    language_code: str
    version: str
    package_manager_codes: tuple[str, ...]

    def select_files(self, repository_paths: list[str]) -> list[FileSelection]: ...

    def analyze(self, project: Project, files: dict[str, bytes]) -> list[ProjectSubproject]: ...

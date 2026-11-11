from typing import Protocol
lazy from collections.abc import Iterable

from gitlab_radar.schemas.project import Project, ProjectSubproject


class FrameworkDefinition(Protocol):
    code: str
    language: object
    dependency_names: list[object]


FRAMEWORK_SUPERSEDES = {
    'fastapi': frozenset({'starlette'}),
}


def detected_framework_codes(
    project: Project,
    frameworks: Iterable[FrameworkDefinition],
) -> set[str]:
    framework_list = list(frameworks)
    project_codes: set[str] = set()
    for subproject in project.subprojects:
        dependency_names = _subproject_dependency_names(subproject)
        detected = {
            framework.code
            for framework in framework_list
            if subproject.language == framework.language.code
            and bool(
                {str(name).casefold() for name in framework.dependency_names}
                & dependency_names
            )
        }
        for framework_code, superseded_codes in FRAMEWORK_SUPERSEDES.items():
            if framework_code in detected:
                detected.difference_update(superseded_codes)
        project_codes.update(detected)
    return project_codes


def _subproject_dependency_names(subproject: ProjectSubproject) -> set[str]:
    dependencies = [
        *subproject.dependencies,
        *subproject.transitive_dependencies,
        *(dependency for group in subproject.optional_dependencies for dependency in group.dependencies),
    ]
    return {dependency.name.casefold() for dependency in dependencies}

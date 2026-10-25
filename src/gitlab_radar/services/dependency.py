from collections import defaultdict
from collections.abc import Iterable

from gitlab_radar.schemas.dependency import (
    Dependency,
    DependencyLevel,
    DependencyProject,
    DependencySource,
    DependencyUsage,
    DependencyVersionUsage,
)
from gitlab_radar.schemas.project import Project, ProjectSubproject
from gitlab_radar.services.project import load_projects

UsageEntry = tuple[Project, str, Dependency, DependencyLevel]


async def build_dependency_catalog(
        projects: list[Project] | None = None,
        source: DependencySource = DependencySource.PYTHON,
) -> list[DependencyUsage]:
    projects = await load_projects() if projects is None else projects
    entries = {
        DependencySource.PYTHON: _python_entries,
        DependencySource.DOCKER: _docker_entries,
        DependencySource.CI: _ci_entries,
        DependencySource.WEBHOOK: _webhook_entries,
    }[source](projects)
    return _build_catalog(entries)


def _python_entries(projects: list[Project]) -> Iterable[UsageEntry]:
    for project in projects:
        for subproject in project.subprojects:
            for dependency, level in subproject_dependency_entries(subproject):
                yield project, subproject.path, dependency, level


def _docker_entries(projects: list[Project]) -> Iterable[UsageEntry]:
    for project in projects:
        for image in project.container_images:
            name = f'{image.registry}/{image.image}'
            path = image.file_path.rpartition('/')[0] or '.'
            yield project, path, Dependency(name=name, version=image.version), DependencyLevel.DIRECT


def _ci_entries(projects: list[Project]) -> Iterable[UsageEntry]:
    for project in projects:
        for component in project.gitlab_ci_components:
            yield project, '.', Dependency(name=component.name, version=component.version), DependencyLevel.DIRECT


def _webhook_entries(projects: list[Project]) -> Iterable[UsageEntry]:
    for project in projects:
        for hook in project.webhooks:
            yield project, '.', Dependency(name=hook.url), DependencyLevel.DIRECT


def _build_catalog(entries: Iterable[UsageEntry]) -> list[DependencyUsage]:
    usage: dict[
        str,
        dict[str | None, dict[int, DependencyProject]],
    ] = defaultdict(lambda: defaultdict(dict))
    priorities = {
        DependencyLevel.DIRECT: 0,
        DependencyLevel.OPTIONAL: 1,
        DependencyLevel.TRANSITIVE: 2,
    }
    for project, path, dependency, level in entries:
        reference = DependencyProject(
            id=project.id,
            name=project.name,
            path_with_namespace=project.path_with_namespace,
            subproject_path=path,
            web_url=project.web_url,
            level=level,
        )
        projects_by_version = usage[dependency.name][dependency.version]
        existing = projects_by_version.get(project.id)
        if existing is None or priorities[level] < priorities[existing.level]:
            projects_by_version[project.id] = reference

    catalog: list[DependencyUsage] = []
    for name, versions in usage.items():
        references = [reference for values in versions.values() for reference in values.values()]
        levels = sorted({reference.level for reference in references}, key=priorities.__getitem__)
        catalog.append(
            DependencyUsage(
                name=name,
                level=levels[0],
                levels=levels,
                projects_count=len({reference.id for reference in references}),
                versions=[
                    DependencyVersionUsage(
                        version=version,
                        projects=sorted(
                            projects_by_version.values(),
                            key=lambda item: (item.path_with_namespace, item.subproject_path),
                        ),
                    )
                    for version, projects_by_version in sorted(
                        versions.items(),
                        key=lambda item: (item[0] is None, item[0] or ''),
                    )
                ],
            ),
        )
    return sorted(catalog, key=lambda item: (-item.projects_count, item.name))


def project_dependency_names(project: Project) -> set[str]:
    return {
        dependency.name
        for subproject in project.subprojects
        for dependency in subproject_dependencies(subproject)
    }


def subproject_dependencies(subproject: ProjectSubproject) -> Iterable[Dependency]:
    for dependency, _ in subproject_dependency_entries(subproject):
        yield dependency


def subproject_dependency_entries(
        subproject: ProjectSubproject,
) -> Iterable[tuple[Dependency, DependencyLevel]]:
    yield from ((dependency, DependencyLevel.DIRECT) for dependency in subproject.dependencies)
    yield from (
        (dependency, DependencyLevel.OPTIONAL)
        for group in subproject.optional_dependencies
        for dependency in group.dependencies
    )
    yield from (
        (dependency, DependencyLevel.TRANSITIVE)
        for dependency in subproject.transitive_dependencies
    )

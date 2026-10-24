from collections import defaultdict
from collections.abc import Iterable

from gitlab_radar.schemas.dependency import (
    Dependency,
    DependencyLevel,
    DependencyProject,
    DependencyUsage,
    DependencyVersionUsage,
)
from gitlab_radar.schemas.project import Project, ProjectSubproject
from gitlab_radar.services.project import load_projects


async def build_dependency_catalog(projects: list[Project] | None = None) -> list[DependencyUsage]:
    projects = await load_projects() if projects is None else projects
    usage: dict[str, dict[str | None, dict[tuple[int, str, DependencyLevel], DependencyProject]]] = defaultdict(
        lambda: defaultdict(dict),
    )
    levels: dict[str, DependencyLevel] = {}
    priorities = {
        DependencyLevel.DIRECT: 0,
        DependencyLevel.OPTIONAL: 1,
        DependencyLevel.TRANSITIVE: 2,
    }

    for project in projects:
        for subproject in project.subprojects:
            for dependency, level in subproject_dependency_entries(subproject):
                reference = DependencyProject(
                    id=project.id,
                    name=project.name,
                    path_with_namespace=project.path_with_namespace,
                    subproject_path=subproject.path,
                    web_url=project.web_url,
                    level=level,
                )
                usage[dependency.name][dependency.version][(project.id, subproject.path, level)] = reference
                current = levels.get(dependency.name)
                if current is None or priorities[level] < priorities[current]:
                    levels[dependency.name] = level

    catalog: list[DependencyUsage] = []
    for name, versions in usage.items():
        project_ids = {
            project.id
            for projects_by_version in versions.values()
            for project in projects_by_version.values()
        }
        catalog.append(
            DependencyUsage(
                name=name,
                level=levels[name],
                levels=sorted(
                    {
                        project.level
                        for projects_by_version in versions.values()
                        for project in projects_by_version.values()
                    },
                    key=lambda usage_level: priorities[usage_level],
                ),
                projects_count=len(project_ids),
                versions=[
                    DependencyVersionUsage(
                        version=version,
                        projects=sorted(
                            projects_by_version.values(),
                            key=lambda reference: (reference.path_with_namespace, reference.subproject_path),
                        ),
                    )
                    for version, projects_by_version in sorted(
                        versions.items(),
                        key=lambda item: (item[0] is None, item[0] or ''),
                    )
                ],
            ),
        )
    return sorted(catalog, key=lambda usage: (-usage.projects_count, usage.name))


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

import re
from collections import Counter
from dataclasses import dataclass
from urllib.parse import urlsplit

from gitlab_radar.database.repository import latest_published_scan
from gitlab_radar.schemas.dashboard import (
    CompanyRequirement,
    Dashboard,
    DataQualityStatistics,
    DependencyCountStatistics,
    DependencyStatistics,
    LastScanStatistics,
    PackageManagerStatistics,
    PythonVersionStatistics,
    TechnologyTarget,
    TechnologyUsage,
)
from gitlab_radar.schemas.dependency import DependencyLevel
from gitlab_radar.schemas.project import Project
from gitlab_radar.schemas.technology import PackageManager
from gitlab_radar.services.application_parameters import application_parameter_values
from gitlab_radar.services.company_rules import load_company_requirements
from gitlab_radar.services.dependency import build_dependency_catalog
from gitlab_radar.services.project import load_projects

PACKAGE_MANAGER_TITLES = {
    PackageManager.UV: 'uv',
    PackageManager.PIP: 'pip',
    PackageManager.POETRY: 'Poetry',
    PackageManager.MIXED: 'Смешанный',
    PackageManager.UNKNOWN: 'Не определен',
}


@dataclass(slots=True)
class _DashboardCache:
    scan_id: int | None = None
    value: Dashboard | None = None


_DASHBOARD_CACHE = _DashboardCache()


def invalidate_dashboard_cache() -> None:
    _DASHBOARD_CACHE.scan_id = None
    _DASHBOARD_CACHE.value = None


async def build_dashboard() -> Dashboard:
    scan = await latest_published_scan()
    if scan is not None and _DASHBOARD_CACHE.scan_id == scan.id and _DASHBOARD_CACHE.value is not None:
        return _DASHBOARD_CACHE.value.model_copy(deep=True)

    projects = await load_projects()
    requirements = await load_company_requirements()
    parameter_values = await application_parameter_values()
    oldest_current_python = tuple(
        map(int, parameter_values['python_oldest_current_version'].split('.')),
    )
    total_projects = len(projects)
    subprojects = [subproject for project in projects for subproject in project.subprojects]
    dependency_catalog = await build_dependency_catalog(projects)
    rule_matches = Counter(
        code for project in projects for code, matches in project.company_rule_results.items() if matches
    )
    python_versions = _python_versions(projects)
    image_statistics, registry_statistics = _registry_statistics(projects)

    dashboard = Dashboard(
        projects_count=total_projects,
        docker_projects_count=sum(project.has_docker for project in projects),
        gitlab_ci_projects_count=sum(project.has_gitlab_ci for project in projects),
        fastapi_projects_count=sum(_project_uses_dependency(project, 'fastapi') for project in projects),
        django_projects_count=sum(_project_uses_dependency(project, 'django') for project in projects),
        package_managers=_package_manager_statistics(projects, subprojects),
        dependency_counts=_dependency_count_statistics(dependency_catalog),
        python_versions=[
            PythonVersionStatistics(version=version, projects_count=count)
            for version, count in sorted(
                python_versions.items(),
                key=lambda item: tuple(int(part) for part in item[0].split('.')),
                reverse=True,
            )
        ],
        top_dependencies=_top_dependencies(projects),
        company_requirements=[
            CompanyRequirement(
                code=rule.code,
                title=rule.title,
                description=rule.description,
                matching_projects=rule_matches[rule.code],
                total_projects=total_projects,
                compliance_percentage=_percentage(rule_matches[rule.code], total_projects),
            )
            for rule in requirements
        ],
        technology_target=TechnologyTarget(
            python_versions=[
                TechnologyUsage(name=f'Python {version}', projects_count=count)
                for version, count in python_versions.most_common()
            ]
            + [
                TechnologyUsage(
                    name='Python LTS',
                    projects_count=sum(
                        count
                        for version, count in python_versions.items()
                        if tuple(map(int, version.split('.'))) >= oldest_current_python
                    ),
                ),
            ],
            dependencies=[
                TechnologyUsage(name=dependency.name, projects_count=dependency.projects_count)
                for dependency in dependency_catalog
                if dependency.level is not DependencyLevel.TRANSITIVE
            ],
            images=image_statistics,
            registries=registry_statistics,
        ),
        registries=registry_statistics,
        subprojects_count=sum(max(len(project.subprojects) - 1, 0) for project in projects),
        data_quality=DataQualityStatistics(
            unknown_package_manager=sum(
                subproject.package_manager is PackageManager.UNKNOWN for subproject in subprojects
            ),
            unknown_python_version=sum(
                not (subproject.python_version or subproject.python_constraint) for subproject in subprojects
            ),
            projects_without_subprojects=sum(not project.subprojects for project in projects),
            analysis_errors=sum(bool(project.scan_error) for project in projects),
        ),
        last_scan=(
            LastScanStatistics(
                completed_at=scan.completed_at.isoformat() if scan.completed_at else None,
                duration_seconds=round((scan.completed_at - scan.started_at).total_seconds(), 1)
                if scan.completed_at
                else 0.0,
                errors_count=len(scan.errors),
                reused_projects=scan.reused_projects,
                skipped_projects=scan.skipped_projects,
                gitlab_requests=scan.gitlab_requests,
            )
            if scan
            else None
        ),
    )
    if scan is not None:
        _DASHBOARD_CACHE.scan_id = scan.id
        _DASHBOARD_CACHE.value = dashboard
    return dashboard.model_copy(deep=True)


def _package_manager_statistics(
    projects: list[Project],
    subprojects: list,
) -> list[PackageManagerStatistics]:
    subproject_managers = Counter(subproject.package_manager for subproject in subprojects)
    projects_by_manager = Counter(
        (project.package_manager or PackageManager.UNKNOWN) if project.subprojects else PackageManager.UNKNOWN
        for project in projects
    )
    return [
        PackageManagerStatistics(
            package_manager=package_manager,
            title=title,
            projects_count=projects_by_manager[package_manager],
            subprojects_count=subproject_managers[package_manager],
            percentage=_percentage(projects_by_manager[package_manager], len(projects)),
        )
        for package_manager, title in PACKAGE_MANAGER_TITLES.items()
    ]


def _dependency_count_statistics(
    dependency_catalog: list,
) -> DependencyCountStatistics:
    names = {
        level: {dependency.name for dependency in dependency_catalog if dependency.level is level}
        for level in DependencyLevel
    }
    direct = names[DependencyLevel.DIRECT]
    optional = names[DependencyLevel.OPTIONAL] - direct
    transitive = names[DependencyLevel.TRANSITIVE] - direct - optional
    return DependencyCountStatistics(
        total=len(direct | optional | transitive),
        direct=len(direct),
        optional=len(optional),
        transitive=len(transitive),
    )


def _python_versions(projects: list[Project]) -> Counter[str]:
    versions: Counter[str] = Counter()
    for project in projects:
        project_versions = {
            _normalize_python_version(subproject.python_version or subproject.python_constraint)
            for subproject in project.subprojects
        }
        versions.update(version for version in project_versions if version)
    return versions


def _registry_statistics(
    projects: list[Project],
) -> tuple[list[TechnologyUsage], list[TechnologyUsage]]:
    image_projects: dict[str, set[int]] = {}
    registry_projects: dict[str, set[int]] = {}
    for project in projects:
        for image in project.container_images:
            image_projects.setdefault(f'{image.registry}/{image.image}', set()).add(project.id)
            registry_projects.setdefault(_registry_name(image.registry), set()).add(project.id)
        for registry in project.package_registries:
            registry_projects.setdefault(_registry_name(registry), set()).add(project.id)
    return _technology_usage(image_projects), _technology_usage(registry_projects)


def _normalize_python_version(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r'(?<!\d)(\d+)\.(\d+)', value)
    return '.'.join(match.groups()) if match else None


def _percentage(value: int, total: int) -> float:
    if not total:
        return 0.0
    return round(value / total * 100, 1)


def _project_uses_dependency(project: Project, dependency_name: str) -> bool:
    return any(
        dependency.name == dependency_name
        for subproject in project.subprojects
        for dependency in (
            subproject.dependencies
            + [dependency for group in subproject.optional_dependencies for dependency in group.dependencies]
        )
    )


def _top_dependencies(projects: list[Project]) -> list[DependencyStatistics]:
    projects_by_dependency: dict[str, set[int]] = {}
    for project in projects:
        for subproject in project.subprojects:
            dependencies = subproject.dependencies + [
                dependency for group in subproject.optional_dependencies for dependency in group.dependencies
            ]
            for dependency in dependencies:
                projects_by_dependency.setdefault(dependency.name, set()).add(project.id)
    return [
        DependencyStatistics(name=name, projects_count=len(project_ids))
        for name, project_ids in sorted(
            projects_by_dependency.items(),
            key=lambda item: (-len(item[1]), item[0]),
        )[:10]
    ]


def _technology_usage(projects_by_name: dict[str, set[int]]) -> list[TechnologyUsage]:
    return [
        TechnologyUsage(name=name, projects_count=len(project_ids))
        for name, project_ids in sorted(
            projects_by_name.items(),
            key=lambda item: (-len(item[1]), item[0]),
        )
    ]


def _registry_name(value: str) -> str:
    parsed = urlsplit(value if '://' in value else f'//{value}')
    return str(parsed.netloc or value.partition('/')[0]).lower()

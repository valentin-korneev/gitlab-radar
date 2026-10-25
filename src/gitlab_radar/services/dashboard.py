import re
from collections import Counter
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
from gitlab_radar.services.company_rules import COMPANY_RULES, project_rule_results
from gitlab_radar.services.dependency import build_dependency_catalog
from gitlab_radar.services.project import load_projects

PACKAGE_MANAGER_TITLES = {
    PackageManager.UV: 'uv',
    PackageManager.POETRY: 'Poetry',
    PackageManager.PIP: 'pip',
    PackageManager.UNKNOWN: 'Не определён',
}


async def build_dashboard() -> Dashboard:
    projects = await load_projects()
    scan = await latest_published_scan()
    total_projects = len(projects)
    subprojects = [subproject for project in projects for subproject in project.subprojects]
    subproject_managers = Counter(subproject.package_manager for subproject in subprojects)
    projects_by_manager = Counter(
        (project.package_manager or PackageManager.UNKNOWN)
        if project.subprojects
        else PackageManager.UNKNOWN
        for project in projects
    )
    dependency_catalog = await build_dependency_catalog(projects)
    rule_matches = Counter(
        code
        for project in projects
        for code, matches in project_rule_results(project).items()
        if matches
    )
    dependency_names = {
        level: {dependency.name for dependency in dependency_catalog if dependency.level is level}
        for level in DependencyLevel
    }
    direct_names = dependency_names[DependencyLevel.DIRECT]
    optional_names = dependency_names[DependencyLevel.OPTIONAL] - direct_names
    transitive_names = dependency_names[DependencyLevel.TRANSITIVE] - direct_names - optional_names
    python_versions: Counter[str] = Counter()
    for project in projects:
        project_versions = {
            _normalize_python_version(subproject.python_version or subproject.python_constraint)
            for subproject in project.subprojects
        }
        python_versions.update(version for version in project_versions if version)

    image_projects: dict[str, set[int]] = {}
    registry_projects: dict[str, set[int]] = {}
    for project in projects:
        for image in project.container_images:
            image_projects.setdefault(f'{image.registry}/{image.image}', set()).add(project.id)
            registry_projects.setdefault(_registry_name(image.registry), set()).add(project.id)
        for registry in project.package_registries:
            registry_projects.setdefault(_registry_name(registry), set()).add(project.id)

    registry_statistics = _technology_usage(registry_projects)

    return Dashboard(
        projects_count=total_projects,
        docker_projects_count=sum(project.has_docker for project in projects),
        gitlab_ci_projects_count=sum(project.has_gitlab_ci for project in projects),
        fastapi_projects_count=sum(_project_uses_dependency(project, 'fastapi') for project in projects),
        django_projects_count=sum(_project_uses_dependency(project, 'django') for project in projects),
        package_managers=[
            PackageManagerStatistics(
                package_manager=package_manager,
                title=title,
                projects_count=projects_by_manager[package_manager],
                subprojects_count=subproject_managers[package_manager],
                percentage=_percentage(projects_by_manager[package_manager], total_projects),
            )
            for package_manager, title in PACKAGE_MANAGER_TITLES.items()
        ],
        dependency_counts=DependencyCountStatistics(
            total=len(direct_names | optional_names | transitive_names),
            direct=len(direct_names),
            optional=len(optional_names),
            transitive=len(transitive_names),
        ),
        python_versions=[
            PythonVersionStatistics(version=version, projects_count=count)
            for version, count in sorted(
                python_versions.items(),
                key=lambda item: tuple(int(part) for part in item[0].split('.')),
                reverse=True,
            )
        ],
        top_dependencies=[
            DependencyStatistics(name=dependency.name, projects_count=dependency.projects_count)
            for dependency in dependency_catalog
            if dependency.level is not DependencyLevel.TRANSITIVE
        ][:10],
        company_requirements=[
            CompanyRequirement(
                code=rule.code,
                title=rule.title,
                description=rule.description,
                matching_projects=rule_matches[rule.code],
                total_projects=total_projects,
                compliance_percentage=_percentage(rule_matches[rule.code], total_projects),
            )
            for rule in COMPANY_RULES
        ],
        technology_target=TechnologyTarget(
            python_versions=[
                TechnologyUsage(name=f'Python {version}', projects_count=count)
                for version, count in python_versions.most_common()
            ],
            dependencies=[
                TechnologyUsage(name=dependency.name, projects_count=dependency.projects_count)
                for dependency in dependency_catalog
                if dependency.level is not DependencyLevel.TRANSITIVE
            ],
            images=_technology_usage(image_projects),
            registries=registry_statistics,
        ),
        registries=registry_statistics,
        subprojects_count=sum(max(len(project.subprojects) - 1, 0) for project in projects),
        data_quality=DataQualityStatistics(
            unknown_package_manager=sum(
                subproject.package_manager is PackageManager.UNKNOWN for subproject in subprojects
            ),
            unknown_python_version=sum(
                not (subproject.python_version or subproject.python_constraint)
                for subproject in subprojects
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
            + [
                dependency
                for group in subproject.optional_dependencies
                for dependency in group.dependencies
            ]
        )
    )


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

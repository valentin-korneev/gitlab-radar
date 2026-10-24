import re
from collections import Counter

from gitlab_radar.schemas.dashboard import (
    CompanyRequirement,
    Dashboard,
    DependencyCountStatistics,
    DependencyStatistics,
    PackageManagerStatistics,
    PythonVersionStatistics,
)
from gitlab_radar.schemas.dependency import DependencyLevel
from gitlab_radar.schemas.technology import PackageManager
from gitlab_radar.services.company_rules import COMPANY_RULES, project_rule_results
from gitlab_radar.services.dependency import build_dependency_catalog
from gitlab_radar.services.project import load_projects

PACKAGE_MANAGER_TITLES = {
    PackageManager.UV: 'uv',
    PackageManager.POETRY: 'Poetry',
    PackageManager.PIP: 'pip',
    PackageManager.PIPENV: 'Pipenv',
    PackageManager.CONDA: 'Conda',
    PackageManager.UNKNOWN: 'Не определён',
}


def build_dashboard() -> Dashboard:
    projects = load_projects()
    total_projects = len(projects)
    package_managers = Counter(project.package_manager or PackageManager.UNKNOWN for project in projects)
    dependency_catalog = build_dependency_catalog(projects)
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
            _normalize_python_version(subproject.python_version)
            for subproject in project.subprojects
        }
        python_versions.update(version for version in project_versions if version)

    return Dashboard(
        projects_count=total_projects,
        docker_projects_count=sum(project.has_docker for project in projects),
        gitlab_ci_projects_count=sum(project.has_gitlab_ci for project in projects),
        package_managers=[
            PackageManagerStatistics(
                package_manager=package_manager,
                title=title,
                projects_count=package_managers[package_manager],
                percentage=_percentage(package_managers[package_manager], total_projects),
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
            for version, count in sorted(python_versions.items(), key=lambda item: item[0], reverse=True)
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

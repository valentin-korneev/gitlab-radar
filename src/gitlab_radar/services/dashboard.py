from collections import Counter

from gitlab_radar.schemas.dashboard import (
    CompanyRequirement,
    Dashboard,
    DependencyStatistics,
    PackageManagerStatistics,
)
from gitlab_radar.schemas.technology import PackageManager
from gitlab_radar.services.dependency import build_dependency_catalog, project_dependency_names
from gitlab_radar.services.project import load_projects

PACKAGE_MANAGER_TITLES = {
    PackageManager.UV: 'uv',
    PackageManager.POETRY: 'Poetry',
    PackageManager.PIP: 'pip',
    PackageManager.PIPENV: 'Pipenv',
    PackageManager.CONDA: 'Conda',
    PackageManager.UNKNOWN: 'Не определён',
}
COMPANY_DEPENDENCIES = {
    'ruff-required': ('ruff обязателен', 'Проект использует ruff.', 'ruff'),
    'bandit-required': ('bandit обязателен', 'Проект использует bandit.', 'bandit'),
    'pylint-required': ('pylint обязателен', 'Проект использует pylint.', 'pylint'),
}


def build_dashboard() -> Dashboard:
    projects = load_projects()
    total_projects = len(projects)
    package_managers = Counter(project.package_manager or PackageManager.UNKNOWN for project in projects)
    dependency_catalog = build_dependency_catalog(projects)
    dependency_projects = {
        dependency: sum(dependency in project_dependency_names(project) for project in projects)
        for _, _, dependency in COMPANY_DEPENDENCIES.values()
    }

    return Dashboard(
        projects_count=total_projects,
        package_managers=[
            PackageManagerStatistics(
                package_manager=package_manager,
                title=title,
                projects_count=package_managers[package_manager],
                percentage=_percentage(package_managers[package_manager], total_projects),
            )
            for package_manager, title in PACKAGE_MANAGER_TITLES.items()
        ],
        top_dependencies=[
            DependencyStatistics(name=dependency.name, projects_count=dependency.projects_count)
            for dependency in dependency_catalog[:10]
        ],
        company_requirements=[
            CompanyRequirement(
                code='uv-required',
                title='uv обязателен',
                description='Проект использует uv как пакетный менеджер.',
                matching_projects=package_managers[PackageManager.UV],
                total_projects=total_projects,
                compliance_percentage=_percentage(package_managers[PackageManager.UV], total_projects),
            ),
            *[
                CompanyRequirement(
                    code=code,
                    title=title,
                    description=description,
                    matching_projects=dependency_projects[dependency],
                    total_projects=total_projects,
                    compliance_percentage=_percentage(dependency_projects[dependency], total_projects),
                )
                for code, (title, description, dependency) in COMPANY_DEPENDENCIES.items()
            ],
        ],
    )


def _percentage(value: int, total: int) -> float:
    if not total:
        return 0.0
    return round(value / total * 100, 1)

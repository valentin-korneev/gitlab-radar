from collections import Counter

from gitlab_radar.schemas.dashboard import CompanyRequirement, Dashboard, PackageManagerStatistics
from gitlab_radar.schemas.technology import PackageManager
from gitlab_radar.services.project import load_projects

PACKAGE_MANAGER_TITLES = {
    PackageManager.UV: 'uv',
    PackageManager.POETRY: 'Poetry',
    PackageManager.PIP: 'pip',
    PackageManager.UNKNOWN: 'Не определён',
}


def build_dashboard() -> Dashboard:
    projects = load_projects()
    total_projects = len(projects)
    package_managers = Counter(project.package_manager or PackageManager.UNKNOWN for project in projects)

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
        company_requirements=[
            CompanyRequirement(
                code='uv-required',
                title='uv обязателен',
                description='Проект использует uv как пакетный менеджер.',
                matching_projects=package_managers[PackageManager.UV],
                total_projects=total_projects,
                compliance_percentage=_percentage(package_managers[PackageManager.UV], total_projects),
            ),
        ],
    )


def _percentage(value: int, total: int) -> float:
    if not total:
        return 0.0
    return round(value / total * 100, 1)

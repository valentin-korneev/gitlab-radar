import logging

from gitlab.const import AccessLevel

from gitlab_radar.clients.gitlab import gitlab_client
from gitlab_radar.database.repository import load_projects as load_projects_from_database
from gitlab_radar.schemas.project import Project
from gitlab_radar.services.visibility import filter_projects_for_user

logger = logging.getLogger(__name__)


def fetch_projects() -> tuple[list[Project], int]:
    logger.info('Запрос доступных Python-проектов из GitLab')
    gitlab_projects = gitlab_client.projects.list(
        min_access_level=AccessLevel.REPORTER,
        with_programming_language='python',
        archived=False,
        iterator=True,
        per_page=100,
    )
    projects: list[Project] = []
    skipped_projects = 0
    for gitlab_project in gitlab_projects:
        project_data = gitlab_project.asdict()
        if not project_data.get('default_branch'):
            skipped_projects += 1
            logger.info(
                'Проект %s пропущен: основная ветка отсутствует',
                project_data.get('path_with_namespace', project_data.get('id')),
            )
            continue
        project_data['gitlab_access_level'] = _project_access_level(project_data.get('permissions'))
        projects.append(Project.model_validate(project_data))
    logger.info(
        'Получено проектов для сканирования: %d; пропущено без основной ветки: %d',
        len(projects),
        skipped_projects,
    )
    return projects, skipped_projects


async def load_projects(
    preferred_username: str | None = None,
    visibility_group: str | None = None,
) -> list[Project]:
    projects = await load_projects_from_database()
    return await filter_projects_for_user(projects, preferred_username, visibility_group)


def _project_access_level(permissions: object) -> int:
    if not isinstance(permissions, dict):
        return 0
    levels = []
    for key in ('project_access', 'group_access'):
        access = permissions.get(key)
        if isinstance(access, dict) and isinstance(access.get('access_level'), int):
            levels.append(access['access_level'])
    return max(levels, default=0)

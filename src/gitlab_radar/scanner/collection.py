import logging

from gitlab.const import AccessLevel

from gitlab_radar.clients.gitlab import ScanGitLab
from gitlab_radar.config import settings
from gitlab_radar.schemas.project import Project
from gitlab_radar.services.project_blacklist import project_is_blacklisted

logger = logging.getLogger(__name__)


def fetch_projects(
    client: ScanGitLab, blacklist: tuple[str, ...] = (), project_ids: list[int] | None = None
) -> tuple[list[Project], int]:
    logger.info('Запрос проектов из GitLab: %s', project_ids if project_ids is not None else 'все доступные')
    common_parameters = {
        'active': True,
        'iterator': settings.gitlab.projects_iterator,
        'per_page': 50,
    }
    project_queries = (
        {'min_access_level': AccessLevel.REPORTER},
        {'visibility': 'public'},
    )
    projects: list[Project] = []
    seen_project_ids: set[int] = set()
    skipped_projects = 0
    queries = (
        ((client.projects.get(project_id) for project_id in project_ids),)
        if project_ids is not None
        else (client.projects.list(**query_parameters, **common_parameters) for query_parameters in project_queries)
    )
    for gitlab_projects in queries:
        for gitlab_project in gitlab_projects:
            client.signal.check()
            project_data = gitlab_project.asdict()
            if project_ids is not None and (
                project_data.get('archived')
                or (
                    project_data.get('visibility') != 'public'
                    and _project_access_level(project_data.get('permissions')) < AccessLevel.REPORTER
                )
            ):
                skipped_projects += 1
                continue
            project_id = int(project_data['id'])
            if project_id in seen_project_ids:
                continue
            seen_project_ids.add(project_id)
            path_with_namespace = str(project_data.get('path_with_namespace') or '')
            if project_is_blacklisted(path_with_namespace, blacklist):
                skipped_projects += 1
                logger.info('Проект %s пропущен по черному списку', path_with_namespace or project_id)
                continue
            if not project_data.get('default_branch'):
                skipped_projects += 1
                logger.info(
                    'Проект %s пропущен: основная ветка отсутствует',
                    project_data.get('path_with_namespace', project_id),
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


def _project_access_level(permissions: object) -> int:
    if not isinstance(permissions, dict):
        return 0
    levels = []
    for key in ('project_access', 'group_access'):
        access = permissions.get(key)
        if isinstance(access, dict) and isinstance(access.get('access_level'), int):
            levels.append(access['access_level'])
    return max(levels, default=0)

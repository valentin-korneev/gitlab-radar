import json
import logging
import shutil
from threading import Lock
lazy from pathlib import Path

from gitlab.const import AccessLevel

from gitlab_radar.clients.gitlab import gitlab_client
from gitlab_radar.config import settings
from gitlab_radar.schemas.project import Project
from gitlab_radar.services.package_files import PackageFilesService

logger = logging.getLogger(__name__)


PROJECTS_FILENAME = 'projects.json'
PROJECTS_DIRECTORY = 'projects'
STAGING_DIRECTORY = '.scan-staging'
BACKUP_DIRECTORY = '.projects.backup'
BACKUP_FILENAME = '.projects.json.backup'

_snapshot_lock = Lock()


def refresh_projects() -> tuple[list[Project], list[str]]:
    logger.info('Запрос доступных Python-проектов из GitLab')
    gitlab_projects = gitlab_client.projects.list(
        min_access_level=AccessLevel.REPORTER,
        with_programming_language='python',
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
        projects.append(Project.model_validate(project_data))
    logger.info(
        'Получено проектов для сканирования: %d; пропущено без основной ветки: %d',
        len(projects),
        skipped_projects,
    )

    data_directory = settings.application.data_dir
    staging_directory = data_directory / STAGING_DIRECTORY
    _remove_path(staging_directory)
    projects_directory = staging_directory / PROJECTS_DIRECTORY
    projects_directory.mkdir(parents=True)
    logger.info('Создана временная директория снимка: %s', staging_directory)

    try:
        errors = PackageFilesService(projects_directory).scan_projects(projects)
        _write_projects(staging_directory / PROJECTS_FILENAME, projects)
        logger.info('Подготовлен новый снимок: проектов %d, ошибок %d', len(projects), len(errors))
        _replace_snapshot(staging_directory)
    finally:
        _remove_path(staging_directory)
        logger.info('Временная директория снимка очищена: %s', staging_directory)

    return projects, errors


def load_projects() -> list[Project]:
    projects_path = settings.application.data_dir / PROJECTS_FILENAME
    with _snapshot_lock:
        if not projects_path.exists():
            logger.info('Файл проектов ещё не создан: %s', projects_path)
            return []
        with projects_path.open(encoding='utf-8') as file:
            projects = [Project.model_validate(project) for project in json.load(file)]
    logger.info('Загружено проектов из файла: %d', len(projects))
    return projects


def _write_projects(path: Path, projects: list[Project]) -> None:
    with path.open('w', encoding='utf-8') as file:
        json.dump(
            [project.model_dump(mode='json') for project in projects],
            file,
            ensure_ascii=False,
            indent=4,
        )
    logger.info('Список проектов записан: %s', path)


def _replace_snapshot(staging_directory: Path) -> None:
    data_directory = settings.application.data_dir
    projects_directory = data_directory / PROJECTS_DIRECTORY
    projects_path = data_directory / PROJECTS_FILENAME
    backup_directory = data_directory / BACKUP_DIRECTORY
    backup_path = data_directory / BACKUP_FILENAME

    with _snapshot_lock:
        logger.info('Публикация нового снимка проектов')
        _remove_path(backup_directory)
        _remove_path(backup_path)
        try:
            if projects_directory.exists():
                projects_directory.replace(backup_directory)
                logger.info('Текущая директория проектов перемещена в резервную')
            if projects_path.exists():
                projects_path.replace(backup_path)
                logger.info('Текущий список проектов перемещён в резервный')
            (staging_directory / PROJECTS_DIRECTORY).replace(projects_directory)
            (staging_directory / PROJECTS_FILENAME).replace(projects_path)
        except Exception:
            logger.exception('Публикация снимка не удалась; выполняется восстановление')
            _remove_path(projects_directory)
            _remove_path(projects_path)
            if backup_directory.exists():
                backup_directory.replace(projects_directory)
            if backup_path.exists():
                backup_path.replace(projects_path)
            raise
        _remove_path(backup_directory)
        _remove_path(backup_path)

    logger.info('Снимок проектов опубликован: %s', data_directory)


def _remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)

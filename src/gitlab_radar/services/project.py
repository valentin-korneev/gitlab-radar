import json
import logging

from gitlab.const import AccessLevel

from gitlab_radar.clients.gitlab import gitlab_client
from gitlab_radar.config import settings
from gitlab_radar.schemas.project import Project

logger = logging.getLogger(__name__)


class ProjectService:
    def __init__(self) -> None:
        self.projects: list[Project] = []

    def refresh_projects(self) -> list[Project]:
        logger.info('Получение списка проектов из GitLab')
        gitlab_projects = gitlab_client.projects.list(
            min_access_level=AccessLevel.REPORTER,
            with_programming_language='python',
            get_all=True,
            iterator=True,
            per_page=100,
        )
        self.projects = [Project.model_validate(project.asdict()) for project in gitlab_projects]
        logger.info('Получено проектов: %d', len(self.projects))
        self.save_projects()
        return self.projects

    def save_projects(self) -> None:
        projects_path = settings.application.base_dir / 'data' / 'projects.json'
        projects_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = projects_path.with_suffix('.json.tmp')
        with temporary_path.open('w', encoding='utf-8') as file:
            json.dump(
                [project.model_dump(mode='json') for project in self.projects],
                file,
                ensure_ascii=False,
                indent=4,
            )
        temporary_path.replace(projects_path)
        logger.info('Проекты сохранены в %s', projects_path)

    def load_projects(self) -> None:
        projects_path = settings.application.base_dir / 'data' / 'projects.json'
        if not projects_path.exists():
            logger.info('Файл проектов ещё не создан: %s', projects_path)
            self.projects = []
            return
        with projects_path.open(encoding='utf-8') as file:
            self.projects = [Project.model_validate(project) for project in json.load(file)]
        logger.info('Загружено проектов из файла: %d', len(self.projects))

    def get_projects(self) -> list[Project]:
        self.load_projects()
        return self.projects

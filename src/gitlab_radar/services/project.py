import json

from gitlab.const import AccessLevel

from gitlab_radar.clients.gitlab import gitlab_client
from gitlab_radar.config import settings


class ProjectService:
    def __init__(self) -> None:
        self.projects = []

    def refresh_projects(self) -> None:
        self.projects = gitlab_client.projects.list(
            min_access_level=AccessLevel.REPORTER,
            with_programming_language='python',
            get_all=True,
            per_page=100,
        )
        self.save_projects()

    def save_projects(self) -> None:
        with open(settings.application.base_dir / 'data' / 'projects.json', 'w') as f:
            json.dump([p.asdict() for p in self.projects], f, indent=4)

    def load_projects(self) -> None:
        with open(settings.application.base_dir / 'data' / 'projects.json') as f:
            self.projects = json.load(f)

    def get_projects(self) -> list:
        self.load_projects()
        return self.projects

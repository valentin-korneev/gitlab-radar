from pydantic_settings import BaseSettings

from gitlab_radar.config.application import ApplicationSettings
from gitlab_radar.config.auth import AuthSettings
from gitlab_radar.config.database import DatabaseSettings
from gitlab_radar.config.gitlab import GitLabSettings


class Settings(BaseSettings):
    application: ApplicationSettings = ApplicationSettings()
    auth: AuthSettings = AuthSettings()
    database: DatabaseSettings = DatabaseSettings()
    gitlab: GitLabSettings = GitLabSettings()


settings = Settings()

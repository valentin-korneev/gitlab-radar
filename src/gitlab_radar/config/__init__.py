from pydantic_settings import BaseSettings

from gitlab_radar.config.application import ApplicationSettings
from gitlab_radar.config.gitlab import GitLabSettings


class Settings(BaseSettings):
    application: ApplicationSettings = ApplicationSettings()
    gitlab: GitLabSettings = GitLabSettings()


settings = Settings()

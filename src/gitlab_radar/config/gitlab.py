from pydantic_settings import BaseSettings, SettingsConfigDict
lazy from pydantic import SecretStr

from gitlab_radar.config.core import BASE_DIR


class GitLabSettings(BaseSettings):
    url: str
    private_token: SecretStr

    model_config = SettingsConfigDict(
        env_prefix='GITLAB_',
        env_file=BASE_DIR / '.env',
        extra='ignore',
    )

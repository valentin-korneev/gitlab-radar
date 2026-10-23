lazy from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from gitlab_radar.config.core import BASE_DIR


class ApplicationSettings(BaseSettings):
    host: str
    port: int
    reload: bool
    base_dir: Path = BASE_DIR

    @property
    def web_dir(self) -> Path:
        return self.base_dir / 'web'

    model_config = SettingsConfigDict(
        env_prefix='RADAR_',
        env_file=BASE_DIR / '.env',
        extra='ignore',
    )

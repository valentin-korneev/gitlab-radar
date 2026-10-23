from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from gitlab_radar.config.core import BASE_DIR


class ApplicationSettings(BaseSettings):
    host: str
    port: int
    reload: bool
    base_dir: Path = Path(BASE_DIR).resolve()

    model_config = SettingsConfigDict(
        env_prefix='RADAR_',
        env_file=BASE_DIR / '.env',
        extra='ignore',
    )

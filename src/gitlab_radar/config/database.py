from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from gitlab_radar.config.core import BASE_DIR


class DatabaseSettings(BaseSettings):
    host: str = Field(validation_alias='POSTGRES_HOST')
    port: int = Field(validation_alias='POSTGRES_PORT')
    database: str = Field(validation_alias='POSTGRES_DB')
    user: str = Field(validation_alias='RADAR_DB_USER')
    password: SecretStr = Field(validation_alias='RADAR_DB_PASSWORD')
    schema_name: str = Field(validation_alias='RADAR_DB_SCHEMA', pattern=r'^[A-Za-z_][A-Za-z0-9_]*$')

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / '.env',
        extra='ignore',
    )

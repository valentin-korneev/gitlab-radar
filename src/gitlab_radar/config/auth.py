from pydantic_settings import BaseSettings, SettingsConfigDict
lazy from pydantic import AnyHttpUrl

from gitlab_radar.config.core import BASE_DIR


class AuthSettings(BaseSettings):
    public_url: AnyHttpUrl
    internal_url: AnyHttpUrl
    realm: str
    client_id: str

    @property
    def issuer(self) -> str:
        return f'{str(self.public_url).rstrip("/")}/realms/{self.realm}'

    @property
    def jwks_url(self) -> str:
        return f'{str(self.internal_url).rstrip("/")}/realms/{self.realm}/protocol/openid-connect/certs'

    model_config = SettingsConfigDict(
        env_prefix='RADAR_AUTH_',
        env_file=BASE_DIR / '.env',
        extra='ignore',
    )

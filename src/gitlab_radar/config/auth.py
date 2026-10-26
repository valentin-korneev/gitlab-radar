from pydantic import AnyHttpUrl, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from gitlab_radar.config.core import BASE_DIR


class KeycloakNotConfiguredError(RuntimeError):
    pass


class AuthSettings(BaseSettings):
    required: bool = False
    public_url: AnyHttpUrl | None = None
    internal_url: AnyHttpUrl | None = None
    realm: str | None = None
    client_id: str | None = None
    preferred_usernames: str = ''

    @model_validator(mode='after')
    def validate_keycloak_settings(self) -> AuthSettings:
        if self.required and not all((self.public_url, self.internal_url, self.realm, self.client_id)):
            msg = 'Для обязательной авторизации необходимо настроить Keycloak'
            raise ValueError(msg)
        if self.required and not self.allowed_preferred_usernames:
            msg = 'Для обязательной авторизации нужен хотя бы один администратор'
            raise ValueError(msg)
        return self

    @property
    def allowed_preferred_usernames(self) -> set[str]:
        return {value.strip() for value in self.preferred_usernames.split(',') if value.strip()}

    @property
    def issuer(self) -> str:
        if self.public_url is None or self.realm is None:
            raise KeycloakNotConfiguredError
        return f'{str(self.public_url).rstrip("/")}/realms/{self.realm}'

    @property
    def jwks_url(self) -> str:
        if self.internal_url is None or self.realm is None:
            raise KeycloakNotConfiguredError
        return f'{str(self.internal_url).rstrip("/")}/realms/{self.realm}/protocol/openid-connect/certs'

    model_config = SettingsConfigDict(
        env_prefix='RADAR_AUTH_',
        env_file=BASE_DIR / '.env',
        extra='ignore',
    )

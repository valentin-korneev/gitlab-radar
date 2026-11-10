from pydantic import AnyHttpUrl, Field, model_validator
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
    client_secret: str | None = Field(default=None, repr=False)
    session_secret: str | None = Field(default=None, repr=False)
    preferred_usernames: str = ''
    development_username: str = 'local-admin'

    @model_validator(mode='after')
    def validate_keycloak_settings(self) -> AuthSettings:
        if self.required and not all((
            self.public_url, self.internal_url, self.realm, self.client_id,
            self.client_secret, self.session_secret,
        )):
            msg = 'Для обязательной авторизации необходимы настройки Keycloak, client secret и session secret'
            raise ValueError(msg)
        if self.required and not self.allowed_preferred_usernames:
            msg = 'Для обязательной авторизации нужен хотя бы один администратор'
            raise ValueError(msg)
        if self.required and len(self.session_secret or '') < 32:
            msg = 'RADAR_AUTH_SESSION_SECRET должен содержать не менее 32 символов'
            raise ValueError(msg)
        if not self.development_username.strip():
            msg = 'Имя локального тестового пользователя не может быть пустым'
            raise ValueError(msg)
        if len(self.development_username.strip()) > 255:
            msg = 'Имя локального тестового пользователя не может быть длиннее 255 символов'
            raise ValueError(msg)
        self.development_username = self.development_username.strip()
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

    @property
    def token_url(self) -> str:
        return f'{self.issuer}/protocol/openid-connect/token'

    @property
    def authorization_url(self) -> str:
        return f'{self.issuer}/protocol/openid-connect/auth'

    @property
    def logout_url(self) -> str:
        return f'{self.issuer}/protocol/openid-connect/logout'

    model_config = SettingsConfigDict(
        env_prefix='RADAR_AUTH_',
        env_file=BASE_DIR / '.env',
        extra='ignore',
    )

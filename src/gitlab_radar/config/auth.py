from urllib.parse import urlsplit

from pydantic import AnyHttpUrl, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from gitlab_radar.config.core import BASE_DIR


class AuthSettings(BaseSettings):
    issuer: AnyHttpUrl | None = None
    public_url: AnyHttpUrl | None = None
    internal_url: AnyHttpUrl
    realm: str | None = None
    client_id: str
    client_secret: SecretStr
    session_secret: SecretStr
    preferred_usernames: str = ''

    @model_validator(mode='after')
    def validate_auth_settings(self) -> AuthSettings:
        self.realm = self.realm.strip() if self.realm else None
        self.client_id = self.client_id.strip()
        if self.issuer is None and (self.public_url is None or self.realm is None):
            msg = 'Для авторизации необходимо настроить issuer или public_url вместе с realm'
            raise ValueError(msg)
        if not self.client_id:
            msg = 'Для авторизации необходимо настроить client_id'
            raise ValueError(msg)
        if not self.client_secret.get_secret_value().strip():
            msg = 'Для авторизации необходимо настроить client_secret'
            raise ValueError(msg)
        if not self.session_secret.get_secret_value().strip():
            msg = 'Для авторизации необходимо настроить session_secret'
            raise ValueError(msg)
        if not self.allowed_preferred_usernames:
            msg = 'Для авторизации нужен хотя бы один администратор'
            raise ValueError(msg)
        return self

    @property
    def normalized_issuer(self) -> str:
        if self.issuer is not None:
            return str(self.issuer).rstrip('/')
        if self.public_url is None or self.realm is None:
            raise RuntimeError
        return f'{str(self.public_url).rstrip("/")}/realms/{self.realm}'

    @property
    def internal_issuer(self) -> str:
        if self.issuer is not None:
            issuer_path = urlsplit(self.normalized_issuer).path.rstrip('/')
            internal_url = str(self.internal_url).rstrip('/')
            internal_path = urlsplit(internal_url).path.rstrip('/')
            if issuer_path and internal_path.endswith(issuer_path):
                return internal_url
            return f'{internal_url}{issuer_path}'
        if self.realm is None:
            raise RuntimeError
        return f'{str(self.internal_url).rstrip("/")}/realms/{self.realm}'

    @property
    def allowed_preferred_usernames(self) -> set[str]:
        return {value.strip() for value in self.preferred_usernames.split(',') if value.strip()}

    model_config = SettingsConfigDict(
        env_prefix='RADAR_AUTH_',
        env_file=BASE_DIR / '.env',
        extra='ignore',
    )

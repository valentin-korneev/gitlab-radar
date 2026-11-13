# Запуск и конфигурация

## Локальный запуск через Compose

Скопируйте [`.env.example`](../.env.example) в `.env` и укажите параметры GitLab, PostgreSQL и OIDC:

```dotenv
GITLAB_URL=https://gitlab.example.com
GITLAB_PRIVATE_TOKEN=<token>
GITLAB_PROJECTS_ITERATOR=true
RADAR_AUTH_CLIENT_ID=<client-id>
RADAR_AUTH_CLIENT_SECRET=<client-secret>
RADAR_AUTH_SESSION_SECRET=<random-secret>
RADAR_AUTH_PREFERRED_USERNAMES=<oidc-username>
```

Compose поднимает приложение и PostgreSQL; OIDC-провайдер должен быть доступен отдельно. Redirect URI
`http://127.0.0.1:8000/api/auth/callback` необходимо зарегистрировать у провайдера.
`GITLAB_PRIVATE_TOKEN` должен принадлежать пользователю с доступом к анализируемым проектам.
`GITLAB_PROJECTS_ITERATOR` по умолчанию равен `true` и включает постраничное получение всех проектов.
В dev-окружении его можно установить в `false`, чтобы обрабатывать только первую страницу и снизить нагрузку
на GitLab.

Запустите сервисы:

```shell
docker compose up -d --build
```

Приложение будет доступно по адресу `http://127.0.0.1:8000`.

## PostgreSQL в OpenShift

Администратор PostgreSQL должен создать роль и схему приложения. Для этого предназначен скрипт
[`deploy/postgres/create-radar.sql`](../deploy/postgres/create-radar.sql):

```shell
psql --host=<postgres-host> --dbname=<database> --username=<admin-user> \
  --set ON_ERROR_STOP=1 \
  --set radar_database=<database> \
  --set radar_user=<application-user> \
  --set radar_password=<password> \
  --set radar_schema=<application-schema> \
  --file deploy/postgres/create-radar.sql
```

Пользователь, пароль и схема должны совпадать с переменными контейнера `RADAR_DB_USER`,
`RADAR_DB_PASSWORD` и `RADAR_DB_SCHEMA`.

## Авторизация

OIDC-провайдер настраивается отдельно: [параметры провайдера и роли](access.md).

## Контейнер приложения

Secret:

```dotenv
GITLAB_PRIVATE_TOKEN=<token>
RADAR_DB_PASSWORD=<password>
RADAR_AUTH_CLIENT_SECRET=<client-secret>
RADAR_AUTH_SESSION_SECRET=<session-secret>
```

ConfigMap:

```dotenv
GITLAB_URL=https://gitlab.example.com
GITLAB_PROJECTS_ITERATOR=true
POSTGRES_HOST=<postgres-host>
POSTGRES_PORT=5432
POSTGRES_DB=<database>
RADAR_DB_USER=<application-user>
RADAR_DB_SCHEMA=<application-schema>
RADAR_HOST=0.0.0.0
RADAR_PORT=8000
RADAR_RELOAD=false
APP_PUBLIC_URL=https://<application-host>
RADAR_AUTH_PREFERRED_USERNAMES=user.one,user.two
RADAR_AUTH_ISSUER=https://<oidc-provider>/<optional-path>
RADAR_AUTH_INTERNAL_URL=https://<oidc-provider-internal-address>
RADAR_AUTH_CLIENT_ID=<client-id>
```

`RADAR_AUTH_ISSUER` должен точно совпадать с claim `iss` токена. Вместо него для Keycloak можно передать
`RADAR_AUTH_PUBLIC_URL` и `RADAR_AUTH_REALM`; тогда issuer формируется как
`RADAR_AUTH_PUBLIC_URL/realms/RADAR_AUTH_REALM`. `RADAR_AUTH_INTERNAL_URL` используется backend для
discovery, token endpoint и JWKS.
Секрет сессий сохраняйте между перезапусками. `POSTGRES_USER` и `POSTGRES_PASSWORD`
контейнеру приложения не нужны.

Для ручного применения миграций:

```shell
uv run --no-sync tortoise migrate
```

При обычном запуске стандартная команда образа применяет миграции автоматически.

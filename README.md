# GitLab Radar

GitLab Radar собирает сведения о Python-проектах в GitLab и показывает используемые технологии,
зависимости и соответствие внутренним правилам компании.

## Возможности

- определение пакетных менеджеров uv, Poetry и pip;
- анализ прямых, опциональных и транзитивных Python-зависимостей;
- определение FastAPI и Django;
- анализ образов из `Dockerfile*` и Docker Compose;
- поиск и группировка компонентов GitLab CI;
- сбор project webhooks для проектов с доступом Maintainer или Owner;
- статистика версий Python, registry и технологий;
- конструктор требований компании;
- повторное использование результатов для неизменившихся ревизий;
- авторизация управляющих разделов через Keycloak.

## Запуск через Compose

Скопируйте [`.env.example`](.env.example) в `.env` и укажите:

```dotenv
GITLAB_URL=https://gitlab.example.com
GITLAB_PRIVATE_TOKEN=<token>
```

Остальные значения в шаблоне поднимают готовое локальное окружение PostgreSQL и Keycloak.
`GITLAB_PRIVATE_TOKEN` должен принадлежать пользователю с доступом к анализируемым проектам.

Запустите сервисы:

```shell
docker compose up --build
```

Приложение будет доступно по адресу `http://127.0.0.1:8000`. Учетная запись локального Keycloak:

- логин: `radar`;
- пароль: `radar`.

## Развертывание в OpenShift

### PostgreSQL

Администратор PostgreSQL должен создать роль и схему приложения. Для этого предназначен скрипт
[`deploy/postgres/create-radar.sql`](deploy/postgres/create-radar.sql):

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

### Keycloak

В Keycloak требуется публичный OIDC-клиент:

- Standard flow — включен;
- PKCE method — `S256`;
- Valid redirect URI — `https://<application-host>/*`;
- Web origin — `https://<application-host>`;
- Valid post logout redirect URI — `https://<application-host>/*`;
- access token содержит audience, равный идентификатору клиента.

Сейчас членство в группах Keycloak не проверяется. Доступ к управляющим разделам получает любой
пользователь с валидным access token указанного клиента. Для ограничения доступа по группе нужно добавить
group mapper в Keycloak и проверку claim в приложении.

### Контейнер приложения

Secret:

```dotenv
GITLAB_PRIVATE_TOKEN=<token>
RADAR_DB_PASSWORD=<password>
```

ConfigMap:

```dotenv
GITLAB_URL=https://gitlab.example.com
POSTGRES_HOST=<postgres-host>
POSTGRES_PORT=5432
POSTGRES_DB=<database>
RADAR_DB_USER=<application-user>
RADAR_DB_SCHEMA=<application-schema>
RADAR_HOST=0.0.0.0
RADAR_PORT=8000
RADAR_RELOAD=false
APP_PUBLIC_URL=https://<application-host>
RADAR_AUTH_PUBLIC_URL=https://<keycloak-public-host>
RADAR_AUTH_INTERNAL_URL=http://<keycloak-service>:8080
RADAR_AUTH_REALM=<realm>
RADAR_AUTH_CLIENT_ID=<client-id>
```

`RADAR_AUTH_PUBLIC_URL` должен совпадать с issuer токена и быть доступен браузеру.
`RADAR_AUTH_INTERNAL_URL` должен вести к тому же Keycloak из pod приложения. `POSTGRES_USER`,
`POSTGRES_PASSWORD` и переменные `KC_*` контейнеру приложения не нужны.

Перед запуском приложения нужно применить миграции:

```shell
uv run --no-sync tortoise migrate
```

При одной реплике это делает стандартная команда образа. При нескольких репликах миграция выполняется
отдельным Job, а Deployment запускается командой:

```shell
uv run --no-sync gitlab-radar
```

## Хранение данных

Снимки сканирования хранятся в PostgreSQL. Полученные из GitLab конфигурационные файлы временно сохраняются
как `TEXT` и удаляются после анализа. Для неизменившейся ревизии используется предыдущий результат.

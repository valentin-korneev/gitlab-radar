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
- опциональная авторизация управляющих разделов через Keycloak.

## Запуск через Compose

Скопируйте [`.env.example`](.env.example) в `.env` и укажите:

```dotenv
GITLAB_URL=https://gitlab.example.com
GITLAB_PRIVATE_TOKEN=<token>
```

Остальные значения в шаблоне поднимают готовое локальное окружение PostgreSQL без авторизации.
`GITLAB_PRIVATE_TOKEN` должен принадлежать пользователю с доступом к анализируемым проектам.

Запустите сервисы:

```shell
docker compose up --build
```

Приложение будет доступно по адресу `http://127.0.0.1:8000`.

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

Для включения авторизации установите `RADAR_AUTH_REQUIRED=true`. В Keycloak требуется публичный
OIDC-клиент:

- Standard flow — включен;
- PKCE method — `S256`;
- Valid redirect URI — `https://<application-host>/*`;
- Web origin — `https://<application-host>`;
- Valid post logout redirect URI — `https://<application-host>/*`.

Первоначальный список администраторов задаётся через запятую по claim `preferred_username`:

```dotenv
RADAR_AUTH_PREFERRED_USERNAMES=user.one,user.two
```

При включённой авторизации список должен содержать хотя бы одного пользователя.

Любой пользователь Keycloak может войти в приложение и автоматически добавляется в список пользователей
без административных прав. Администраторы назначают роли и блокируют пользователей в разделе
«Пользователи»; там же можно заранее добавить или удалить локальную запись. Удалённый пользователь снова
появится после следующего входа, поэтому для запрета доступа используется блокировка. Роль пользователей из
`RADAR_AUTH_PREFERRED_USERNAMES` управляется через окружение.

Отключённого пользователя не авторизует Keycloak. Для немедленного запрета доступа пользователю с уже
выданным токеном используется блокировка в приложении.

При `RADAR_AUTH_REQUIRED=false` Keycloak не используется. Приложение создаёт локальную тестовую
идентичность `local-admin`, имя которой можно изменить через `RADAR_AUTH_DEVELOPMENT_USERNAME`. В интерфейсе
можно переключиться на любое имя пользователя и проверить его персональные группы и назначенные
администратором ограничения. Выбранное имя передаётся в `X-Radar-Development-User`; этот заголовок
учитывается только при отключённой авторизации.

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
RADAR_AUTH_REQUIRED=true
RADAR_AUTH_PREFERRED_USERNAMES=user.one,user.two
RADAR_AUTH_PUBLIC_URL=https://<keycloak-public-host>
RADAR_AUTH_INTERNAL_URL=http://<keycloak-service>:8080
RADAR_AUTH_REALM=<realm>
RADAR_AUTH_CLIENT_ID=<client-id>
```

При обязательной авторизации `RADAR_AUTH_PUBLIC_URL` должен совпадать с issuer токена и быть доступен
браузеру, а `RADAR_AUTH_INTERNAL_URL` должен вести к тому же Keycloak из pod приложения. При отключённой
авторизации параметры Keycloak не передаются. `POSTGRES_USER` и `POSTGRES_PASSWORD` контейнеру приложения
не нужны.

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

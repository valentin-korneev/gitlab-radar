# GitLab Radar

GitLab Radar собирает сведения о Python-проектах в GitLab и показывает используемые технологии,
зависимости и соответствие внутренним правилам компании.

## Возможности

- определение пакетных менеджеров uv и pip;
- анализ прямых, опциональных и транзитивных Python-зависимостей;
- определение FastAPI и Django;
- анализ образов из `Dockerfile*` и Docker Compose;
- поиск и группировка компонентов GitLab CI;
- сбор project webhooks для проектов с доступом Maintainer или Owner;
- статистика версий Python, registry и технологий;
- конструктор требований компании;
- повторное использование результатов для неизменившихся ревизий;
- OIDC-авторизация управляющих разделов с публичным доступом к каталогам.

## Запуск через Compose

Скопируйте [`.env.example`](.env.example) в `.env` и укажите параметры GitLab, PostgreSQL и OIDC:

```dotenv
GITLAB_URL=https://gitlab.example.com
GITLAB_PRIVATE_TOKEN=<token>
RADAR_AUTH_CLIENT_ID=<client-id>
RADAR_AUTH_CLIENT_SECRET=<client-secret>
RADAR_AUTH_SESSION_SECRET=<random-secret>
RADAR_AUTH_PREFERRED_USERNAMES=<oidc-username>
```

Compose поднимает приложение и PostgreSQL; OIDC-провайдер должен быть доступен отдельно. Redirect URI
`http://127.0.0.1:8000/api/auth/callback` необходимо зарегистрировать у провайдера.
`GITLAB_PRIVATE_TOKEN` должен принадлежать пользователю с доступом к анализируемым проектам.

Запустите сервисы:

```shell
docker compose up -d --build
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

### OIDC

Авторизация обязательна для управляющих функций. Публичные страницы доступны без входа и без ограничений
видимости. У OIDC-провайдера требуется confidential client:

- Authorization Code flow — включен;
- PKCE с методом `S256` — включен;
- аутентификация клиента через `client_secret` — включена;
- redirect URI — `https://<application-host>/api/auth/callback`;
- post logout redirect URI, если провайдер поддерживает RP-initiated logout, — `https://<application-host>/`.

Backend получает OIDC metadata через внутренний адрес провайдера, обменивает authorization code с
`client_secret` и хранит зашифрованные токены в серверной сессии. В браузер передаются только идентификатор
сессии в `HttpOnly` cookie и отдельный CSRF-токен. Провайдер должен возвращать подписанный `id_token` с
claim `preferred_username`.

Issuer задаётся одним из двух способов:

```dotenv
# Приоритетный вариант для любого OIDC-провайдера
RADAR_AUTH_ISSUER=https://gitlab.com
RADAR_AUTH_INTERNAL_URL=https://gitlab.com
```

или через совместимые с прежней конфигурацией параметры Keycloak:

```dotenv
RADAR_AUTH_PUBLIC_URL=https://keycloak.example.com
RADAR_AUTH_INTERNAL_URL=http://keycloak:8080
RADAR_AUTH_REALM=example
```

Если задан `RADAR_AUTH_ISSUER`, значения `RADAR_AUTH_PUBLIC_URL` и `RADAR_AUTH_REALM` игнорируются.
`RADAR_AUTH_INTERNAL_URL` задаёт адрес того же провайдера, доступный backend. Для прямого issuer его путь
сохраняется, меняется только origin; если отдельного внутреннего адреса нет, укажите тот же адрес провайдера.

Первоначальный список администраторов задаётся через запятую по claim `preferred_username`:

```dotenv
RADAR_AUTH_PREFERRED_USERNAMES=user.one,user.two
```

Список должен содержать хотя бы одного пользователя.

Любой пользователь OIDC-провайдера может войти в приложение и автоматически добавляется в список
пользователей без административных прав. Администраторы назначают роли и блокируют пользователей в разделе
«Пользователи»; там же можно заранее добавить или удалить локальную запись. Удалённый пользователь снова
появится после следующего входа, поэтому для запрета доступа используется блокировка. Роль пользователей из
`RADAR_AUTH_PREFERRED_USERNAMES` управляется через окружение.

Отключённого пользователя не авторизует OIDC-провайдер. Для немедленного запрета доступа пользователю с уже
выданной сессией используется блокировка в приложении. Локального тестового пользователя нет.

### Контейнер приложения

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
`RADAR_AUTH_SESSION_SECRET` используется только для шифрования токенов в серверных сессиях и должен быть
стабильным между перезапусками и одинаковым на всех репликах. `POSTGRES_USER` и `POSTGRES_PASSWORD`
контейнеру приложения не нужны.

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

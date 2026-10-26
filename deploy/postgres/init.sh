#!/bin/sh
set -eu

psql \
  --set ON_ERROR_STOP=1 \
  --set database_name="$POSTGRES_DB" \
  --set radar_user="$RADAR_DB_USER" \
  --set radar_password="$RADAR_DB_PASSWORD" \
  --set radar_schema="$RADAR_DB_SCHEMA" \
  --set keycloak_user="$KC_DB_USERNAME" \
  --set keycloak_password="$KC_DB_PASSWORD" \
  --set keycloak_schema="$KC_DB_SCHEMA" \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" <<'SQL'
CREATE ROLE :"radar_user" LOGIN PASSWORD :'radar_password';
CREATE SCHEMA :"radar_schema" AUTHORIZATION :"radar_user";
ALTER ROLE :"radar_user" IN DATABASE :"database_name" SET search_path = :"radar_schema";

CREATE ROLE :"keycloak_user" LOGIN PASSWORD :'keycloak_password';
CREATE SCHEMA :"keycloak_schema" AUTHORIZATION :"keycloak_user";
ALTER ROLE :"keycloak_user" IN DATABASE :"database_name" SET search_path = :"keycloak_schema";

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE :"database_name" TO :"radar_user", :"keycloak_user";
SQL

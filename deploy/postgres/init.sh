#!/bin/sh
set -eu

psql \
  --set ON_ERROR_STOP=1 \
  --set database_name="$POSTGRES_DB" \
  --set radar_user="$RADAR_DB_USER" \
  --set radar_password="$RADAR_DB_PASSWORD" \
  --set radar_schema="$RADAR_DB_SCHEMA" \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" <<'SQL'
CREATE ROLE :"radar_user" LOGIN PASSWORD :'radar_password';
CREATE SCHEMA :"radar_schema" AUTHORIZATION :"radar_user";
ALTER ROLE :"radar_user" IN DATABASE :"database_name" SET search_path = :"radar_schema";

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE :"database_name" TO :"radar_user";
SQL

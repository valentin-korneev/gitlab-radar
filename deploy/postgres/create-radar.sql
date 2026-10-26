SELECT format('CREATE ROLE %I LOGIN', :'radar_user')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'radar_user')
\gexec

ALTER ROLE :"radar_user" LOGIN PASSWORD :'radar_password';
GRANT CONNECT ON DATABASE :"radar_database" TO :"radar_user";

CREATE SCHEMA IF NOT EXISTS :"radar_schema" AUTHORIZATION :"radar_user";
ALTER SCHEMA :"radar_schema" OWNER TO :"radar_user";
GRANT USAGE, CREATE ON SCHEMA :"radar_schema" TO :"radar_user";

ALTER ROLE :"radar_user" IN DATABASE :"radar_database"
SET search_path TO :"radar_schema";

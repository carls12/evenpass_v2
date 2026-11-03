#!/bin/sh
# Central PostgreSQL: one database + one login per app. Runs on every `docker compose up`
# (service db-setup) and is idempotent: creates what is missing, updates passwords, never deletes.
#
# Apps are listed as "<database/login name>:<env var holding its password>". An app whose
# password is empty is skipped, so a new app only needs a line here and a password in .env.
set -eu

APPS="bodyofchrist:BODYOFCHRIST_DB_PASSWORD"

# Logins may only open their own app database, not the maintenance database either.
psql -v ON_ERROR_STOP=1 -q -c 'REVOKE CONNECT ON DATABASE postgres FROM PUBLIC'

for entry in $APPS; do
  name=${entry%%:*}
  var=${entry#*:}
  eval "password=\${$var:-}"
  if [ -z "$password" ]; then
    echo "db-setup: $name skipped ($var is empty)"
    continue
  fi
  # psql variables (:'pw') quote the password safely; format(%I/%L) quotes names and literals.
  psql -v ON_ERROR_STOP=1 -v app="$name" -v pw="$password" -q <<'SQL'
SELECT format('CREATE ROLE %I LOGIN', :'app') WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app') \gexec
SELECT format('ALTER ROLE %I WITH LOGIN PASSWORD %L', :'app', :'pw') \gexec
SELECT format('CREATE DATABASE %I OWNER %I ENCODING ''UTF8''', :'app', :'app') WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'app') \gexec
-- Isolation: only the app's own login (and the admin) may connect to its database.
SELECT format('REVOKE ALL ON DATABASE %I FROM PUBLIC', :'app') \gexec
SQL
  echo "db-setup: $name ready"
done

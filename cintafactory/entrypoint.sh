#!/usr/bin/env bash
set -euo pipefail

# Attente Postgres si HOST/PORT fournis
if [ -n "${DATABASE_HOST:-}" ] && [ -n "${DATABASE_PORT:-}" ]; then
  echo "Attente de Postgres ${DATABASE_HOST}:${DATABASE_PORT} ..."
  for i in {1..120}; do
    nc -z "${DATABASE_HOST}" "${DATABASE_PORT}" && echo "Postgres OK" && break
    sleep 1
  done
fi

# Migrations / static (désactivables via variables)
if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  echo "Migrating..."
  python manage.py migrate --noinput
fi

if [ "${COLLECT_STATIC:-1}" = "1" ]; then
  echo "Collecting static..."
  python manage.py collectstatic --noinput || true
fi

: "${APP_MODULE:=project.wsgi:application}"

exec gunicorn "$APP_MODULE" --config /app/gunicorn.conf.py

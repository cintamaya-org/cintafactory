#!/usr/bin/env bash
set -euo pipefail

# Détecte la racine du projet Django (dev: /app, prod: /app/cintafactory)
if [ -f /app/manage.py ]; then
  APP_DIR=/app
elif [ -f /app/cintafactory/manage.py ]; then
  APP_DIR=/app/cintafactory
else
  echo "ERROR: manage.py introuvable dans /app ou /app/cintafactory" >&2
  exit 1
fi

MANAGE_PY="${APP_DIR}/manage.py"
GUNICORN_CONF="${APP_DIR}/gunicorn.conf.py"

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
  python "$MANAGE_PY" migrate --noinput
fi


if [ "${COLLECT_STATIC:-1}" = "1" ]; then
  echo "Collecting static..."
  python "$MANAGE_PY" collectstatic --noinput || true
fi

: "${APP_MODULE:=project.wsgi:application}"

exec gunicorn "$APP_MODULE" --config "$GUNICORN_CONF"

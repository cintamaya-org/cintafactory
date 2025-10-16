#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 [test|prod]" >&2
  exit 1
fi

ENVIRONMENT="$1"

case "$ENVIRONMENT" in
  test)
    COMPOSE_OVERRIDE="deploy/docker-compose.test.yml"
    DEFAULT_PROJECT_NAME="cintafactory_test"
    DEFAULT_COLLECTSTATIC="0"
    ;;
  prod)
    COMPOSE_OVERRIDE="deploy/docker-compose.prod.yml"
    DEFAULT_PROJECT_NAME="cintafactory_prod"
    DEFAULT_COLLECTSTATIC="1"
    ;;
  *)
    echo "Unknown environment '$ENVIRONMENT' (expected 'test' or 'prod')." >&2
    exit 1
    ;;
esac

COMPOSE_BASE="deploy/docker-compose.base.yml"
COMPOSE_FILES=(-f "$COMPOSE_BASE" -f "$COMPOSE_OVERRIDE")

# Determine which Compose binary to use.
if docker compose version >/dev/null 2>&1; then
  COMPOSE_BIN=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_BIN=(docker-compose)
else
  echo "Docker Compose is required but was not found on the host." >&2
  exit 1
fi

# Load environment-specific overrides if present.
ENV_FILE="deploy/env/${ENVIRONMENT}.env"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
else
  echo "Warning: ${ENV_FILE} not found. Continuing without additional overrides." >&2
fi

export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-$DEFAULT_PROJECT_NAME}"

RUN_MANAGEMENT_COMMANDS="${RUN_MANAGEMENT_COMMANDS:-1}"
RUN_COLLECTSTATIC="${RUN_COLLECTSTATIC:-$DEFAULT_COLLECTSTATIC}"

"${COMPOSE_BIN[@]}" "${COMPOSE_FILES[@]}" up -d --build

if [ "$RUN_MANAGEMENT_COMMANDS" = "1" ]; then
  "${COMPOSE_BIN[@]}" "${COMPOSE_FILES[@]}" exec -T web python3 manage.py migrate --noinput
  if [ "$RUN_COLLECTSTATIC" = "1" ]; then
    "${COMPOSE_BIN[@]}" "${COMPOSE_FILES[@]}" exec -T web python3 manage.py collectstatic --noinput
  fi
fi

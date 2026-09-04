#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DASH_DIR="$ROOT_DIR/cintafactory/deploy/observability/grafana/dashboards"
COMPOSE_FILE="$ROOT_DIR/cintafactory/docker-compose.observability.dev.yml"

required_dashboards=(
  "service-overview.json"
  "reliability-slo.json"
  "logs-and-traces.json"
  "capacity-and-scaling.json"
  "architecture-and-interactions.json"
)

for file in "${required_dashboards[@]}"; do
  path="$DASH_DIR/$file"
  if [[ ! -f "$path" ]]; then
    echo "[FAIL] missing dashboard: $path"
    exit 1
  fi
  python3 -m json.tool "$path" >/dev/null
  echo "[OK] valid JSON: $file"
done

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "[FAIL] missing compose file: $COMPOSE_FILE"
  exit 1
fi

grep -q "prometheus:" "$COMPOSE_FILE" || { echo "[FAIL] compose missing prometheus service"; exit 1; }
grep -q "grafana:" "$COMPOSE_FILE" || { echo "[FAIL] compose missing grafana service"; exit 1; }
grep -q "loki:" "$COMPOSE_FILE" || { echo "[FAIL] compose missing loki service"; exit 1; }
grep -q "promtail:" "$COMPOSE_FILE" || { echo "[FAIL] compose missing promtail service"; exit 1; }
grep -q "cadvisor:" "$COMPOSE_FILE" || { echo "[FAIL] compose missing cadvisor service"; exit 1; }

echo "[PASS] dashboard asset validation"

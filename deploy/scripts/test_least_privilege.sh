#!/usr/bin/env bash
set -euo pipefail

service_block() {
  local file="$1"
  local service="$2"
  awk -v svc="$service" '
    BEGIN {in_block=0}
    $0 ~ "^  "svc":" {in_block=1; print; next}
    in_block && $0 ~ "^  [a-zA-Z0-9_-]+:" {exit}
    in_block {print}
  ' "$file"
}

assert_block_has() {
  local file="$1"
  local service="$2"
  local pattern="$3"
  local block
  block="$(service_block "$file" "$service")"
  if [[ -z "$block" ]]; then
    echo "FAIL: service '$service' not found in $file"
    exit 1
  fi
  if ! grep -Eq -- "$pattern" <<<"$block"; then
    echo "FAIL: '$service' in $file missing pattern: $pattern"
    exit 1
  fi
}

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

# Scaling stack: app runtimes must drop privileges.
assert_block_has "docker-compose.scaling.dev.yml" "web" "security_opt:"
assert_block_has "docker-compose.scaling.dev.yml" "web" "no-new-privileges:true"
assert_block_has "docker-compose.scaling.dev.yml" "web" "cap_drop:"
assert_block_has "docker-compose.scaling.dev.yml" "web" "- ALL"

assert_block_has "docker-compose.scaling.dev.yml" "worker" "security_opt:"
assert_block_has "docker-compose.scaling.dev.yml" "worker" "no-new-privileges:true"
assert_block_has "docker-compose.scaling.dev.yml" "worker" "cap_drop:"
assert_block_has "docker-compose.scaling.dev.yml" "worker" "- ALL"

assert_block_has "docker-compose.scaling.dev.yml" "likec4" "security_opt:"
assert_block_has "docker-compose.scaling.dev.yml" "likec4" "no-new-privileges:true"
assert_block_has "docker-compose.scaling.dev.yml" "likec4" "cap_drop:"
assert_block_has "docker-compose.scaling.dev.yml" "likec4" "- ALL"
assert_block_has "docker-compose.scaling.dev.yml" "likec4" "user:"
assert_block_has "docker-compose.scaling.dev.yml" "likec4" "read_only: true"

assert_block_has "docker-compose.scaling.dev.yml" "likec4-exporter" "security_opt:"
assert_block_has "docker-compose.scaling.dev.yml" "likec4-exporter" "no-new-privileges:true"
assert_block_has "docker-compose.scaling.dev.yml" "likec4-exporter" "cap_drop:"
assert_block_has "docker-compose.scaling.dev.yml" "likec4-exporter" "- ALL"
assert_block_has "docker-compose.scaling.dev.yml" "likec4-exporter" "user:"
assert_block_has "docker-compose.scaling.dev.yml" "likec4-exporter" "read_only: true"

# Deploy base stack: same profile for app + LikeC4 services.
assert_block_has "deploy/docker-compose.base.yml" "web" "security_opt:"
assert_block_has "deploy/docker-compose.base.yml" "web" "no-new-privileges:true"
assert_block_has "deploy/docker-compose.base.yml" "web" "cap_drop:"
assert_block_has "deploy/docker-compose.base.yml" "web" "- ALL"

assert_block_has "deploy/docker-compose.base.yml" "likec4" "security_opt:"
assert_block_has "deploy/docker-compose.base.yml" "likec4" "no-new-privileges:true"
assert_block_has "deploy/docker-compose.base.yml" "likec4" "cap_drop:"
assert_block_has "deploy/docker-compose.base.yml" "likec4" "- ALL"
assert_block_has "deploy/docker-compose.base.yml" "likec4" "user:"
assert_block_has "deploy/docker-compose.base.yml" "likec4" "read_only: true"

assert_block_has "deploy/docker-compose.base.yml" "likec4-exporter" "security_opt:"
assert_block_has "deploy/docker-compose.base.yml" "likec4-exporter" "no-new-privileges:true"
assert_block_has "deploy/docker-compose.base.yml" "likec4-exporter" "cap_drop:"
assert_block_has "deploy/docker-compose.base.yml" "likec4-exporter" "- ALL"
assert_block_has "deploy/docker-compose.base.yml" "likec4-exporter" "user:"
assert_block_has "deploy/docker-compose.base.yml" "likec4-exporter" "read_only: true"

echo "PASS: least-privilege policy checks passed."

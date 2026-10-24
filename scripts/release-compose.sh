#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/scripts/build-lib.sh"

usage() { echo "用法: $0 <frontend|backend|deps|all> | $0 rollback <stamp> <frontend|backend|deps|all>"; }
rollback() {
  local stamp="$1" scope="$2" service image snapshot
  export DOMAIN_ADMIN_BASE_IMAGE="$(base_image)"
  for service in $(scope_services "$scope"); do
    image="domain-admin-${service}:latest"
    snapshot="domain-admin-${service}:rollback-${stamp}"
    docker image inspect "$snapshot" >/dev/null
    docker image tag "$snapshot" "$image"
  done
  (cd "$ROOT" && docker compose up -d --no-deps $(scope_services "$scope"))
}

if [ "${1:-}" = "rollback" ]; then
  [ $# -eq 3 ] || { usage; exit 2; }
  rollback "$2" "$3"
  exit 0
fi
[ $# -eq 1 ] || { usage; exit 2; }
scope_services "$1" >/dev/null || { usage; exit 2; }
stamp="$(date +%Y%m%d%H%M%S)"
for service in $(scope_services "$1"); do
  image="domain-admin-${service}:latest"
  snapshot="domain-admin-${service}:rollback-${stamp}"
  docker image inspect "$image" >/dev/null 2>&1 && docker image tag "$image" "$snapshot" || true
done
"$ROOT/scripts/build-images.sh" "$1"
export DOMAIN_ADMIN_BASE_IMAGE="$(base_image)"
(cd "$ROOT" && docker compose up -d --no-deps $(scope_services "$1"))
echo "rollback_stamp=${stamp} scope=$1"

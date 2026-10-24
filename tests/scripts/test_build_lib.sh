#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
source "$ROOT/scripts/build-lib.sh"

assert_eq() {
  [ "$1" = "$2" ] || { echo "期望 '$1'，实际 '$2'" >&2; exit 1; }
}

assert_eq "domain-admin-base:deps-dcb7d8c888558c95" "$(base_image)"
assert_eq "frontend" "$(scope_for_paths <<'EOF'
domain-admin-web/src/App.vue
EOF
)"
assert_eq "backend" "$(scope_for_paths <<'EOF'
domain-admin/domain_admin/main.py
EOF
)"
assert_eq "deps" "$(scope_for_paths <<'EOF'
domain-admin/requirements/production.lock
EOF
)"
assert_eq "all" "$(scope_for_paths <<'EOF'
README.md
EOF
)"
assert_eq "backend worker scheduler" "$(scope_services backend)"
assert_eq "frontend" "$(scope_services frontend)"

if scope_services invalid >/dev/null 2>&1; then
  echo "非法范围不应成功" >&2
  exit 1
fi

"$ROOT/scripts/check-production-lock.sh"
grep -q 'reason=new-base' "$ROOT/scripts/build-images.sh"
grep -q 'compose_build_args+=(--no-cache)' "$ROOT/scripts/build-images.sh"
grep -q -- '--build-arg APT_ARCHIVE_BASE' "$ROOT/scripts/build-images.sh"
grep -q 'BUILD_TIMEOUT_SECONDS' "$ROOT/scripts/build-images.sh"
grep -q 'docker compose --progress plain build' "$ROOT/scripts/build-images.sh"
grep -q 'result=timeout' "$ROOT/scripts/build-images.sh"
echo "test_build_lib: PASS"

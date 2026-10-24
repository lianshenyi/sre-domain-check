#!/usr/bin/env bash
# 公共构建函数；本文件只定义函数，便于 shell 测试复用。
set -euo pipefail

BUILD_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK_FILE="$BUILD_ROOT/domain-admin/requirements/production.lock"

base_digest() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$LOCK_FILE" | awk '{print substr($1, 1, 16)}'
  else
    shasum -a 256 "$LOCK_FILE" | awk '{print substr($1, 1, 16)}'
  fi
}

base_image() {
  printf 'domain-admin-base:deps-%s\n' "$(base_digest)"
}

scope_services() {
  case "$1" in
    frontend) printf 'frontend\n' ;;
    backend|deps) printf 'backend worker scheduler\n' ;;
    all) printf 'frontend backend worker scheduler\n' ;;
    *) return 2 ;;
  esac
}

scope_for_paths() {
  local path scope=""
  while IFS= read -r path; do
    case "$path" in
      domain-admin/requirements/production.lock|domain-admin/Dockerfile.base)
        printf 'deps\n'; return ;;
      domain-admin-web/*) scope="${scope:-frontend}" ;;
      domain-admin/*|docker-compose.yml|scripts/*|build.sh) scope="backend" ;;
      *) printf 'all\n'; return ;;
    esac
  done
  printf '%s\n' "${scope:-all}"
}

scope_for_git_ref() {
  git -C "$BUILD_ROOT" diff --name-only "$1"...HEAD | scope_for_paths
}

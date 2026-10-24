#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/scripts/build-lib.sh"

usage() { echo "用法: $0 <frontend|backend|deps|all|--since <git-ref>>"; }
if [ "${1:-}" = "--since" ]; then
  [ $# -eq 2 ] || { usage; exit 2; }
  SCOPE="$(scope_for_git_ref "$2")"
elif [ $# -eq 1 ]; then
  SCOPE="$1"
else
  usage; exit 2
fi
scope_services "$SCOPE" >/dev/null || { usage; exit 2; }
docker buildx version >/dev/null

BASE_IMAGE="$(base_image)"
export DOMAIN_ADMIN_BASE_IMAGE="$BASE_IMAGE"
APT_ARCHIVE_BASE="${APT_ARCHIVE_BASE:-https://mirrors.cloud.tencent.com/debian-archive}"
PIP_INDEX="${PIP_INDEX:-https://pypi.org/simple/}"
BUILD_TIMEOUT_SECONDS="${BUILD_TIMEOUT_SECONDS:-600}"
case "$BUILD_TIMEOUT_SECONDS" in
  ''|*[!0-9]*|0) echo "BUILD_TIMEOUT_SECONDS 必须是正整数秒" >&2; exit 2 ;;
esac
LOG_DIR="$ROOT/artifacts/build"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/$(date +%Y%m%d-%H%M%S)-${SCOPE}.log"
started="$(date +%s)"
echo "scope=${SCOPE} base=${BASE_IMAGE} log=${LOG}" | tee -a "$LOG"

base_built=0
if ! docker image inspect "$BASE_IMAGE" >/dev/null 2>&1; then
  echo "phase=base cache=miss" | tee -a "$LOG"
  docker build --progress=plain --network host \
    --build-arg APT_ARCHIVE_BASE="$APT_ARCHIVE_BASE" \
    --build-arg PIP_INDEX="$PIP_INDEX" \
    -t "$BASE_IMAGE" -f "$ROOT/domain-admin/Dockerfile.base" "$ROOT/domain-admin" 2>&1 | tee -a "$LOG"
  # 新 digest base 首次出现时，强制三个子镜像舍弃旧 FROM 缓存，确保运行时
  # 实际继承该 base；之后的热构建仍可复用普通 Docker layer cache。
  base_built=1
else
  echo "phase=base cache=hit image-exists" | tee -a "$LOG"
fi

services="$(scope_services "$SCOPE")"
echo "phase=services services=${services} progress=plain timeout_seconds=${BUILD_TIMEOUT_SECONDS}" | tee -a "$LOG"
compose_build_args=()
if [ "$base_built" -eq 1 ]; then
  echo "phase=services cache=miss reason=new-base" | tee -a "$LOG"
  compose_build_args+=(--no-cache)
fi
set +e
(cd "$ROOT" && timeout --signal=TERM --kill-after=15s "${BUILD_TIMEOUT_SECONDS}s" \
  docker compose --progress plain build "${compose_build_args[@]}" $services) 2>&1 | tee -a "$LOG"
build_rc="${PIPESTATUS[0]}"
set -e
elapsed=$(( $(date +%s) - started ))
hits="$(grep -Ec 'CACHED|cache hit|cache=hit' "$LOG" || true)"
if [ "$build_rc" -ne 0 ]; then
  if [ "$build_rc" -eq 124 ] || [ "$build_rc" -eq 137 ]; then
    echo "result=timeout elapsed_seconds=${elapsed} cache_hits=${hits} timeout_seconds=${BUILD_TIMEOUT_SECONDS}" | tee -a "$LOG"
  else
    echo "result=failure exit_code=${build_rc} elapsed_seconds=${elapsed} cache_hits=${hits}" | tee -a "$LOG"
  fi
  exit "$build_rc"
fi
echo "result=success elapsed_seconds=${elapsed} cache_hits=${hits}" | tee -a "$LOG"

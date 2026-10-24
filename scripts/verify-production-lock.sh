#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOCK="$ROOT/domain-admin/requirements/production.lock"
PYTHON_IMAGE="${PYTHON_IMAGE:-python:3.7.17-slim-bullseye}"
PIP_INDEX="${PIP_INDEX:-https://pypi.org/simple/}"

"$ROOT/scripts/check-production-lock.sh"

# --dry-run 仍会下载元数据/分发包来校验哈希，但不会写入镜像或宿主机环境。
docker run --rm -e PIP_INDEX="$PIP_INDEX" -v "$ROOT/domain-admin:/work:ro" -w /work "$PYTHON_IMAGE" \
  sh -ec 'python -m pip install -i "$PIP_INDEX" --dry-run --require-hashes -r requirements/production.lock'

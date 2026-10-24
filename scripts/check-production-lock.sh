#!/usr/bin/env bash
# 校验顶层生产依赖均已被锁文件精确固定，避免遗漏运行时入口依赖。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
INPUT="$ROOT/domain-admin/requirements/production.txt"
LOCK="$ROOT/domain-admin/requirements/production.lock"

test -s "$INPUT"
test -s "$LOCK"

while IFS= read -r requirement || [ -n "$requirement" ]; do
  requirement="${requirement%%#*}"
  [ -n "${requirement//[[:space:]]/}" ] || continue
  package="$(printf '%s' "$requirement" | sed 's/[<>=!~;[].*$//' | tr '[:upper:]_' '[:lower:]-')"
  grep -Eiq "^${package}==" "$LOCK" || {
    echo "生产依赖未锁定: ${requirement}" >&2
    exit 1
  }
done < "$INPUT"

grep -q -- '--hash=sha256:' "$LOCK"
echo "production lock input: PASS"

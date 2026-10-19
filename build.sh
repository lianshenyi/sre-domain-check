#!/usr/bin/env bash
set -euo pipefail

# 用法:
#   ./build.sh                    # 构建所有镜像（latest）
#   ./build.sh v1.0.1             # 构建所有镜像（指定版本标签）
#   ./build.sh latest backend     # 只构建 backend
#   ./build.sh v1.0.1 worker scheduler  # 只构建 worker + scheduler

TAG="${1:-latest}"
shift 2>/dev/null || true
TARGETS=("${@:-backend frontend worker scheduler}")

# 如果没传具体目标，默认全部
if [ ${#TARGETS[@]} -eq 0 ]; then
  TARGETS=(backend frontend worker scheduler)
fi

BASE_IMAGE="domain-admin-base:${TAG}"

echo "==> 构建基础镜像: ${BASE_IMAGE}"
docker build --network host \
  -t "${BASE_IMAGE}" \
  -f domain-admin/Dockerfile.base \
  domain-admin

for target in "${TARGETS[@]}"; do
  case "${target}" in
    backend)
      echo "==> 构建 backend:${TAG}"
      docker build --network host \
        --build-arg BASE_IMAGE="${BASE_IMAGE}" \
        -t "domain-admin-backend:${TAG}" \
        -f domain-admin/Dockerfile \
        domain-admin
      ;;
    frontend)
      echo "==> 构建 frontend:${TAG}"
      docker build --network host \
        -t "domain-admin-frontend:${TAG}" \
        -f domain-admin-web/Dockerfile \
        domain-admin-web
      ;;
    worker)
      echo "==> 构建 worker:${TAG}"
      docker build --network host \
        --build-arg BASE_IMAGE="${BASE_IMAGE}" \
        -t "domain-admin-worker:${TAG}" \
        -f domain-admin/Dockerfile.worker \
        domain-admin
      ;;
    scheduler)
      echo "==> 构建 scheduler:${TAG}"
      docker build --network host \
        --build-arg BASE_IMAGE="${BASE_IMAGE}" \
        -t "domain-admin-scheduler:${TAG}" \
        -f domain-admin/Dockerfile.scheduler \
        domain-admin
      ;;
    *)
      echo "未知目标: ${target}，可选: backend frontend worker scheduler"
      exit 1
      ;;
  esac
done

echo ""
echo "==> 构建完成"
docker images | grep domain-admin

#!/usr/bin/env bash
set -euo pipefail

# 用法:
#   ./build.sh                    # 构建所有镜像（latest）
#   ./build.sh v1.0.1             # 构建所有镜像（指定版本标签）
#   ./build.sh latest backend     # 只构建 backend
#   ./build.sh v1.0.1 worker scheduler  # 只构建 worker + scheduler
#   REGION=cn ./build.sh v1.0.1   # 国内源构建（apt/pip/npm 走阿里云/npmmirror）
#   REGION=global ./build.sh      # 国际源构建（默认）

TAG="${1:-latest}"
shift 2>/dev/null || true

if [ $# -eq 0 ]; then
  TARGETS=(backend frontend worker scheduler)
else
  TARGETS=("$@")
fi

REGION="${REGION:-global}"

if [ "$REGION" = "cn" ]; then
  APT_MIRROR="mirrors.aliyun.com"
  PIP_INDEX="https://mirrors.aliyun.com/pypi/simple/"
  NPM_REGISTRY="https://registry.npmmirror.com"
else
  APT_MIRROR="deb.debian.org"
  PIP_INDEX="https://pypi.org/simple/"
  NPM_REGISTRY="https://registry.npmjs.org"
fi

BASE_IMAGE="domain-admin-base:${TAG}"

echo "==> 镜像源: ${REGION} (apt=${APT_MIRROR}, pip=${PIP_INDEX}, npm=${NPM_REGISTRY})"
echo "==> 构建基础镜像: ${BASE_IMAGE}"
docker build --network host \
  --build-arg APT_MIRROR="${APT_MIRROR}" \
  --build-arg PIP_INDEX="${PIP_INDEX}" \
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
        --build-arg NPM_REGISTRY="${NPM_REGISTRY}" \
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

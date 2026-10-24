# 第一阶段构建缓存与范围发布优化

## 范围

本次只优化构建可复现性和 Docker 构建路径：不升级 Python 3.7、Debian bullseye 或 Node，不改业务 API，也不引入 Go 服务。

## 依赖与不可变 base

- `domain-admin/requirements/production.lock` 由 Python 3.7 的 `pip-compile --generate-hashes` 生成，固定生产直接/间接依赖及下载哈希。
- `scripts/check-production-lock.sh` 先校验 `production.txt` 的每个顶层依赖均在 lock 中精确固定；`scripts/verify-production-lock.sh` 再用 Python 3.7 容器执行 `pip install --dry-run --require-hashes`。任一步失败都表示 lock 不可用于构建。
- base tag 为 `domain-admin-base:deps-<production.lock SHA-256 前 16 位>`。当前 lock 对应 `domain-admin-base:deps-dcb7d8c888558c95`。
- backend、worker、scheduler 从同一 `DOMAIN_ADMIN_BASE_IMAGE` 构建，不再依赖可变 `latest`。

## 构建与发布

Bullseye 已 EOL，apt 默认使用腾讯完整归档 base：`https://mirrors.cloud.tencent.com/debian-archive`。它同时覆盖 `/debian`、`/debian-security` 和 updates，禁止回退到常规 `/debian-security` 命名空间。腾讯源不可用时，可仅对本次构建传 `APT_ARCHIVE_BASE=https://mirrors.aliyun.com/debian-archive PIP_INDEX=https://mirrors.aliyun.com/pypi/simple/ scripts/release-compose.sh deps`。参数会改变 base 构建层，但不改变 lock 或运行时镜像内容。

系统包安装层位于 `COPY production.lock` 之前；因此 lock 变化仅使 pip 层失效，apt 包层继续命中缓存。`Dockerfile.base` 的 apt cache mount 也不会进入最终运行时镜像。

### BUG-005：Bullseye Archive 源

常规 Bullseye security 命名空间在 EOL 后可能保留过期索引而删除对应包，表现为 `apt-get update` 成功、安装时 404。已改为完整 Archive base URL。目标机验证腾讯 Archive 与阿里 Archive 的 Release 签名、解析版本和样本包 SHA-256 一致；腾讯为默认，阿里为一次性回退，不进行无限重试。

### 目标机验收记录（2026-10-23）

- BUG-004：以 Python 3.7 完整重生成的 lock 固定 `gunicorn==22.0.0` 与 `python-dateutil==2.9.0.post0`；目标构建的 `pip install --require-hashes` 成功，运行镜像内 `gunicorn --version` 可调用。
- BUG-005：腾讯 Archive cold `deps` 发布成功，构建日志 `20261023-112923-deps.log` 记录 `elapsed_seconds=1016`、`cache_hits=4`；系统 apt 层命中缓存，pip 层完成首次填充并通过哈希安装。
- 同 digest 热构建日志 `20261023-114655-deps.log` 记录 `phase=base cache=hit image-exists`、`elapsed_seconds=36`、`cache_hits=2`，三个 Python 角色的代码 COPY 层均为 `CACHED`。
- 发布后验证 6 个 Compose 容器运行（MySQL、Redis healthy），入口及 `/api/getSystemVersion` 返回 200；使用环境中的管理员凭据登录成功，带 token 的 `/api/getDomainList` 返回 200。凭据与 token 未写入日志或本文档。

```bash
# 只构建前端；不构建 Python base
scripts/build-images.sh frontend

# 只构建三个 Python 代码镜像；已有 base 时不会重装依赖
scripts/build-images.sh backend

# lock 或 Dockerfile.base 变化时：先构建新的 base，再构建三个 Python 角色
scripts/build-images.sh deps

# 根据相对 Git 基线自动选择范围
scripts/build-images.sh --since origin/main

# 构建、创建镜像快照，并仅重建目标服务
scripts/release-compose.sh frontend
scripts/release-compose.sh backend
scripts/release-compose.sh deps
```

每次构建日志写入 `artifacts/build/`（本地忽略），末行有 `elapsed_seconds` 与 `cache_hits`。BuildKit 为必需条件：`docker buildx version` 失败时脚本会终止；请安装/启用 Docker BuildKit 后再执行。

Compose 构建固定使用 plain 进度，并由 `BUILD_TIMEOUT_SECONDS` 限时（默认 600 秒）。超时日志末行记录 `result=timeout`，其他失败记录 `result=failure`；需要适配低速构建机时可对单次命令覆盖，例如 `BUILD_TIMEOUT_SECONDS=900 scripts/build-images.sh frontend`。

### BUG-006：frontend 构建误判停滞

QA 首次 frontend 构建日志显示 npm 层实际耗时 89.5 秒，随后 Vite 进入 `transforming...`，在整个命令约 124 秒时被人工终止；当时尚未达到目标机实测约 49–60 秒的 Vite 转换耗时。进程树确认高 CPU 位于 BuildKit 容器内的 Vite 子进程，宿主机 `docker compose` 零 CPU 是等待构建结果，并非死锁。

脚本现显式启用 plain 进度和 600 秒截止，并在失败、超时、成功时写入不同结果。目标机对照验证：脚本路径 75 秒成功、直接 Compose 81 秒成功、直接 `docker build` 83 秒成功；镜像导出分别只需约 3–13 秒，排除 Compose、BuildKit 导出层和脚本管道停滞。

修复后连续两次 frontend 热构建分别在 23 秒和 19 秒完成，均记录 `result=success` 与 9 个 cache hit，服务范围只有 frontend；三个 Python 镜像创建时间和 6 个运行容器 ID 均未变化。另以 `BUILD_TIMEOUT_SECONDS=1` 注入超时，脚本返回 124、记录 `result=timeout`，且无残留 Compose/Buildx 进程。

## 冷/热缓存验收

在不含本项目 Docker layer cache 的构建机执行一次 `scripts/build-images.sh deps` 和 `scripts/build-images.sh frontend`，保存为 cold 证据。紧接着重复相同命令作为 hot 证据；对比日志末行耗时，并检查 `CACHED`、`cache hit` 与 `phase=base cache=hit image-exists`。

首次生成某个 digest base 时，脚本会对三个 Python 角色加 `--no-cache`，日志显示 `phase=services cache=miss reason=new-base`；这是为了强制它们继承新 base。随后同一 digest 的热构建不传该参数，可正常命中业务镜像层缓存。

完成范围发布后执行：

```bash
docker compose ps
curl -fsS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:${HTTP_PORT:-8080}/
curl -fsS http://127.0.0.1:${HTTP_PORT:-8080}/api/getSystemVersion
```

登录验证仍使用 `env/backend.env` 中的管理员凭据，禁止将真实凭据写入命令历史、文档或工单。

## 回滚

每次 `release-compose.sh` 都打印 `rollback_stamp`。仅回滚受影响范围：

```bash
scripts/release-compose.sh rollback <rollback_stamp> frontend
scripts/release-compose.sh rollback <rollback_stamp> backend
scripts/release-compose.sh rollback <rollback_stamp> deps
```

依赖变更回滚时，先恢复此前源码/lock，再以此前 lock 派生的 `DOMAIN_ADMIN_BASE_IMAGE` 重建或恢复 backend、worker、scheduler 快照。镜像回滚不回滚数据库迁移；若有迁移，另按备份恢复流程处置。

# CLAUDE.md

本文件记录「在一台服务器上用 Docker Compose 部署本项目」所需的全部关键信息，供 Claude / 运维人员参考。

## 1. 项目概览

`domain-admin` 是一个域名 / SSL 证书巡检系统。本仓库是部署仓库，内含后端、前端源码以及 Docker / K8s 资产。

生产拓扑（`docker-compose.yml`，默认项目名即目录名 `sre-domain-check`）：

| 服务 | 构建 / 镜像 | 作用 | 宿主机端口 | 数据挂载 |
| --- | --- | --- | --- | --- |
| `frontend` | `domain-admin-web/Dockerfile`（node 构建 + nginx） | 静态页面 + 反向代理 `/api`、`/temp` 到 `backend:8000` | `${HTTP_PORT:-8080}:80` | 无 |
| `backend` | `domain-admin/Dockerfile`（gunicorn） | Flask API，`domain_admin.main:app` | 不发布（仅 expose 8000） | `data/backend`、`logs/backend`、`data/temp` |
| `worker` | `domain-admin/Dockerfile.worker` | Redis(RQ) 异步任务消费者，`python -m domain_admin.worker` | 不发布 | 同上 |
| `scheduler` | `domain-admin/Dockerfile.scheduler` | 定时调度，`python -m domain_admin.scheduler` | 不发布 | 同上 |
| `mysql` | `mysql:8.0` | 业务数据库 | 不发布 | `data/mysql` |
| `redis` | `redis:7-alpine` | 缓存 / 任务队列 / 分布式锁 | 不发布 | `data/redis` |

要点：

- 容器网络固定为 `domain-admin-net`，`container_name` 固定为 `domain-admin-*`。
- 只有 `frontend` 暴露宿主机端口；MySQL / Redis 仅容器内网可达，**不要**给它们加 ports。
- `backend` / `worker` 固定 `SCHEDULER_ENABLED=false`、`SCHEDULER_ROLE=none`；只有 `scheduler` 是 `true / worker`，避免重复调度。
- 所有业务容器 `TZ=Asia/Shanghai`，避免 apscheduler / tzlocal 容器内时区问题。
- 业务容器运行目录为 `/app`，`/app/database`、`/app/logs`、`/app/temp` 分别对应宿主机 `data/backend`、`logs/backend`、`data/temp`。

## 2. 关键文件

| 文件 | 说明 |
| --- | --- |
| `docker-compose.yml` | 生产 Compose 编排（6 个服务） |
| `.env.example` | Compose 插值变量样例（`HTTP_PORT`、MySQL 初始化账号） |
| `env/backend.env.example` | backend/worker/scheduler 环境变量样例（`DB_CONNECT_URL`、Redis、管理员账号等） |
| `domain-admin/Dockerfile.base` | 共享基础镜像 `domain-admin-base:deps-<lock-digest>`（Python 3.7 + 锁定生产依赖 + tzdata） |
| `domain-admin/Dockerfile` / `.worker` / `.scheduler` | 三个业务镜像，均 `FROM domain-admin-base:<tag>` |
| `domain-admin-web/Dockerfile` + `domain-admin-web/docker/nginx.conf` | 前端多阶段构建与 nginx 配置 |
| `build.sh` | 构建并打标签 `domain-admin-*` 镜像（用于推仓库 / K8s） |
| `k8s/` | Kubernetes 清单（`deploy.yaml`、`configmap.yaml` 等） |
| `docs/` | 2026-03-20 系列修复记录（worker/scheduler/MySQL） |
| `README.md` | 原有部署文档，本文件为其提炼与补充 |

## 3. 服务器前置条件

- Linux 服务器（x86_64 / arm64 均可），已安装 Docker Engine 20.10+ 与 **Docker Compose v2**（使用 `docker compose` 子命令，不是旧的 `docker-compose`）。
- Compose 的 build 配置使用默认 bridge 网络，**不要加 `network: host`**：Buildx 0.37.2+ 会要求 `network.host` entitlement，而 Compose <= v5.6.0 调用 bake 时不会传 `--allow=network.host`。独立的 `docker build --network host`（基础镜像构建、`build.sh`）不受影响。
- 服务器可访问外网：Docker Hub（`mysql:8.0`、`redis:7-alpine`、`python:3.7.17-slim-bullseye`、`node:18-alpine`、`nginx:1.27-alpine`）、PyPI、npm registry。
- 资源建议：≥ 2 核 4G 内存（前端 node 构建较吃内存），磁盘 ≥ 10GB。
- 防火墙只放行 `HTTP_PORT`（默认 8080），其余端口不对外。
- 已安装 `git`。

## 4. 首次部署（最短路径）

```bash
git clone <repo-url> sre-domain-check && cd sre-domain-check

cp .env.example .env
cp env/backend.env.example env/backend.env
# 编辑 .env 和 env/backend.env（见 4.1），保证密码 / 库名一致

# 校验 production.txt→lock 完整性、Python 3.7 hash dry-run，再按范围构建并发布
scripts/verify-production-lock.sh
scripts/release-compose.sh all
```

### 4.1 环境变量（两个文件均不入库）

`.env`：供 Compose 插值使用（`docker compose` 会自动读取项目根目录的 `.env`）：

```env
HTTP_PORT=8080
MYSQL_ROOT_PASSWORD=<强密码>
MYSQL_DATABASE=data
MYSQL_USER=domainadmin
MYSQL_PASSWORD=<强密码>
```

`env/backend.env`：注入 backend / worker / scheduler 容器。**必须写实际值**——Compose 不会对 env_file 内容做 compose.yaml 那样的 `${...}` 插值，写成 `${MYSQL_USER:-...}` 会原样传入容器导致连库失败。样例已提供与 `.env.example` 一致的测试默认值，生产环境需同步修改：

```env
APP_MODE=production
DB_CONNECT_URL=mysql://domainadmin:<与 MYSQL_PASSWORD 一致>@mysql:3306/data

ADMIN_USERNAME=admin
ADMIN_PASSWORD=<强密码>
ENABLED_REGISTER=true

CACHE_BACKEND=redis
ASYNC_TASK_BACKEND=redis
REDIS_URL=redis://redis:6379/0
REDIS_PREFIX=domain_admin
REDIS_CACHE_DB=0
REDIS_ASYNC_DB=1
REDIS_TASK_RESULT_TTL=86400
REDIS_LOCK_TTL=3600

SCHEDULER_ENABLED=false
SCHEDULER_ROLE=none

# 强烈建议显式设置：不设置时每个进程启动都会随机生成，重启后旧 token 全部失效
SECRET_KEY=<随机长字符串>
```

注意：

- `.env`、`env/backend.env` 已被 `.gitignore` 忽略，**绝不提交**。
- `DB_CONNECT_URL` 的用户名 / 密码 / 库名必须与 `.env` 中 `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DATABASE` 一致。
- `ADMIN_USERNAME` / `ADMIN_PASSWORD` 只在数据库**首次初始化**时写入管理员账号，之后修改 env 不会改已有密码。
- 不要创建 `domain-admin/.env`：`domain-admin/.dockerignore` 未排除 `.env`，它会被 COPY 进镜像并干扰 environs 的配置读取。

### 4.2 基础镜像必须先生成

`domain-admin/Dockerfile`、`.worker`、`.scheduler` 都通过 `BASE_IMAGE` 读取同一 `DOMAIN_ADMIN_BASE_IMAGE`。该镜像由 `production.lock` 的摘要命名：

```dockerfile
ARG BASE_IMAGE=domain-admin-base:deps-<lock-digest>
FROM ${BASE_IMAGE}
```

`docker compose build` **不会**构建 `Dockerfile.base`。使用 `scripts/build-images.sh deps` 或 `scripts/release-compose.sh deps` 会在 lock 变化或本地没有对应 digest base 时构建它；仅业务代码或前端代码更新则复用已有 base。

### 4.3 启动与验证

```bash
docker compose ps                     # 6 个服务，mysql/redis 应为 healthy
docker compose logs --tail 200 backend worker scheduler

curl -i http://127.0.0.1:8080/                              # 前端页面 200
curl -i http://127.0.0.1:8080/api/getSystemVersion          # API JSON
curl -i -X POST http://127.0.0.1:8080/api/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"<ADMIN_PASSWORD>"}'   # 返回 token
```

首次启动 MySQL 初始化较慢，`depends_on: condition: service_healthy` 会等 mysql/redis 健康后再启动业务容器。

## 5. 构建体系与镜像关系（重点，易踩坑）

- `Dockerfile.base` → `domain-admin-base:<tag>`：Python 3.7 + 系统依赖 + 生产依赖。
- Compose 用 4 个 Dockerfile 自行构建，镜像默认命名为 `<项目名>-<服务>`（例如 `sre-domain-check-backend`）。compose 文件里**没有** `image:` 字段，所以不会使用 `build.sh` 产出的镜像。
- `build.sh` 产出 `domain-admin-<service>:<tag>`，用于推镜像仓库 / K8s；若想让 Compose 复用，需要给 service 增加 `image:` 字段（当前未配置）。
- `build.sh` 默认参数有 bug：不带构建目标时 `TARGETS` 会变成 `"backend frontend worker scheduler"` 单个字符串并报「未知目标」。**必须显式传 target**：

```bash
./build.sh latest backend frontend worker scheduler
```

使用 `latest` 时 base 镜像名为 `domain-admin-base:latest`，与 Compose 的 build arg 一致。

### 更新代码后的重建

```bash
# 仅业务代码变更
docker compose up -d --build

# requirements/production.txt 变更（必须先重建 base，再重建业务镜像）
docker build --network host -t domain-admin-base:latest -f domain-admin/Dockerfile.base domain-admin
docker compose up -d --build
```

## 6. 日常运维命令

```bash
docker compose ps
docker compose logs -f --tail=200 backend
docker compose logs -f --tail=200 worker
docker compose logs -f --tail=200 scheduler
docker compose restart backend worker scheduler
docker compose stop
docker compose down            # 删除容器/网络，bind mount 数据保留
```

进入容器：

```bash
docker compose exec mysql mysql -udomainadmin -p data
docker compose exec redis redis-cli
docker compose exec redis redis-cli -n 1 keys 'domain_admin:*'
docker compose exec backend bash
```

## 7. 数据、持久化与备份

Bind mount（删除宿主机目录 = 丢数据）：

- `./data/mysql`：MySQL 数据目录
- `./data/redis`：Redis AOF
- `./data/backend` → `/app/database`：sqlite / acme / 缓存等
- `./data/temp` → `/app/temp`：临时文件
- `./logs/backend` → `/app/logs`：日志

备份示例：

```bash
docker compose exec -T mysql sh -c \
  'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --databases "$MYSQL_DATABASE"' \
  > backup-$(date +%F).sql

tar czf domain-admin-state-$(date +%F).tar.gz data logs env/backend.env .env
```

`docker compose down -v` 不会删除 bind mount；真正的数据丢失只发生在删除 `./data` / `./logs` 时。

## 8. 配置要点

- 调度：只有 `scheduler` 容器开启（`SCHEDULER_ENABLED=true`、`SCHEDULER_ROLE=worker`）。不要在 backend/worker 打开，否则重复调度。
- Redis：DB 0 为缓存，DB 1 为异步任务 / 锁 / 队列；key 前缀 `domain_admin`；RQ 队列名 `rq:queue:domain-admin`。
- MySQL：8.0，`mysql_native_password`，`utf8mb4` / `utf8mb4_unicode_ci`。
- Nginx：`/api/`、`/temp/` 反代 `http://backend:8000`，其余 `try_files` 回落到 `index.html`（SPA）。
- 前端构建参数 `VITE_APP_API=/api`、`VITE_BASE_URL=/`，改前端 API 前缀需同时改 nginx 配置。
- 对外端口改 `.env` 的 `HTTP_PORT` 后执行 `docker compose up -d`。

### 修改密码

- 改 `.env` 的 `MYSQL_PASSWORD` 只影响 MySQL **首次初始化**；已有 `./data/mysql` 时库内密码不变，需要：

```bash
docker compose exec mysql mysql -uroot -p
# ALTER USER 'domainadmin'@'%' IDENTIFIED BY '<new-password>'; FLUSH PRIVILEGES;
```

然后同步修改 `env/backend.env` 的 `DB_CONNECT_URL`，再 `docker compose up -d`。

- 管理员密码同理，只在首次建库写入；已初始化后请在页面里修改或直接改数据库（bcrypt 存储）。

## 9. 常见故障排查

1. **build 报 `pull access denied for domain-admin-base`**：没有先构建基础镜像，见 4.2。
2. **backend 连不上 MySQL（Access denied / Can't connect）**：`env/backend.env` 里 `DB_CONNECT_URL` 仍是 `${...}` 占位符，或密码 / 库名与 `.env` 不一致；确认 mysql 处于 `healthy`。
3. **宿主机 8080 被占用**：改 `.env` 的 `HTTP_PORT` 后 `docker compose up -d`。
4. **前端 502**：backend 未启动或不健康，查 `docker compose logs backend`。
5. **页面能开、接口 404**：确认前端构建参数 `VITE_APP_API=/api` 与 nginx 反代路径一致。
6. **worker 重复执行 / 队列积压**：清理 Redis 中残留 flag / lock / 队列（背景见 `docs/20260320-*`）：

```bash
docker compose exec redis sh -c "redis-cli -n 1 keys 'domain_admin:flag:pending:*' | xargs -r redis-cli -n 1 del"
docker compose exec redis sh -c "redis-cli -n 1 keys 'domain_admin:lock:execute:*' | xargs -r redis-cli -n 1 del"
docker compose exec redis redis-cli -n 1 del 'rq:queue:domain-admin'
```

7. **首次登录失败**：确认使用的密码是首次初始化时的 `ADMIN_PASSWORD`；如确实忘记且可丢弃数据，删除 `./data/mysql` 后重新 `docker compose up -d`。

## 10. 仓库约定 / 不要做

- 使用中文。
- `prd.md`、`spec.md`、`tasks.md` 固定在仓库根目录；其余 Markdown 放在 `docs/`，按「时间 + 序号 + 备注」命名（例如 `20261019-04-public-repo-cleanup.md`）。
- `README.md` 是总结与索引；`docs/` 有更新时同步更新 README。
- 文档中不得出现真实账号密码，示例统一用占位符。
- 修改前先查看 `docs/` 中最新的更新记录；修复类改动需在 `docs/` 留记录并在 `README.md` 增加条目。
- 代码尽量拆分，避免单文件过长。
- 不提交 `.env`、`env/backend.env`、`data/`、`logs/`。
- 不给 MySQL / Redis 映射宿主机端口。
- 不在 backend / worker 打开 scheduler。
- 不删除 Compose 中的 `BASE_IMAGE` build arg。
- 不要无参数运行 `./build.sh`（参数解析有 bug）。
- `.kiro/` 的有效内容已合并到根目录 `prd.md` / `spec.md` / `tasks.md`，目录已删除，不要再引用。
- `.codex/` 与 `openspec/` 保留，用于 Codex / OpenSpec 继续开发；新建 change 放在 `openspec/changes/`。
- `domain-admin/http/` 是手工 API 调试样例；请求头使用 `{{token}}`，本地真实 token 放 `domain-admin/http/http-client.private.env.json`（已 gitignore）。

## 11. 相关文档

- `README.md`：镜像构建、推送、Compose / K8s 部署
- `AGENTS.md`：Codex 协作说明（项目结构、命令、开发约定、安全红线）
- `openspec/config.yaml`、`.codex/skills/openspec-*`：OpenSpec 变更流程
- `prd.md`：部署 PRD（目标、范围、验收标准）
- `spec.md`：部署技术规格（架构、构建、配置、升级回滚、备份）
- `tasks.md`：部署任务清单（可勾选执行）
- `docs/20261019-04-public-repo-cleanup.md`：公开仓库清理与发布清单（删除候选、脱敏、历史重建）
- `k8s/deploy.yaml`、`k8s/configmap.yaml`、`k8s/secret.yaml`、`k8s/svc.yaml`、`k8s/router.yaml`：Kubernetes 部署
- `docs/20260320-*`：worker / scheduler / MySQL 重连与重复执行修复记录

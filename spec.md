# Docker Compose 服务器部署技术规格

- 文档编号：20261019-02
- 关联文档：
  - PRD：[prd.md](prd.md)
  - 任务清单：[tasks.md](tasks.md)
- 说明：本文不含任何真实账号密码，示例值一律使用占位符。

## 1. 总体架构

```
                        HTTP :${HTTP_PORT:-8080}
                                 │
                                 ▼
                 ┌───────────────────────────────┐
                 │ frontend (nginx:1.27-alpine)  │
                 │  /      → /usr/share/nginx/html│
                 │  /api/  → backend:8000/api/    │
                 │  /temp/ → backend:8000/temp/   │
                 └───────────────┬───────────────┘
                                 │ domain-admin-net
                                 ▼
                 ┌───────────────────────────────┐
                 │ backend (gunicorn :8000)      │
                 │ Flask domain_admin.main:app   │
                 └───────┬───────────────┬───────┘
                         │               │
              ┌──────────▼─────┐   ┌─────▼────────────┐
              │ mysql:8.0      │   │ redis:7-alpine   │
              │ 业务数据库      │   │ 缓存/队列/锁      │
              └────────────────┘   └─────┬────────────┘
                                         │
                          ┌──────────────┴──────────────┐
                          ▼                             ▼
                 ┌─────────────────┐          ┌──────────────────┐
                 │ worker (RQ)     │          │ scheduler        │
                 │ 异步任务消费     │          │ APScheduler 调度  │
                 └─────────────────┘          └──────────────────┘
```

- 所有服务位于同一自定义 bridge 网络 `domain-admin-net`，通过服务名互相访问。
- 只有 `frontend` 发布宿主机端口，其余服务仅在容器网络内可达。

## 2. 服务清单

| 服务 | 构建上下文 / 镜像 | 启动命令 | 端口 | 挂载 | 健康检查 |
| --- | --- | --- | --- | --- | --- |
| `mysql` | `mysql:8.0` | 默认 + `mysql_native_password`、`utf8mb4` | 不发布 | `./data/mysql:/var/lib/mysql` | `mysqladmin ping`，10s 间隔，20 次重试 |
| `redis` | `redis:7-alpine` | `redis-server --appendonly yes` | 不发布 | `./data/redis:/data` | `redis-cli ping`，10s 间隔，20 次重试 |
| `backend` | `./domain-admin` + `Dockerfile` | `gunicorn --bind [::]:8000 --timeout 120 domain_admin.main:app` | expose 8000 | `data/backend→/app/database`、`logs/backend→/app/logs`、`data/temp→/app/temp` | 无（由 frontend 反代探活） |
| `worker` | `./domain-admin` + `Dockerfile.worker` | `python -m domain_admin.worker` | 无 | 同上 | 无 |
| `scheduler` | `./domain-admin` + `Dockerfile.scheduler` | `python -m domain_admin.scheduler` | 无 | 同上 | 无 |
| `frontend` | `./domain-admin-web` + `Dockerfile` | nginx 默认启动 | `${HTTP_PORT:-8080}:80` | 无（静态资源打进镜像） | 无 |

- 所有服务 `restart: unless-stopped`。
- `backend` / `worker` / `scheduler` 均 `TZ=Asia/Shanghai`。
- 容器名固定为 `domain-admin-<service>`，便于运维脚本定位。

## 3. 镜像与构建

### 3.1 镜像层次

```
python:3.7.17-slim-bullseye
        │  Dockerfile.base（系统依赖 + requirements/production.txt）
        ▼
domain-admin-base:latest
        │
        ├── Dockerfile           → backend 镜像
        ├── Dockerfile.worker    → worker 镜像
        └── Dockerfile.scheduler → scheduler 镜像

node:18-alpine ──build──▶ nginx:1.27-alpine + dist → frontend 镜像
```

### 3.2 构建规则

1. **必须先构建基础镜像**。三个后端 Dockerfile 的 `FROM ${BASE_IMAGE}` 默认值为 `domain-admin-base:latest`，Compose 不会构建 `Dockerfile.base`。

   ```bash
   docker build --network host \
     -t domain-admin-base:latest \
     -f domain-admin/Dockerfile.base \
     domain-admin
   ```

2. Compose 构建的镜像默认命名为 `<项目名>-<服务>`（项目名默认为目录名，例如 `sre-domain-check-backend`）。`docker-compose.yml` 中没有 `image:` 字段，因此 Compose 不会复用 `build.sh` 产出的 `domain-admin-*` 镜像。
3. `build.sh` 用于构建 `domain-admin-<service>:<tag>`，供推送镜像仓库 / K8s 使用。其默认参数解析有缺陷：不传构建目标时会把默认目标拼成一个字符串并报「未知目标」。必须显式传 target：

   ```bash
   ./build.sh latest backend frontend worker scheduler
   ```

4. 构建统一使用 `network: host`（Compose build 配置）或 `docker build --network host`，确保 apt / pip / npm 下载正常。

### 3.3 重建策略

| 变更类型 | 操作 |
| --- | --- |
| 仅业务代码 | `docker compose up -d --build` |
| `requirements/production.txt` | 先重建 `domain-admin-base:latest`，再 `docker compose up -d --build` |
| 前端代码 / 依赖 | `docker compose up -d --build`（frontend 会重新执行 node 构建） |

## 4. 配置管理

### 4.1 两个环境文件

| 文件 | 使用方 | 内容 | 是否入库 |
| --- | --- | --- | --- |
| `.env` | Docker Compose 插值 | `HTTP_PORT`、MySQL 初始化账号 / 库名 | 否 |
| `env/backend.env` | backend / worker / scheduler 容器 | 数据库连接、Redis、管理员初始化、调度开关、`SECRET_KEY` | 否 |

`.env` 示例（值为占位符）：

```env
HTTP_PORT=8080
MYSQL_ROOT_PASSWORD=<root-password>
MYSQL_DATABASE=<database>
MYSQL_USER=<db-user>
MYSQL_PASSWORD=<db-password>
```

`env/backend.env` 关键项（值为占位符）：

```env
APP_MODE=production
DB_CONNECT_URL=mysql://<db-user>:<db-password>@mysql:3306/<database>

ADMIN_USERNAME=<admin-user>
ADMIN_PASSWORD=<admin-password>
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

SECRET_KEY=<random-secret>
```

### 4.2 配置约束

1. **`env_file` 内容不做 Compose 变量插值**：`DB_CONNECT_URL` 必须写死实际值，不能写成 `${MYSQL_USER:-...}` 这类占位符（仓库中的 `env/backend.env.example` 已提供可用的测试默认值）。
2. `.env` 中的 `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DATABASE` 必须与 `DB_CONNECT_URL` 完全一致。
3. `SECRET_KEY` 必须显式设置。不设置时应用每个进程启动都会随机生成，重启后旧 token 全部失效。
4. `ADMIN_USERNAME` / `ADMIN_PASSWORD` 只在数据库首次初始化时写入管理员账号，后续修改环境变量不会更新已有账号。
5. 不要创建 `domain-admin/.env`：`domain-admin/.dockerignore` 未排除 `.env`，会被打进镜像并干扰 environs 的配置读取。
6. `.env`、`env/backend.env` 权限建议设置为 `600`，且确认被 git 忽略：

   ```bash
   chmod 600 .env env/backend.env
   git check-ignore -v .env env/backend.env
   ```

## 5. 网络与端口

| 项目 | 规格 |
| --- | --- |
| 网络 | `domain-admin-net`（自定义 bridge） |
| 服务发现 | 容器内通过 `mysql`、`redis`、`backend` 等服务名访问 |
| 宿主机端口 | 仅 `${HTTP_PORT:-8080}` |
| 内部端口 | backend 8000；mysql 3306；redis 6379 |
| 防火墙 | 仅放行 `HTTP_PORT`；SSH 按运维规范单独放行 |

禁止为 `mysql` / `redis` 增加 `ports` 映射；如需临时调试，使用 `docker compose exec`。

## 6. 存储与持久化

| 宿主机路径 | 容器路径 | 内容 | 是否必须备份 |
| --- | --- | --- | --- |
| `./data/mysql` | `/var/lib/mysql` | MySQL 数据文件 | 是（优先逻辑备份） |
| `./data/redis` | `/data` | Redis AOF | 否（可重建，队列数据按需） |
| `./data/backend` | `/app/database` | sqlite（如使用）、ACME 证书、缓存 | 是 |
| `./data/temp` | `/app/temp` | 临时文件 | 否 |
| `./logs/backend` | `/app/logs` | 应用日志 | 按需 |

说明：

- Docker 会自动创建不存在的目录，默认属主为 root；不要手工修改 MySQL 数据目录内容。
- `docker compose down` 不会删除 bind mount；只有删除宿主机 `data/`、`logs/` 才会丢数据。
- 运行目录由应用以 `os.getcwd()`（容器内 `/app`）为基准生成，因此挂载点必须与上表一致。

## 7. 启动顺序与健康检查

```
mysql healthy ──┐
                ├──▶ backend / worker / scheduler
redis healthy ──┘

backend ──▶ frontend
```

- `backend` / `worker` / `scheduler` 通过 `depends_on.condition: service_healthy` 等待 MySQL 和 Redis。
- MySQL healthcheck：`mysqladmin ping -h 127.0.0.1`，间隔 10s，超时 5s，重试 20 次。
- Redis healthcheck：`redis-cli ping`，间隔 10s，超时 5s，重试 20 次。
- 首次启动包含镜像拉取、MySQL 初始化，耗时可能数分钟；健康检查未通过前业务容器不会启动，属正常现象。

## 8. 运行时角色与调度

| 容器 | `SCHEDULER_ENABLED` | `SCHEDULER_ROLE` | 说明 |
| --- | --- | --- | --- |
| `backend` | `false` | `none` | 仅提供 API，不参与调度 |
| `worker` | `false` | `none` | 仅消费异步任务 |
| `scheduler` | `true` | `worker` | 唯一调度实例 |

- Redis DB 0：缓存；DB 1：异步任务、任务锁、调度锁。
- 关键 key 前缀：`domain_admin:`；RQ 队列：`rq:queue:domain-admin`。
- 严禁在 backend / worker 打开 scheduler，否则多实例重复调度。

## 9. 部署流程

```bash
# 1. 获取代码
git clone <repo-url> sre-domain-check
cd sre-domain-check

# 2. 准备配置
cp .env.example .env
cp env/backend.env.example env/backend.env
# 按第 4 节修改，写死 DB_CONNECT_URL，设置 SECRET_KEY / 管理员密码
chmod 600 .env env/backend.env

# 3. 构建基础镜像
docker build --network host \
  -t domain-admin-base:latest \
  -f domain-admin/Dockerfile.base \
  domain-admin

# 4. 构建并启动
docker compose up -d --build

# 5. 查看状态
docker compose ps
```

## 10. 验证方案

```bash
# 前端
curl -i http://127.0.0.1:${HTTP_PORT:-8080}/

# 系统版本
curl -i http://127.0.0.1:${HTTP_PORT:-8080}/api/getSystemVersion

# 登录（密码为部署时设置的管理员密码）
curl -i -X POST http://127.0.0.1:${HTTP_PORT:-8080}/api/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"<admin-user>","password":"<admin-password>"}'

# 服务日志
docker compose logs --tail 200 backend worker scheduler

# 端口检查：应只看到 HTTP_PORT
ss -lntp | grep -E ':8080|:3306|:6379'
```

预期结果：

- `/` 返回 200 且为前端 HTML。
- `/api/getSystemVersion` 返回 JSON。
- `/api/login` 返回 token，无鉴权错误。
- `docker compose ps` 中 mysql / redis 为 healthy，6 个容器均为 Up。
- 宿主机 3306 / 6379 无监听。

## 11. 升级与回滚

### 11.1 升级

```bash
# 升级前备份（见第 12 节）
docker compose exec -T mysql sh -c \
  'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --databases "$MYSQL_DATABASE"' \
  > backup-before-upgrade-$(date +%F).sql

git pull
# requirements 变更时先重建 base
docker build --network host -t domain-admin-base:latest -f domain-admin/Dockerfile.base domain-admin
docker compose up -d --build
docker compose ps
```

### 11.2 回滚

Compose 构建的镜像 tag 默认为 `latest`，升级前先给当前镜像打快照：

```bash
for svc in backend frontend worker scheduler; do
  docker image tag "sre-domain-check-${svc}:latest" "sre-domain-check-${svc}:rollback-$(date +%Y%m%d)"
done
```

回滚时恢复 tag 并用现有镜像启动：

```bash
for svc in backend frontend worker scheduler; do
  docker image tag "sre-domain-check-${svc}:rollback-<date>" "sre-domain-check-${svc}:latest"
done
docker compose up -d --no-build
```

注意：

- 若升级包含数据库迁移，回滚镜像前必须评估迁移是否可逆，必要时同时恢复数据库备份。
- 项目名不是 `sre-domain-check` 时（如设置了 `COMPOSE_PROJECT_NAME`），镜像名前缀需相应调整。
- 更规范的做法是后续为 Compose 服务增加 `image:` 字段并使用版本 tag，本次不强制。

## 12. 备份与恢复

### 12.1 备份

```bash
# MySQL 逻辑备份（在容器内使用其环境变量）
docker compose exec -T mysql sh -c \
  'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --databases "$MYSQL_DATABASE"' \
  > backup-$(date +%F).sql

# 运行目录 + 配置
tar czf domain-admin-state-$(date +%F).tar.gz data logs env/backend.env .env
```

### 12.2 恢复

```bash
# 1. 停止业务容器
docker compose stop backend worker scheduler frontend

# 2. 恢复 MySQL
docker compose exec -T mysql sh -c \
  'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' \
  < backup-<date>.sql

# 3. 按需恢复 data/backend 等目录

# 4. 启动
docker compose start backend worker scheduler frontend
```

建议每季度至少做一次恢复演练；备份文件应异地保存并设置保留周期。

## 13. 安全设计

- 仅暴露 `HTTP_PORT`；MySQL / Redis 不发布宿主机端口。
- `.env`、`env/backend.env` 使用强密码并设置 `600` 权限，禁止提交到 git。
- 必须显式设置 `SECRET_KEY`；泄露或轮换后所有已签发 token 失效，属预期行为。
- 管理员密码只在首次初始化时生效，部署时应直接设置为强密码。
- 文档、工单、聊天记录中不得出现真实账号密码。
- 有 Docker 权限的账号等同于 root 权限，服务器登录与 Docker 权限需按最小化原则管理。
- 如需公网访问，建议在前面加 HTTPS 终止（Nginx / SLB），并限制来源 IP。

## 14. 已知限制与易错点

| 编号 | 问题 | 处理方式 |
| --- | --- | --- |
| K1 | 未构建 `domain-admin-base:latest`，构建报 `pull access denied` | 先执行 base 镜像构建 |
| K2 | `env/backend.env` 保留 `${...}` 占位符，backend 连库失败 | 写死实际用户名 / 密码 / 库名 |
| K3 | `./build.sh` 无参数调用报「未知目标」 | 显式传 `latest backend frontend worker scheduler` |
| K4 | 以为 `build.sh` 的镜像会被 Compose 使用 | Compose 用 `<项目名>-<服务>` 自行构建 |
| K5 | 已有数据卷后修改 `MYSQL_PASSWORD` 不生效 | 需 `ALTER USER` 修改库内密码并同步 `DB_CONNECT_URL` |
| K6 | 修改 `ADMIN_PASSWORD` 后旧账号密码不变 | 只在首次初始化生效，后续在页面或数据库修改 |
| K7 | 未设置 `SECRET_KEY` 导致重启后登录态失效 | 显式设置固定随机值 |
| K8 | 单机部署无高可用 | 通过备份、恢复演练、外部监控降低风险 |
| K9 | 前端构建内存不足 | 服务器至少 4G 内存，或临时增加 swap |

## 15. 文件清单

| 文件 | 作用 |
| --- | --- |
| `docker-compose.yml` | 生产编排 |
| `.env.example` | Compose 变量样例 |
| `env/backend.env.example` | 业务环境变量样例 |
| `domain-admin/Dockerfile.base` | 共享基础镜像 |
| `domain-admin/Dockerfile` / `.worker` / `.scheduler` | 后端三类镜像 |
| `domain-admin-web/Dockerfile` | 前端镜像 |
| `domain-admin-web/docker/nginx.conf` | 前端反向代理配置 |
| `build.sh` | 镜像构建脚本（推仓库 / K8s） |
| `docker-compose.smoke.yml` + `Dockerfile.app` | 单容器冒烟方案（非生产） |
| `prd.md`、`spec.md`、`tasks.md` | 部署 PRD / 技术规格 / 任务清单（仓库根目录） |
| `docs/20261019-04-public-repo-cleanup.md` | 公开仓库清理与发布清单 |

## 16. 应用技术栈

> 合并自原 `.kiro/steering/tech.md`，供排查构建与依赖问题时参考。

### 16.1 后端（`domain-admin/`）

- 语言：Python 3.7+
- Web 框架：Flask（自定义 FlaskApp 封装）
- ORM：Peewee（通过 `playhouse.db_url.connect` 连接数据库）
- 数据库：MySQL 8.0（开发时可用 SQLite）
- 缓存 / 队列：Redis 7（diskcache 作为本地备选）
- 异步任务：RQ（Redis Queue）
- 定时调度：APScheduler
- WSGI 服务器：Gunicorn
- 证书签发：acme + pyOpenSSL
- 远程部署：Fabric（SSH）
- 云服务 SDK：阿里云（alidns、cdn、dcdn、cas、oss2）、腾讯云
- 认证：PyJWT + bcrypt
- 监控：prometheus-client

### 16.2 前端（`domain-admin-web/`）

- 框架：Vue 3（Composition API）
- 构建工具：Vite 3
- UI 组件库：Element Plus
- 状态管理：Pinia
- 路由：Vue Router 4
- HTTP 客户端：Axios
- 样式：Tailwind CSS + Less
- 图表：ECharts
- 代码编辑器：CodeMirror 6

### 16.3 基础设施

- 容器化：Docker + Docker Compose
- 前端反向代理：Nginx
- 编排：Kubernetes（`k8s/` 目录）
- 包发布：PyPI（`setup.py` + twine）

## 17. 代码结构与编码约定

> 合并自原 `.kiro/steering/structure.md`。

### 17.1 后端分层

```
请求 → router/api_map.py（路由表）→ api/*（参数校验）→ service/*（业务逻辑）→ model/*（数据访问）
```

- 路由采用平铺字典映射，不使用 Flask Blueprint。
- 每个请求通过 `before_request` 钩子解析 Token 并打开数据库连接。
- 每个请求结束通过 `teardown_request` 关闭数据库连接。
- API 函数直接返回 dict，由自定义 FlaskApp 统一序列化为 JSON。
- 模型类继承 `BaseModel`，表名以 `tb_` 前缀命名。
- API 函数命名：`动词_资源_by_条件`（如 `get_domain_list`、`update_domain_by_id`）。
- 路由 URL 命名：`/api/驼峰动词资源`（如 `/api/getDomainList`）。
- 配置通过环境变量注入，默认值定义在 `config/default_config.py`。
- 后端文件头部统一包含 `# -*- coding: utf-8 -*-` 和 `from __future__ import` 兼容声明。

### 17.2 前端结构

- `src/views/` 按功能模块组织页面。
- `src/api/` 与后端 API 一一对应。
- `src/store/` 使用 Pinia 管理全局状态。
- Element Plus 组件按需自动导入（unplugin-vue-components）。

## 18. 仓库文档约定

> 合并自原 `.kiro/steering/work-style.md`。

- 使用中文。
- `prd.md`、`spec.md`、`tasks.md` 固定在仓库根目录；其余新增 Markdown 放在 `docs/`。
- `README.md` 是总结和索引，详细内容放 `docs/`；`docs/` 有更新时同步更新 `README.md`。
- 文档中不包含账号密码，示例一律使用占位符。
- 每次新增文档按「时间 + 序号 + 备注」命名，例如 `20261019-04-public-repo-cleanup.md`。
- 修改前先查看 `docs/` 中最新的更新记录。
- 代码尽量拆分，避免单文件过长，便于理解运行流程。
- `.codex/` 与 `openspec/` 保留用于 Codex / OpenSpec 工作流；`domain-admin/http/` 的本地 token 放 `http-client.private.env.json`，不入库。

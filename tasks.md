# Docker Compose 服务器部署任务清单

- 文档编号：20261019-03
- 关联文档：
  - PRD：[prd.md](prd.md)
  - 技术规格：[spec.md](spec.md)
- 使用方式：按阶段执行，完成后将 `[ ]` 改为 `[x]`；命令中的 `<>` 为占位符，禁止在文档中填写真实密码。
- 执行约定（合并自原 `.kiro/steering/work-style.md`）：
  - 使用中文；`prd.md` / `spec.md` / `tasks.md` 固定在仓库根目录，其余新增 Markdown 放在 `docs/` 并按「时间 + 序号 + 备注」命名。
  - `README.md` 是总结与索引；`docs/` 有更新时同步更新 README。
  - 文档中不得出现真实账号密码。
  - 修改前先查看 `docs/` 中最新的更新记录。
  - 代码尽量拆分，避免单文件过长。

## 0. 前置确认

- [ ] **T0-1 确认服务器条件**：Linux x86_64 / arm64，≥ 2 核 4G，磁盘可用 ≥ 10GB。
- [ ] **T0-2 确认 Docker 环境**：Docker Engine 20.10+，并支持 `docker compose`（v2）。
  ```bash
  docker version
  docker compose version
  ```
- [ ] **T0-3 确认外网访问**：Docker Hub、PyPI、npm registry 可访问；`docker build --network host` 可用。
- [ ] **T0-4 确认防火墙**：仅放行 `HTTP_PORT`（默认 8080）与运维 SSH；3306 / 6379 不对外。
- [ ] **T0-5 获取代码并记录版本**：
  ```bash
  git clone <repo-url> sre-domain-check
  cd sre-domain-check
  git rev-parse HEAD
  ```

## 1. 配置准备

- [ ] **T1-1 创建 Compose 环境文件**：
  ```bash
  cp .env.example .env
  ```
- [ ] **T1-2 创建业务环境文件**：
  ```bash
  cp env/backend.env.example env/backend.env
  ```
- [ ] **T1-3 设置 MySQL 凭据**：在 `.env` 中设置 `MYSQL_ROOT_PASSWORD`、`MYSQL_USER`、`MYSQL_PASSWORD`、`MYSQL_DATABASE`，全部使用强密码。
- [ ] **T1-4 写死数据库连接串**：`env/backend.env` 中 `DB_CONNECT_URL` 改为实际值（用户名 / 密码 / 库名与 `.env` 一致），不要保留 `${...}` 占位符。
- [ ] **T1-5 设置 `SECRET_KEY`**：使用随机长字符串，避免重启后 token 失效。
  ```bash
  openssl rand -hex 32
  ```
- [ ] **T1-6 设置管理员账号**：`ADMIN_USERNAME` / `ADMIN_PASSWORD` 使用强密码；该配置只在首次初始化数据库时生效。
- [ ] **T1-7 确认 Redis / 调度配置**：`CACHE_BACKEND=redis`、`ASYNC_TASK_BACKEND=redis`、`SCHEDULER_ENABLED=false`、`SCHEDULER_ROLE=none`。
- [ ] **T1-8 收紧文件权限**：
  ```bash
  chmod 600 .env env/backend.env
  ```
- [ ] **T1-9 确认配置不入库**：
  ```bash
  git check-ignore -v .env env/backend.env
  # 两项均应输出匹配的 .gitignore 规则
  ```

## 2. 镜像构建

- [ ] **T2-1 构建共享基础镜像**（首次部署、依赖变更时必做）：
  ```bash
  docker build --network host \
    -t domain-admin-base:latest \
    -f domain-admin/Dockerfile.base \
    domain-admin
  ```
- [ ] **T2-2 构建 Compose 业务镜像**：
  ```bash
  docker compose build
  ```
- [ ] **T2-3 确认镜像存在**：应看到 `<项目名>-backend`、`<项目名>-frontend`、`<项目名>-worker`、`<项目名>-scheduler`，以及 `domain-admin-base:latest`。
  ```bash
  docker images | grep -E 'domain-admin-base|backend|frontend|worker|scheduler'
  ```
- [ ] **T2-4（可选）构建仓库 / K8s 镜像**：如需推送镜像仓库，显式传 target；不要无参数运行 `build.sh`。
  ```bash
  ./build.sh latest backend frontend worker scheduler
  ```

## 3. 服务启动

- [ ] **T3-1 启动全部服务**：
  ```bash
  docker compose up -d
  ```
- [ ] **T3-2 等待依赖健康**：`mysql`、`redis` 状态应为 `healthy`。
  ```bash
  docker compose ps
  ```
- [ ] **T3-3 确认 6 个容器均为 Up**：mysql、redis、backend、worker、scheduler、frontend。
- [ ] **T3-4 检查启动日志无异常**：
  ```bash
  docker compose logs --tail 200 mysql
  docker compose logs --tail 200 backend
  docker compose logs --tail 200 worker
  docker compose logs --tail 200 scheduler
  docker compose logs --tail 200 frontend
  ```
- [ ] **T3-5 确认调度角色**：scheduler 日志包含调度启动记录；backend / worker 无调度启动。

## 4. 部署验证

- [ ] **T4-1 前端页面**：返回 200 和 HTML。
  ```bash
  curl -i http://127.0.0.1:${HTTP_PORT:-8080}/
  ```
- [ ] **T4-2 系统版本接口**：返回 JSON。
  ```bash
  curl -i http://127.0.0.1:${HTTP_PORT:-8080}/api/getSystemVersion
  ```
- [ ] **T4-3 登录接口**：返回 token。
  ```bash
  curl -i -X POST http://127.0.0.1:${HTTP_PORT:-8080}/api/login \
    -H 'Content-Type: application/json' \
    -d '{"username":"<admin-user>","password":"<admin-password>"}'
  ```
- [ ] **T4-4 端口暴露检查**：宿主机只应监听 `HTTP_PORT`，无 3306 / 6379。
  ```bash
  ss -lntp | grep -E ':<HTTP_PORT>|:3306|:6379'
  ```
- [ ] **T4-5 持久化验证**：
  ```bash
  docker compose down
  docker compose up -d
  # 重新登录，确认原有域名 / 用户数据仍存在
  ```
- [ ] **T4-6 日志落盘验证**：`logs/backend` 有日志文件产生。

## 5. 运维交接

- [ ] **T5-1 首次备份**：
  ```bash
  docker compose exec -T mysql sh -c \
    'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --databases "$MYSQL_DATABASE"' \
    > backup-$(date +%F).sql
  tar czf domain-admin-state-$(date +%F).tar.gz data logs env/backend.env .env
  ```
- [ ] **T5-2 恢复演练**：在测试目录或测试库按技术规格第 12 节恢复备份，确认可用。
- [ ] **T5-3 升级流程确认**：升级前打镜像快照、备份数据库，升级后重新执行第 4 节验证。
- [ ] **T5-4 回滚流程确认**：按技术规格 11.2 恢复镜像 tag 并 `docker compose up -d --no-build`。
- [ ] **T5-5 日常巡检项落地**：`docker compose ps`、磁盘使用率、`logs/backend` 错误日志、备份任务。
- [ ] **T5-6 文档归档**：确认 README 已索引本组文档，本次变更记录已归档到 `docs/`。

## 6. 可选后续（不在本次范围）

- [ ] **T6-1 HTTPS / 域名接入**：前置 Nginx 或 SLB 终止 TLS。
- [ ] **T6-2 CI/CD**：自动构建、推送、部署。
- [ ] **T6-3 监控告警**：采集 Prometheus 指标并配置告警。
- [ ] **T6-4 镜像版本化**：为 Compose 服务增加 `image:` 字段，使用固定 tag 替代 `latest`。

## 完成定义（DoD）

- 第 0 ～ 4 节全部勾选，PRD 中 AC-1 ～ AC-7 全部通过。
- 第 5 节备份、恢复演练、升级 / 回滚流程确认完成（AC-8）。
- README 文档索引已更新，所有文档不含真实账号密码（AC-9）。

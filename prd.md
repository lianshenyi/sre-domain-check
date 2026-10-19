# Docker Compose 服务器部署 PRD

- 文档编号：20261019-01
- 状态：待评审
- 关联文档：
  - 技术规格：[spec.md](spec.md)
  - 任务清单：[tasks.md](tasks.md)
- 说明：本文不含任何真实账号密码，示例值一律使用占位符。

## 1. 产品概述与背景

### 1.1 产品概述

> 合并自原 `.kiro/steering/product.md`。

Domain Admin 是一个域名与 SSL 证书管理平台，用于监控域名到期时间、SSL 证书状态，并支持自动签发和部署证书。

核心功能：

- SSL 证书到期监控与告警通知
- 域名注册信息（WHOIS）到期监控
- ACME 协议自动签发 Let's Encrypt 证书
- 证书部署到远程主机（SSH / Fabric）
- 证书部署到阿里云 CDN / DCDN / OSS
- HTTP 站点可用性监控
- 多用户与分组权限管理
- 定时调度任务（APScheduler）
- Prometheus 指标暴露（`/metrics`）
- 多语言支持（i18n）
- 微信域名封禁状态检查

部署架构由 4 个业务服务组成：backend（Flask API，Gunicorn）、frontend（Vue 3 SPA，Nginx）、worker（RQ 异步任务消费者）、scheduler（APScheduler 定时调度）；依赖 MySQL 8.0、Redis 7。

### 1.2 背景

本仓库已具备 `docker-compose.yml`、多个 Dockerfile 以及 K8s 清单，并已在开发机上验证过前端 + 后端最小链路。现在需要在一台独立的 Linux 服务器上，以 Docker Compose 方式完整部署 domain-admin，作为生产 / 预生产环境使用。

现有 `README.md` 和部署笔记偏操作说明，缺少目标、范围、验收标准与任务拆解，容易出现「容器起来了」但无法判断是否真正交付完成的问题。

## 2. 目标

- G1：在一台干净的 Linux 服务器上，按文档可重复完成部署，首次启动成功。
- G2：通过 `docker compose up -d` 拉起全部 6 个服务，无需手工进入容器修改配置。
- G3：数据、日志、临时文件全部持久化到宿主机，容器重建不丢数据。
- G4：部署后可通过 HTTP 完成页面访问、API 调用和管理员登录验证。
- G5：形成可交接的 PRD / 技术规格 / 任务清单 / 运维说明。

## 3. 用户与场景

| 角色 | 场景 |
| --- | --- |
| 运维 | 首次部署、日常巡检、升级、备份、故障处理 |
| 开发 | 在服务器环境复现问题、验证修复版本 |
| 安全 / 审计 | 确认端口暴露、凭据管理、数据留存符合要求 |

## 4. 范围

### 4.1 In scope

- 单机 Docker Compose 部署：`mysql`、`redis`、`backend`、`worker`、`scheduler`、`frontend`
- 环境变量与密钥管理
- 镜像构建流程（含共享基础镜像 `domain-admin-base`）
- 健康检查、启动顺序、容器重启策略
- 数据持久化、备份与恢复
- 版本升级与回滚
- 部署验证与验收

### 4.2 Out of scope

- Kubernetes 部署（`k8s/` 已单独维护）
- HTTPS / 域名接入（由前置 Nginx / SLB 或后续迭代负责）
- CI/CD 流水线建设
- 多节点、高可用、读写分离
- 监控告警平台对接（应用已暴露 Prometheus 指标，采集侧不在本次范围）

## 5. 功能需求

| 编号 | 需求 | 优先级 |
| --- | --- | --- |
| FR-1 | 通过 `docker compose up -d` 启动 6 个服务，容器名固定为 `domain-admin-*` | P0 |
| FR-2 | 配置外置：Compose 级使用 `.env`，业务级使用 `env/backend.env`，两个文件均不入库 | P0 |
| FR-3 | `data/`、`logs/` 下数据通过 bind mount 持久化，`down` / 重建容器不丢数据 | P0 |
| FR-4 | MySQL / Redis 配置健康检查，业务容器在其健康后启动 | P0 |
| FR-5 | scheduler 仅在 `scheduler` 容器运行，backend / worker 关闭调度，避免重复执行 | P0 |
| FR-6 | frontend 由 nginx 托管静态资源，并反代 `/api`、`/temp` 到 backend | P0 |
| FR-7 | 支持查看容器状态、健康状态与各服务日志 | P1 |
| FR-8 | 支持代码升级后重建镜像并重启，失败时可回滚到上一版本 | P1 |
| FR-9 | 支持 MySQL 与运行目录备份、恢复 | P1 |
| FR-10 | 安全基线：仅暴露 HTTP 端口，MySQL / Redis 不映射宿主机，凭据不出现在代码和文档中 | P0 |

## 6. 非功能需求

| 编号 | 类别 | 要求 |
| --- | --- | --- |
| NFR-1 | 安全 | 仅 `HTTP_PORT` 对外；`env/backend.env`、`.env` 权限建议 600；必须显式设置 `SECRET_KEY`；禁止使用默认弱密码 |
| NFR-2 | 可用性 | 所有服务 `restart: unless-stopped`；MySQL / Redis 健康检查失败时不启动业务容器 |
| NFR-3 | 性能与容量 | 建议 ≥ 2 核 4G、磁盘 ≥ 10GB；前端 node 构建需预留内存 |
| NFR-4 | 兼容性 | Linux x86_64 / arm64；Docker Engine 20.10+；Docker Compose v2 |
| NFR-5 | 可维护性 | 部署、升级、回滚、备份均有文档和明确命令；变更记录归档到 `docs/` |
| NFR-6 | 可观测性 | 可通过 `docker compose ps` / `logs` 判断服务状态；应用日志落盘到 `logs/backend` |

## 7. 验收标准

| 编号 | 验收项 | 通过标准 |
| --- | --- | --- |
| AC-1 | 服务状态 | `docker compose ps` 显示 6 个容器 Up，`mysql` / `redis` 为 healthy |
| AC-2 | 页面访问 | `curl -i http://<host>:<HTTP_PORT>/` 返回 200 和前端 HTML |
| AC-3 | API 可用 | `GET /api/getSystemVersion` 返回正常 JSON |
| AC-4 | 登录可用 | `POST /api/login` 使用部署时设置的管理员账号返回 token |
| AC-5 | 数据持久化 | `docker compose down` 后重新 `up -d`，已有域名 / 用户数据仍存在 |
| AC-6 | 端口暴露 | 宿主机仅监听 `HTTP_PORT`；MySQL(3306)、Redis(6379) 未监听在宿主机 |
| AC-7 | 角色正确 | scheduler 日志有调度启动记录；backend / worker 无重复调度 |
| AC-8 | 备份可用 | 按文档生成的备份文件可成功恢复到演练环境 |
| AC-9 | 文档合规 | README 有文档索引；所有文档不含真实账号密码 |

## 8. 假设与依赖

- 服务器为 Linux，可执行 `docker build --network host`。
- 服务器可访问 Docker Hub、PyPI、npm registry。
- 应用代码可正常构建（Python 3.7 / Node 18）。
- 部署使用单机本地盘存储，暂不涉及共享存储。

## 9. 风险

| 风险 | 影响 | 缓解措施 |
| --- | --- | --- |
| 未先构建 `domain-admin-base:latest` | 首次部署直接失败 | 部署流程固化，任务清单强制检查 |
| `env_file` 中的 `${...}` 不被展开 | backend 连不上 MySQL | 文档要求写死实际值，验收前检查配置 |
| `build.sh` 无参数调用报错 | 构建中断 | 明确要求显式传 target |
| 单机故障 | 服务中断、数据不可用 | 定期备份、恢复演练、`restart` 策略 |
| 弱密码 / 密钥泄露 | 安全风险 | 强密码、`SECRET_KEY`、文件权限、文档脱敏 |
| 数据库迁移不可逆 | 升级失败难回退 | 升级前全量备份，先预演 |

## 10. 里程碑

| 阶段 | 内容 | 完成标志 |
| --- | --- | --- |
| M1 | 配置与构建就绪 | base 镜像与 4 个业务镜像构建成功 |
| M2 | 服务启动 | 6 个容器 Up，依赖健康 |
| M3 | 验证通过 | AC-1 ～ AC-7 全部通过 |
| M4 | 运维交接 | AC-8、AC-9 通过，任务清单归档 |

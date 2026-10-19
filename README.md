# domain-admin deployment repo

这个目录用于承载 `domain-admin` / `domain-admin-web` 的容器化部署资产。

## 目录说明

- `domain-admin/`：后端源码
- `domain-admin-web/`：前端源码
- `docker-compose.yml`：Docker Compose 部署文件
- `k8s/`：Kubernetes 清单
- `env/`：示例环境变量文件
- `import/`：导入示例与本地导入数据（仅示例纳入 Git）

## 本地导入文件

将配置导入文件 `config-import.txt`、监控导入文件 `config-monitor-import.csv` 等原始数据统一放在根目录的 `import/` 下。目录不存在时先执行 `mkdir -p import`，导入时从该目录选择对应文件。

仓库提供两个脱敏示例：[example.txt](import/example.txt) 用于域名 / 证书导入，每行一个域名，可附带端口；[example.csv](import/example.csv) 用于站点监控导入，包含名称、请求 URL、超时和检测频率。使用时复制为其他文件名再填写真实数据，示例中的域名仅用于展示格式。

真实导入文件可能包含真实域名、IP 或凭据，仅保存在本地，不随仓库分发。`.gitignore` 仅放行 `import/example.txt` 和 `import/example.csv`，忽略该目录中的其他文件，并保留对根目录旧文件名的忽略规则，避免误提交；不要使用 `git add -f` 强制加入，也不要将真实数据填入示例文件。

## 部署方案文档

- [PRD：Docker Compose 服务器部署](prd.md)
- [技术规格：Docker Compose 服务器部署](spec.md)
- [任务清单：Docker Compose 服务器部署](tasks.md)
- [公开仓库清理与发布清单](docs/20261019-04-public-repo-cleanup.md)
- [域名列表移动端横向溢出修复](docs/20261019-05-fix-mobile-domain-list-overflow.md)
- [首次空库初始化并发竞态修复](docs/20261019-06-fix-initial-database-race.md)
- [开发与部署指南（CLAUDE.md）](CLAUDE.md)
- [Codex 协作说明（AGENTS.md）](AGENTS.md)
- [运行手册（RUNBOOK.md）](RUNBOOK.md)

## 镜像构建

先进入目录：

```bash
cd /path/to/sre-domain-check
```

### 国内 / 国际镜像源

基础镜像的 apt / pip 与前端镜像的 npm 默认走官方源（`deb.debian.org` / `pypi.org` / `registry.npmjs.org`），国内构建会很慢。`build.sh` 支持通过 `REGION` 切换：

```bash
REGION=cn ./build.sh v1.0.1              # 国内源：阿里云 apt/pip + npmmirror
REGION=cn ./build.sh latest backend      # 国内源，只构建 backend
./build.sh v1.0.1                        # 国际源（默认），构建 base + 全部业务镜像
```

手动执行 `docker build` 时，国内构建需显式传参：

```bash
# 基础镜像
docker build --network host \
  --build-arg APT_MIRROR=mirrors.aliyun.com \
  --build-arg APT_SECURITY_MIRROR=archive.debian.org \
  --build-arg PIP_INDEX=https://mirrors.aliyun.com/pypi/simple/ \
  -t domain-admin-base:latest \
  -f domain-admin/Dockerfile.base \
  domain-admin

# 前端镜像
docker build --network host \
  --build-arg NPM_REGISTRY=https://registry.npmmirror.com \
  -t domain-admin-frontend:latest \
  -f domain-admin-web/Dockerfile \
  domain-admin-web
```

说明：

- 镜像源只影响构建期，产物内容与区域无关，镜像 tag 不需要区分 cn / global。
- 切换 `REGION` 会使依赖安装层缓存失效，下一次构建会重新安装依赖；requirements 不变时后续构建继续走缓存。
- **bullseye 已 EOL（2026-08-31）**：`bullseye-security` 的 deb 包已从常规镜像（阿里云、TUNA、`security.debian.org` 等）移除，但索引仍在，直接安装会大量 404。因此 `APT_SECURITY_MIRROR` 固定指向 `archive.debian.org`，cn / global 均如此；`APT_MIRROR` 只负责 `bullseye` 和 `bullseye-updates`。
- 长期方案是把基础镜像从 `python:3.7.17-slim-bullseye` 升级到受支持的版本（Python 3.7 与 Debian 11 均已 EOL）。

### 手动构建

先构建共享基础镜像（backend / worker / scheduler 都 `FROM` 它，Compose 不会构建 `Dockerfile.base`）：

```bash
docker build --network host \
  -t domain-admin-base:latest \
  -f domain-admin/Dockerfile.base \
  domain-admin
```

再构建 4 个业务镜像：

```bash
docker build --network host -t domain-admin-backend:latest -f domain-admin/Dockerfile domain-admin
docker build --network host -t domain-admin-frontend:latest -f domain-admin-web/Dockerfile domain-admin-web
docker build --network host -t domain-admin-worker:latest -f domain-admin/Dockerfile.worker domain-admin
docker build --network host -t domain-admin-scheduler:latest -f domain-admin/Dockerfile.scheduler domain-admin
```

如果你想显式指定前端构建参数：

```bash
docker build --network host \
  --build-arg VITE_APP_API=/api \
  --build-arg VITE_BASE_URL=/ \
  -t domain-admin-frontend:latest \
  -f domain-admin-web/Dockerfile \
  domain-admin-web
```

构建后查看镜像：

```bash
docker images | grep domain-admin
```

## 推送到镜像仓库

假设仓库前缀如下：

```bash
export REGISTRY=registry.example.com/domain-admin
```

### latest 标签

```bash
docker tag domain-admin-backend:latest   $REGISTRY/backend:latest
docker tag domain-admin-frontend:latest  $REGISTRY/frontend:latest
docker tag domain-admin-worker:latest    $REGISTRY/worker:latest
docker tag domain-admin-scheduler:latest $REGISTRY/scheduler:latest

docker push $REGISTRY/backend:latest
docker push $REGISTRY/frontend:latest
docker push $REGISTRY/worker:latest
docker push $REGISTRY/scheduler:latest
```

### 固定版本标签

```bash
export TAG=v1
export REGISTRY=registry.example.com/domain-admin

docker build --network host -t $REGISTRY/backend:$TAG -f domain-admin/Dockerfile domain-admin
docker build --network host -t $REGISTRY/frontend:$TAG -f domain-admin-web/Dockerfile domain-admin-web
docker build --network host -t $REGISTRY/worker:$TAG -f domain-admin/Dockerfile.worker domain-admin
docker build --network host -t $REGISTRY/scheduler:$TAG -f domain-admin/Dockerfile.scheduler domain-admin

docker push $REGISTRY/backend:$TAG
docker push $REGISTRY/frontend:$TAG
docker push $REGISTRY/worker:$TAG
docker push $REGISTRY/scheduler:$TAG
```

## Docker Compose 启动

先准备环境文件：

```bash
cp .env.example .env
cp env/backend.env.example env/backend.env
```

启动：

```bash
docker compose up -d
```

查看状态：

```bash
docker compose ps
```

查看日志：

```bash
docker compose logs --tail 200 backend
docker compose logs --tail 200 worker
docker compose logs --tail 200 scheduler
```

## 验证接口

```bash
curl -i http://127.0.0.1:8080/
curl -i http://127.0.0.1:8080/api/getSystemVersion
curl -i -X POST http://127.0.0.1:8080/api/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"<admin-password>"}'
```

### 测试机启动说明

`docker-compose.yml` 已内置 `mysql` 和 `redis`，测试机无需外部依赖，一条命令即可拉起完整 6 个服务；首次启动前按上一节准备两个环境文件即可。

## Kubernetes

K8s 清单位于：

- `k8s/deploy.yaml`：backend / frontend / worker / scheduler
- `k8s/configmap.yaml`：公共环境变量
- `k8s/secret.yaml`：凭据（部署前替换占位符）
- `k8s/svc.yaml`：Service
- `k8s/router.yaml`：APISIX 路由（部署前替换域名）

应用（先按实际情况修改 secret / configmap / router 中的占位符）：

```bash
kubectl apply -f k8s/
```

注意：
- 需要先把镜像名改成你的仓库地址
- 需要替换 Ingress / APISIX 域名
- 需要修改默认密码
- 共享 PVC 默认使用 `ReadWriteMany`


## fix镜像

### 2026-03-20 修复 Worker/Scheduler MySQL 连接丢失

详见 [docs/20260320-fix-mysql-lost-connection.md](docs/20260320-fix-mysql-lost-connection.md)

### 2026-03-20 修复 Worker MySQL InterfaceError 自动重连

详见 [docs/20260320-fix-mysql-interface-error.md](docs/20260320-fix-mysql-interface-error.md)

### 2026-03-20 修复 Worker 启动时 execute_sql 参数不匹配

详见 [docs/20260320-fix-reconnect-execute-sql-signature.md](docs/20260320-fix-reconnect-execute-sql-signature.md)

### 2026-03-20 修复异步任务重复提交导致 Worker 大量重复执行

详见 [docs/20260320-04-fix-async-task-duplicate-submit.md](docs/20260320-04-fix-async-task-duplicate-submit.md)

### 2026-03-20 修复 pending flag 竞态条件导致任务仍然重复执行

详见 [docs/20260320-05-fix-pending-flag-race-condition.md](docs/20260320-05-fix-pending-flag-race-condition.md)

### 2026-03-20 修复 Worker 端队列残留任务导致重复执行

详见 [docs/20260320-06-fix-worker-duplicate-execution.md](docs/20260320-06-fix-worker-duplicate-execution.md)

### 2026-03-20 修复 Worker 串行消费导致残留任务逐个执行

详见 [docs/20260320-07-fix-worker-serial-drain-duplicate.md](docs/20260320-07-fix-worker-serial-drain-duplicate.md)

### 2026-03-20 修复 Worker 异步任务失败时 RuntimeError 信息为空

详见 [docs/20260320-08-fix-worker-empty-runtime-error.md](docs/20260320-08-fix-worker-empty-runtime-error.md)

### 2026-03-20 修复 Worker 执行任务时装饰器双重执行导致 AppException

详见 [docs/20260320-09-fix-worker-decorator-double-wrap.md](docs/20260320-09-fix-worker-decorator-double-wrap.md)

### 2026-03-20 Worker 任务增加进度日志与容错处理

详见 [docs/20260320-10-add-worker-task-progress-logging.md](docs/20260320-10-add-worker-task-progress-logging.md)

需要重新构建并部署 backend、worker 和 scheduler 镜像。

```bash
export REGISTRY=registry.example.com/sre
export TAG=v1.0.14
```

```bash
cd /path/to/sre-domain-check && \
docker build --network host -t $REGISTRY/domain-admin-backend:$TAG -f domain-admin/Dockerfile domain-admin && \
docker build --network host -t $REGISTRY/domain-admin-worker:$TAG -f domain-admin/Dockerfile.worker domain-admin && \
docker build --network host -t $REGISTRY/domain-admin-scheduler:$TAG -f domain-admin/Dockerfile.scheduler domain-admin && \
docker push $REGISTRY/domain-admin-backend:$TAG && \
docker push $REGISTRY/domain-admin-worker:$TAG && \
docker push $REGISTRY/domain-admin-scheduler:$TAG && \
kubectl set image deploy/domain-admin-backend backend=$REGISTRY/domain-admin-backend:$TAG && \
kubectl set image deploy/domain-admin-worker worker=$REGISTRY/domain-admin-worker:$TAG && \
kubectl set image deploy/domain-admin-scheduler scheduler=$REGISTRY/domain-admin-scheduler:$TAG && \
kubectl rollout status deploy/domain-admin-backend && \
kubectl rollout status deploy/domain-admin-worker && \
kubectl rollout status deploy/domain-admin-scheduler
```

```bash
cd /path/to/sre-domain-check && \
docker build --network host -t $REGISTRY/domain-admin-worker:$TAG -f domain-admin/Dockerfile.worker domain-admin  && \
docker push $REGISTRY/domain-admin-worker:$TAG && \
kubectl set image deploy/domain-admin-worker worker=$REGISTRY/domain-admin-worker:$TAG && \
kubectl rollout status deploy/domain-admin-worker
```

```bash
kubectl set image deploy/domain-admin-backend backend=$REGISTRY/domain-admin-backend:$TAG && \
kubectl set image deploy/domain-admin-worker worker=$REGISTRY/domain-admin-worker:$TAG && \
kubectl set image deploy/domain-admin-scheduler scheduler=$REGISTRY/domain-admin-scheduler:$TAG && \
kubectl rollout status deploy/domain-admin-backend && \
kubectl rollout status deploy/domain-admin-worker && \
kubectl rollout status deploy/domain-admin-scheduler
```

```bash
kubectl logs -f deploy/domain-admin-worker
```

## redis

kubectl exec -it redis-0 -- /bin/bash
# 1. 查看所有残留的 pending flag
redis-cli -n 1 -a redis keys "domain_admin:flag:pending:*"

# 2. 一键清除所有 pending flag
redis-cli -n 1 -a redis keys "domain_admin:flag:pending:*" | xargs -r redis-cli -n 1 -a redis del

# 3. 查看所有残留的 lock
redis-cli -n 1 -a redis keys "domain_admin:lock:execute:*"

# 4. 一键清除所有 execute lock
redis-cli -n 1 -a redis keys "domain_admin:lock:execute:*" | xargs -r redis-cli -n 1 -a redis del

# 5. 清空 RQ 队列中排队的任务（如果有残留）
redis-cli -n 1 -a redis del "rq:queue:domain-admin"

# 6. 确认清理干净
redis-cli -n 1 -a redis keys "domain_admin:*"


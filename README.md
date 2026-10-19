# domain-admin deployment repo

这个目录用于承载 `domain-admin` / `domain-admin-web` 的容器化部署资产。

## 目录说明

- `domain-admin/`：后端源码
- `domain-admin-web/`：前端源码
- `docker-compose.yml`：Docker Compose 部署文件
- `k8s/`：Kubernetes 清单
- `env/`：示例环境变量文件

## 部署方案文档

- [PRD：Docker Compose 服务器部署](prd.md)
- [技术规格：Docker Compose 服务器部署](spec.md)
- [任务清单：Docker Compose 服务器部署](tasks.md)
- [公开仓库清理与发布清单](docs/20261019-04-public-repo-cleanup.md)
- [开发与部署指南（CLAUDE.md）](CLAUDE.md)
- [Codex 协作说明（AGENTS.md）](AGENTS.md)

## 镜像构建

先进入目录：

```bash
cd /path/to/sre-domain-check
```

构建 4 个镜像：

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


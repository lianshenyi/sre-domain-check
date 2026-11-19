# 运行手册

## 启动

完整环境（前端、后端、MySQL、Redis）：

```bash
cp .env.example .env
cp env/backend.env.example env/backend.env
scripts/release-compose.sh deps
docker compose up -d
```

前端本地开发（默认 Vite 地址为 `http://localhost:5173`）：

```bash
cd domain-admin-web
npm ci
npm run dev
```

后端本地开发（`python app.py` 监听端口 8000）：

```bash
cd domain-admin
pip install -r requirements.txt
python app.py
```

Compose 前端默认使用 `HTTP_PORT=8080`，访问 `http://localhost:8080`。仅 frontend 对宿主机发布端口；MySQL 和 Redis 只在 Compose 网络中可用。

## 依赖与配置

- MySQL 8 与 Redis 7 由 `docker compose` 启动；数据分别保存在 `data/mysql` 与 `data/redis`。
- 环境变量文件：`.env`、`env/backend.env`。变量包括 `HTTP_PORT`、`MYSQL_ROOT_PASSWORD`、`MYSQL_DATABASE`、`MYSQL_USER`、`MYSQL_PASSWORD`、`DB_CONNECT_URL`、`ADMIN_USERNAME`、`ADMIN_PASSWORD`、`SECRET_KEY`、`REDIS_URL`、`REDIS_PREFIX`。
- 所有密码、连接串与密钥使用占位值或本地私有配置，禁止提交。管理员账号由 `ADMIN_USERNAME` / `ADMIN_PASSWORD` 在首次建库时创建。

## 验证与排查

```bash
docker compose ps
curl -i http://localhost:${HTTP_PORT:-8080}/
curl -i http://localhost:${HTTP_PORT:-8080}/api/getSystemVersion
```

- `pull access denied for domain-admin-base`：先执行上方基础镜像构建命令。
- 后端无法连库：确认 MySQL healthy，且 `DB_CONNECT_URL` 与 `.env` 的 MySQL 用户、密码、数据库一致；`env_file` 不会展开 `${...}`。
- 前端 502：执行 `docker compose logs --tail=200 backend`。
- 端口冲突：在 `.env` 调整 `HTTP_PORT` 后重新执行 `docker compose up -d`。

## 证书批量刷新验证

- 前端连接本地 Flask 时，从前端目录运行 `VITE_APP_API=http://127.0.0.1:8000/api npm run dev`。
- 使用有权读取测试域名的账号进入「证书监控」，点击「全部更新」。用可正常读取证书的域名和探测失败的测试域名覆盖成功与失败计数。
- 若进度查询持续重试，检查浏览器中 `getDomainCertBatchProgress` 的响应和后台任务日志。长时间等待执行时，检查 worker 与 Redis 队列。

## 区域 Agent 验证

- 使用首次初始化的管理员账号（`ADMIN_USERNAME`、`ADMIN_PASSWORD`），在「证书监控」登记一条该账号可读的测试域名。
- 在 HTTPS 控制台的「系统管理 → Agent 节点」登记两个测试节点。安装和区域复测沿用控制台的 `VITE_APP_API` 与现有鉴权，Agent 使用控制台的 HTTPS origin。
- 登记或重签按钮不可用时，检查浏览器打开的是 HTTPS 地址。节点保持离线时，检查 runner 进程、控制端证书信任和节点日志。安装码过期后在控制台重签。
- 安装、复测与回滚步骤见[多地区 Agent 操作说明](docs/20261118-01-regional-domain-agents.md)。

## 依赖 base 与回滚

- Python base 由 `production.lock` 的摘要命名；日常使用 `scripts/build-images.sh frontend|backend|deps|all` 或 `scripts/release-compose.sh <scope>`，仅依赖变更会重建 base。
- Bullseye EOL 后默认使用腾讯 Archive。若该源失败，仅本次命令可切到阿里：`APT_ARCHIVE_BASE=https://mirrors.aliyun.com/debian-archive PIP_INDEX=https://mirrors.aliyun.com/pypi/simple/ scripts/release-compose.sh deps`。不要使用常规 `/debian-security` 源。
- 发布命令会输出 `rollback_stamp`；仅恢复受影响服务：`scripts/release-compose.sh rollback <stamp> deps`。镜像回滚不会回滚 MySQL/Redis 数据卷。

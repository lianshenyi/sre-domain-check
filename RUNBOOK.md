# 运行手册

## 启动

完整环境（前端、后端、MySQL、Redis）：

```bash
cp .env.example .env
cp env/backend.env.example env/backend.env
docker build --network host -t domain-admin-base:latest -f domain-admin/Dockerfile.base domain-admin
docker compose up -d --build
```

前端本地开发（默认 Vite 地址为 `http://localhost:5173`）：

```bash
cd domain-admin-web
npm ci
npm run dev
```

后端本地开发（默认 Flask 地址由应用配置决定）：

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

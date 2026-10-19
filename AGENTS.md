# AGENTS.md

本文件供 Codex 等编码代理使用。项目的人类文档以仓库根目录为准，不要在本文件里重复大段内容。

## 项目是什么

域名 / SSL 证书监控平台：Flask + Peewee + RQ + APScheduler 后端，Vue 3 + Vite 前端，MySQL 8 + Redis 7。测试机通过根目录 `docker-compose.yml` 一键启动 6 个容器。

## 先读哪些文档

- `CLAUDE.md`：部署、镜像构建、运维命令、故障排查、仓库约定。
- `prd.md`：产品范围、功能需求 FR-1..FR-10、验收标准。
- `spec.md`：技术方案、服务角色、配置、端口、数据持久化、K1..K9 注意事项。
- `tasks.md`：当前任务清单与完成定义。
- `docs/`：按 `YYYYMMDD-NN-主题.md` 命名的变更记录；改完代码后更新对应文档和 `README.md` 索引。

## 常用命令

```bash
# 完整测试机环境（含 MySQL / Redis）
docker compose up -d --build

# 冒烟环境（app 单容器 + MySQL + Redis）
docker compose -f docker-compose.smoke.yml up -d --build

# 前端本地开发
cd domain-admin-web && npm ci && npm run dev

# 后端本地开发
cd domain-admin && pip install -r requirements.txt && python app.py
```

## 开发约定

- 使用中文注释、中文文档；提交信息简洁描述变更。
- 修改环境变量时同步更新 `.env.example` / `env/backend.env.example` / `compose` 默认值，保持测试默认值一致。
- `env_file` 不展开 `${...}`，示例值必须是字面量。
- 只有 `scheduler` 服务允许 `SCHEDULER_ENABLED=true`，backend / worker 必须为 false。
- Redis DB 0 用于缓存，DB 1 用于异步任务 / 锁 / RQ 队列，key 前缀 `domain_admin`。
- 新增依赖后同步更新 `requirements.txt` 或 `package.json` + lockfile，并验证 Docker 构建。

## 安全红线

- 公开仓库禁止提交真实账号、密码、token、内网 IP、内部域名；文档与示例一律用 `<placeholder>` 或 `{{token}}`。
- `domain-admin/http/` 是脱敏后的调试样例；本地真实凭据放在 `http-client.private.env.json`（已 gitignore）。
- 不要删除 `k8s/`、`openspec/`、`.codex/` 等目录，除非任务明确要求。

## OpenSpec 工作流

需要新增功能或较大改动时，先在 `openspec/changes/` 下创建 change（包含 proposal、tasks、design 等），实现完成后再归档。可用 `.codex/skills/openspec-*` 中的流程说明。

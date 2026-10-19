# 公开仓库清理与发布清单

- 文档编号：20261019-04
- 关联文档：
  - [PRD](../prd.md)
  - [技术规格](../spec.md)
  - [任务清单](../tasks.md)
- 说明：本文不含任何真实账号密码；体积为当前工作区实测值。

## 1. 本次已完成

| 项目 | 处理 |
| --- | --- |
| `k8s/secret.yaml` | 默认账号密码改为 `<...>` 占位符 |
| `k8s/configmap.yaml` | 数据库 / Redis 连接串改为占位符 |
| `k8s/deploy.yaml` | 内部镜像仓库改为 `registry.example.com/sre`，pull secret 名改为 `registry-credentials` |
| `k8s/router.yaml` | 内部域名改为 `domain-check.example.com` |
| `README.md` | 内部路径 `/git/...` 改为 `/path/to/...`；内部仓库地址改为示例地址；修正不存在的 `k8s/domain-admin.yaml`、`k8s/README.md` 引用；登录示例密码改为占位符；增加测试机启动说明 |
| `env/backend.env.example` | 修复 `DB_CONNECT_URL` 使用 `${...}` 导致 env_file 不展开的问题，改为与 `.env.example` 一致的测试默认值 |
| `.env.example` / `env/backend.env.example` | 增加「测试默认值，生产必须修改」注释 |
| `domain-admin/.env.example` | 示例密码改为占位符 |
| `domain-admin/.dockerignore` | 保留 `tests`、`http`、`.env` 等排除项，缩小构建上下文；删除已不存在路径的规则 |
| `domain-admin-web/.dockerignore` | 新增，排除 `node_modules`、`dist`、`.git` 等 |
| `k8s/bak/domain-admin.yaml` | 工作区已删除（待提交） |
| `.kiro/steering/product.md` | 产品概述合并到 PRD 1.1，原目录已删除 |
| `.kiro/steering/structure.md`、`tech.md` | 代码结构与技术栈合并到技术规格第 16、17 节，原目录已删除 |
| `.kiro/steering/work-style.md` | 文档约定合并到技术规格第 18 节和任务清单「执行约定」，原目录已删除 |
| `.codex/`、`openspec/` | 因后续需要 Codex / OpenSpec 继续开发，已恢复保留；`.kiro/` 仍保持删除 |
| `domain-admin/image/`、`domain-admin/doc/`、`domain-admin/docs/` | 已确认前端与后端运行时均未引用，已删除（约 5.7M） |
| `domain-admin/package.json`、`domain-admin/pnpm-lock.yaml` | 仅用于构建已删除的 VitePress 文档，已删除 |
| `domain-admin/http/` | 保留作为开发调试样例，已脱敏：移除 `pro` 环境内网 IP、历史 JWT、Prometheus bearer token；请求头改为 `{{token}}` / `{{prometheusKey}}` |
| `.gitignore` | 增加 `domain-admin/http/http-client.private.env.json`，本地真实 token 不入库 |
| `AGENTS.md` | 新增，供 Codex 读取项目结构、常用命令、开发约定与安全红线 |
| `openspec/config.yaml` | 填写项目上下文与 proposal / tasks / design 规则，供 OpenSpec 生成变更使用 |
| `prd.md`、`spec.md`、`tasks.md` | 按用户要求从 `docs/` 移至仓库根目录，并同步修正所有引用 |

## 2. 已删除（原待删除清单）

以下路径已按确认删除：

| 路径 | 体积 | 判断依据 |
| --- | --- | --- |
| `domain-admin/tests/top-1m.txt` | 11M | 代码中无引用，仅被已删除的上游开发文档提到 |
| `domain-admin/.github/` | 28K | 上游 PyPI / Docker / 同步工作流，公开仓库中可能误触发 |
| `domain-admin-web/pnpm-lock.yaml` | 92K | 与 `package-lock.json` 重复；Dockerfile 使用 npm，`npm ci --dry-run` 已验证通过 |
| `docker/app.nginx.conf`、`docker/start-app.sh` | 8K | 无任何引用（`Dockerfile.app` 只使用 `start-app.py`） |
| `COMPOSE_NOTES.md` | 4K | 内容已被 README / CLAUDE.md / 技术规格覆盖 |

同时已把 `domain-admin-web/README.md` 的 `pnpm i` 改为 `npm ci`，并清理 `domain-admin/.dockerignore` 中指向已删除目录的规则。

删除后工作区（不含 `.git`）约 2.0M；`.git` 中的历史对象不会自动变小，公开前仍需执行第 4.1 节的历史重建。

## 3. 需要确认后决定

| 路径 | 体积 | 说明 |
| --- | --- | --- |
| `domain-admin/tests/`（删除 `top-1m.txt` 后） | 约 124K | 保留可维持代码质量；纯部署仓库可整体删除 |
| `Dockerfile.app` + `docker-compose.smoke.yml` + `docker/start-app.py` | 12K | 轻量冒烟方案；保留可让测试机只起 3 个容器，删除可消除与主 compose 重复的 mysql/redis 定义 |
| `domain-admin-web/template/` + `more-copy.config.cjs` | 36K | 前端代码生成工具；开发不用可删除 |
| `domain-admin/README.md`、`CHANGELOG.md` | 36K | 上游说明与变更记录；建议保留以保留来源与 MIT 归属 |
| `k8s/` | 24K | 若公开仓库只做 Compose，可整体删除；保留则已做脱敏 |

## 4. 公开前必须处理

### 4.1 Git 历史

重建前的历史只有 1 个提交 `3a3b07c`，其中包含：

- `k8s/bak/domain-admin.yaml`（含 `domainadmin123` 等旧默认凭据）
- `k8s/secret.yaml` 旧版本（含 `root` / `123456`）
- 11M 的 `domain-admin/tests/top-1m.txt`

只在工作区删除不会从历史中移除。本次已用「孤立提交」重建公开历史：

```bash
# 先完成第 2 节删除并确认工作区干净
git checkout --orphan public-main
git add -A
git commit -m "Initial public release"
git branch -D main
git branch -m main

# 远端已存在（origin 已指向本仓库），覆盖旧历史
git push --force-with-lease origin main

# 远端跟踪分支更新后，清理本地不可达对象
git fetch --prune origin
git gc --prune=now
```

> 重建前的远端 `main` 为 `3a3b07c`，force-push 后该提交不再被任何分支引用。重建后的公开提交为 `6ac924d`（`Initial public release`），本地与 `origin/main` 已一致。若仓库曾经公开或被他人克隆，仍应把所有出现过真实凭据的账号 / token 视为已泄露并轮换。

> 如果必须保留提交历史，使用 `git filter-repo` 移除敏感路径 / 大文件并替换文本，再推送。

### 4.2 敏感信息复查

```bash
git grep -nE 'domainadmin123|pp-registry|tencentcloudcr|p2my\.com|AKID|SecretKey'
```

说明：仓库中仍有 `123456`、`domainadmin123` 等**测试默认值**，分布在测试代码、mock 数据、上游文档和 Compose 默认值中；这些不是生产凭据，但公开前应确认是否接受。生产部署必须通过 `.env` / `env/backend.env` 覆盖。

### 4.3 许可证与来源

- `domain-admin/LICENSE` 为 MIT，公开仓库需保留。
- README 建议保留上游项目地址与来源说明。
- 若公开的是部署仓库，建议在根目录补充 LICENSE 或注明各子目录许可。

### 4.4 其他

- `.gitignore` 末尾有一段被注释掉的 `#domain-admin/*` 规则和说明，已无实际作用，可删除以免误导。
- 公开仓库建议关闭不需要的 Actions；删除上游 `.github/workflows` 后不会误触发发布流程。
- 不建议把 `.env`、`env/backend.env`、`data/`、`logs/` 提交入库（已在 `.gitignore`）。

## 5. MySQL / Redis 与测试机启动

`docker-compose.yml` **已经包含** `mysql` 和 `redis`，并带健康检查与数据卷；`backend` / `worker` / `scheduler` 会等待两者健康后启动。测试机无需外部数据库。

完整测试环境（6 个容器）：

```bash
cp .env.example .env
cp env/backend.env.example env/backend.env
docker build --network host -t domain-admin-base:latest -f domain-admin/Dockerfile.base domain-admin
docker compose up -d --build
```

轻量冒烟环境（3 个容器：mysql + redis + app，不含 worker / scheduler）：

```bash
docker compose -f docker-compose.smoke.yml up -d --build
```

如需在测试机上直连 MySQL / Redis 调试，可临时使用 override（不要用于公网）：

```yaml
# docker-compose.test.yml（按需创建，未纳入版本库）
services:
  mysql:
    ports:
      - "127.0.0.1:3306:3306"
  redis:
    ports:
      - "127.0.0.1:6379:6379"
```

```bash
docker compose -f docker-compose.yml -f docker-compose.test.yml up -d
```

## Why

当前发布脚本每次均构建 Python 基础镜像，生产依赖又未被精确锁定，导致代码级发布重复执行 apt/pip 下载、构建结果随时间漂移。前端、后端和依赖变更也无法使用一个明确、可复验的范围构建入口。

## What Changes

- 增加带版本和哈希校验的 Python 生产依赖锁文件，并让共享基础镜像只安装该锁文件。
- 用锁文件内容派生不可变的基础镜像标签；backend、worker、scheduler 显式共用该标签。
- 为 Dockerfile 增加可选的 BuildKit pip/npm 下载缓存，不改变最终运行时镜像内容。
- 重写构建/发布脚本，区分 frontend、Python 业务代码和 Python 依赖变更，并提供构建、部署、回滚与计时记录命令。
- 更新 Compose 与运维文档，使首次迁移、日常范围构建和回滚可操作、可验证。

## Capabilities

### New Capabilities

- `reproducible-container-builds`: 锁定后端依赖、派生不可变基础镜像版本并支持缓存的可复现构建。
- `scoped-compose-release`: 按前端、后端代码或依赖变更范围构建并部署 Compose 服务，支持回滚和构建证据采集。

### Modified Capabilities

无。

## Impact

- 修改 `domain-admin` 的生产依赖与三个 Python Dockerfile、`docker-compose.yml`、`build.sh`，并新增范围部署辅助脚本与验证测试。
- 修改 `domain-admin-web/Dockerfile` 以复用 npm 下载缓存。
- 更新 `CLAUDE.md`、`README.md`、`spec.md`、`tasks.md` 和一份中文变更记录；不修改 Python 3.7、Debian 基础版本、业务 API 或 Go 架构。
- 部署时需要先生成/拉取由锁文件摘要命名的 base；可通过文档中的 `docker build`、`docker compose`、`curl` 和日志命令验证。

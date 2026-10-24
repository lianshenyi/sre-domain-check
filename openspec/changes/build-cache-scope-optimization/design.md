## Context

现有 `production.txt` 大多为浮动版本，`build.sh` 无条件重建 `domain-admin-base:<tag>`，Compose 三个 Python 服务引用可变的 `latest`。这使同样的代码并不保证得到同样的依赖，也令仅前端或业务代码变更时重复下载 Python 依赖。部署目标是单机 Docker Compose，必须兼容现有 BuildKit/Compose，不增加运行时服务，也不更换 Python、Debian 或业务实现。

## Goals / Non-Goals

**Goals:**

- 用经哈希校验的生产依赖 lock 实现可复现的 pip 安装。
- 以 lock 文件摘要派生稳定的 base tag，并让 backend、worker、scheduler 显式使用同一 tag。
- 让构建工具根据目标或变更范围只构建必要镜像，并记录阶段耗时及缓存命中。
- 提供可执行的首次迁移、回滚和健康验证步骤。

**Non-Goals:**

- 不升级 Python 3.7、Debian bullseye 或 Node，也不重写为 Go、修改应用 API 或引入远端镜像仓库。
- 不保证跨不同 CPU 架构复用本地 Docker layer cache；依赖 lock 才是跨机器可复现边界。

## Decisions

1. **提交 `requirements/production.lock`，保留 `production.txt` 作为人工维护的顶层清单。** lock 由兼容 Python 3.7 的 `pip-compile --generate-hashes` 生成，并在构建/校验中执行 `pip install --require-hashes`。相较在 Dockerfile 中自由解析，lock 固定直接与间接依赖及分发包哈希；相较弃用顶层清单，仍保留清晰的业务依赖意图。

2. **base tag 为 `domain-admin-base:deps-<lock 前 16 位 SHA-256>`。** `scripts/build-images.sh` 是唯一计算入口，向 Compose 注入 `DOMAIN_ADMIN_BASE_IMAGE`。三个 Python Dockerfile 继续是轻量的代码/CMD 层，但 `FROM` 只接受该显式参数。相较 `latest`，该 tag 可以直接表达依赖身份，也可并存用于回滚。

3. **使用 Dockerfile syntax 1.4 的缓存挂载。** pip 使用 `/root/.cache/pip`，npm 使用 `/root/.npm`；最终镜像仍不含缓存。构建机未启用 BuildKit 时，脚本明确失败并给出启用命令，而不是静默使用不兼容 Dockerfile。

4. **按输入范围选择服务。** `frontend` 仅构建/替换 frontend；`backend` 构建/替换 backend、worker、scheduler；`deps` 先确保 base，再构建/替换三个 Python 角色；`all` 组合以上。若以 Git 基线判断变更，前端路径映射 frontend，Python 源码映射 backend，lock/基础 Dockerfile 映射 deps；未知根目录构建配置映射 all，安全优先。

5. **Compose 用 image 固定业务镜像名且通过环境变量透传 base。** 保留本地 build，不要求仓库。部署脚本先对将替换的镜像打 rollback tag，再用 `docker compose up -d --no-deps <服务>` 替换，避免无关容器重启。

## Risks / Trade-offs

- [Python 3.7 解析器无法生成完全兼容 lock] → 在目标构建机内使用与 base 相同的 Python 3.7 容器生成/验证，并把该限制明确留在文档中；升级单列后续项目。
- [依赖源短暂不可用导致冷缓存慢] → 缓存挂载降低重复下载；计时日志区分 cold/hot，不能把网络问题误判为代码问题。
- [错误选择范围遗漏服务] → 脚本有 `all` 保守回退，接受显式目标，并为路径映射写单元测试。
- [base tag 被手工删除] → `deps` 或首次运行自动构建；回滚说明保留旧 tag 和业务镜像快照。

## Migration Plan

1. 生成并审查 lock，运行 hash 校验和 Docker 构建测试。
2. 执行 `scripts/build-images.sh deps` 生成 digest base，再执行 `scripts/release-compose.sh all`，记录 cold 阶段日志。
3. 立即再执行相同命令记录 hot 阶段日志；确认 base 未重建而层显示缓存命中。
4. 运行 6 容器、入口、版本、登录和核心 API 健康检查。
5. 回滚时以 `scripts/release-compose.sh rollback <stamp> <scope>` 恢复业务镜像；若 lock/base 有误，切回先前 `DOMAIN_ADMIN_BASE_IMAGE` 并重新替换 Python 三角色。

## Open Questions

- 无：本阶段只使用本地 BuildKit cache；远端 registry cache 在有受信任镜像仓库时另行评估。

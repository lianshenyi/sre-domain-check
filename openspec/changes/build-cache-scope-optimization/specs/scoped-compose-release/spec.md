## ADDED Requirements

### Requirement: Scoped image build selection
构建工具 SHALL 支持 `frontend`、`backend`、`deps` 与 `all` 目标，并支持从 Git 基线计算变更范围。范围映射 SHALL 使前端变更只选择 frontend，Python 源码变更选择三个 Python 角色，依赖或基础构建输入变更选择 deps。

#### Scenario: 前端范围构建
- **WHEN** 运维选择 frontend 或检测到仅 `domain-admin-web` 变更
- **THEN** 工具 SHALL 只构建 frontend 镜像且不得构建共享 Python base

#### Scenario: 依赖范围构建
- **WHEN** 运维选择 deps 或检测到 lock 变更
- **THEN** 工具 SHALL 先构建 digest base，再构建 backend、worker 和 scheduler 镜像

### Requirement: Scoped Compose deployment and rollback
发布工具 SHALL 对被替换服务创建带时间戳的本地 rollback 镜像标签，并使用 `docker compose up -d --no-deps` 仅替换选定服务。工具 SHALL 支持按范围恢复最近或指定时间戳的快照。

#### Scenario: Frontend scoped deployment
- **WHEN** 运维发布 frontend 范围
- **THEN** 工具 SHALL 只替换 frontend 容器，backend、worker、scheduler 的容器 ID 不变

#### Scenario: Scoped rollback
- **WHEN** 运维指定已有 rollback 时间戳和范围
- **THEN** 工具 SHALL 恢复该范围的镜像并仅重建该范围容器

### Requirement: Build evidence
构建与发布工具 SHALL 输出阶段耗时、base 标签、服务范围与 BuildKit cache 证据；文档 SHALL 给出 cold/hot 采集与运行健康验证命令。

#### Scenario: Benchmark collection
- **WHEN** 运维执行 cold 或 hot benchmark
- **THEN** 工具 SHALL 保存包含阶段耗时和构建输出的日志文件，便于验收 cache hit 和健康状态

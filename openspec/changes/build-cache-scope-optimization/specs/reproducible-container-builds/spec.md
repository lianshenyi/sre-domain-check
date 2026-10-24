## ADDED Requirements

### Requirement: Hash-verified production dependencies
系统 SHALL 将生产 Python 依赖锁定在提交的 lock 文件中，包含直接和间接依赖的精确版本及哈希。基础镜像构建 SHALL 使用 `pip install --require-hashes` 安装该 lock，并提供独立校验命令。

#### Scenario: Lock 校验成功
- **WHEN** 运维执行依赖校验命令且 lock 未被篡改
- **THEN** pip 在不解析浮动版本的情况下通过哈希校验完成安装

#### Scenario: Lock 内容被篡改
- **WHEN** lock 中的包哈希与下载分发包不匹配
- **THEN** 构建或校验 SHALL 失败且不得生成可用 base 镜像

### Requirement: Immutable shared Python base
系统 SHALL 从生产 lock 的 SHA-256 派生 `domain-admin-base:deps-<digest>` 标签。backend、worker 和 scheduler SHALL 在同一次构建/部署中使用相同的显式 base 标签；仅 Python 源码改变时不得重建该 base。

#### Scenario: Python 业务代码变更
- **WHEN** 仅 `domain-admin` 业务源文件变更且 lock 与 base Dockerfile 未变
- **THEN** 构建工具 SHALL 复用已有 digest base 并仅构建三个 Python 角色镜像

#### Scenario: 依赖 lock 变更
- **WHEN** 生产 lock 内容改变
- **THEN** 构建工具 SHALL 派生不同的 digest base 标签并构建新的共享 base

### Requirement: Dependency download cache
Docker 构建 SHALL 在 BuildKit 可用时使用 pip 与 npm 的缓存挂载；缓存不得被复制到最终运行时镜像。

#### Scenario: 热缓存构建
- **WHEN** 在同一 BuildKit 构建机重复构建且依赖输入未变
- **THEN** 构建日志 SHALL 显示依赖安装层 cache hit 或复用下载缓存

# domain-cert-batches Specification

## Purpose
TBD - created by archiving change bound-domain-cert-batches. Update Purpose after archive.
## Requirements
### Requirement: 用户批量刷新可追踪

系统 SHALL 在用户批量刷新时返回任务 ID，并允许发起人查询逐项进度及终态。

#### Scenario: 一项超时或失败

- **WHEN** 部分域名超时或探测失败
- **THEN** 其他域名继续执行，最终成功数和失败数之和等于总数，任务状态为失败

#### Scenario: 查看任务进度

- **WHEN** 发起者提供任务 ID
- **THEN** 系统返回当前计数和任务状态；其他用户不能读取该任务

### Requirement: 域名列表显示批量刷新进度

域名列表 SHALL 用启动响应的任务 ID 查询并显示已完成数、总数、成功数和失败数。

#### Scenario: 正常推进

- **WHEN** 批量任务排队或执行中
- **THEN** 页面持续更新计数，并在总数未知时显示占位符

#### Scenario: 批量刷新到达终态

- **WHEN** 任务成功或失败，含部分域名失败
- **THEN** 页面保留最终计数、停止轮询并刷新证书列表

#### Scenario: 查询中断或离开页面

- **WHEN** 进度查询失败
- **THEN** 页面提示查询失败、保留计数并重试同一任务
- **WHEN** 用户离开页面
- **THEN** 客户端取消当前进度请求和后续轮询

## Context

`domain_service.update_domain_row` 是当前单条、批量及定时中心证书刷新路径。`model/database.py` 为各角色创建缺失的表，`router/api_map.py` 和 `FlaskApp` 统一 Web API 的路由和响应。区域复测只检查已有域名记录，每节点从本地 DNS 解析并采集一个端点的证书，单独保存结果。现有手工 IP 清单、中心结果和告警继续由中心路径处理。

## Decisions

- 用独立 Python runner 主动通过 HTTPS 轮询，节点无需入站端口、Redis 或数据库凭据。安装码 15 分钟有效且单次可用，运行凭据绑定节点，数据库只保留两者的 SHA-256 摘要。登记、轮换和撤销均为管理员操作。
- 数据库持久化节点与每节点任务。5 分钟的任务期限包括排队与执行，超时后由读取结果时计算为 `expired`。一次领取对应一次执行，领取响应丢失或进程崩溃的任务到期后由管理员重新发起。已接受的重复回报返回现有结果。轮换和撤销同时取消本节点所有未到期的活跃任务。
- 区域协议从登记记录推导，支持直连 TLS、SMTP STARTTLS 和端口 21 的显式 FTPS。Agent 采集叶证书的 DER，后端在校验输入大小后复用现有证书名称匹配规则并解析有效期。检查采集过期或自签名证书的证书信息。控制端的 HTTPS 另行校验信任链与主机名。Agent 唯一任务类型为 `domain_tls`。
- 管理端派发和读取结果时复用中心单条刷新对域名所有者和分组成员的读取权限。域名编辑或删除后，服务器在领取及回报时比对目标快照。运行凭据只可更新受其绑定的节点的心跳和任务。
- 业务模块分别位于 `api/agent_api.py`、`service/agent_service.py`、`model/agent_model.py`，独立 runner 位于 `domain_admin/agent_runner.py`。两张新表由现有初始化流程创建，回滚旧版本可保留表以便后续恢复。

## API 契约

管理端全部使用 POST JSON 和既有管理员 `X-Token`。Agent 协议使用 POST JSON 和 `Authorization: Bearer <credential>`。统一响应为 `{code, msg, data}`，以 `code === 0` 判断成功。Agent 请求常用业务码为 400（参数或载荷错误）、401（凭据无效）、409（任务不可回报）或 413（请求体过大）。管理操作以 `data` 为准，非零 `code` 显示 `msg`。所有时间为 UTC ISO 8601，未设置时为 `null`。

### 管理端

| 路径 | 请求体 | 响应 data |
| --- | --- | --- |
| `/api/createAgent` | `{name, region, origin}` | `{agent, enrollment_code, install_command}` |
| `/api/renewAgentEnrollment` | `{agent_id, origin}` | 同创建，新安装码立即生效，原凭据与活跃任务作废 |
| `/api/revokeAgent` | `{agent_id}` | 节点对象，状态为 `revoked` |
| `/api/getAgentList` | `{}` | 节点对象数组，按 ID 升序 |
| `/api/startAgentDomainCheck` | `{domain_id, agent_ids}` | `{batch_id, results}`，包含各节点任务 |
| `/api/getAgentCheckResults` | `{domain_id, batch_id?}` | 任务对象数组，按 ID 倒序，最多 50 条 |

节点对象为 `{id, name, region, status, last_seen_at, enrollment_expires_at}`。状态含 `pending`（待登记）、`online`（最近一次心跳距今不足 60 秒）、`offline`（已登记且心跳超时）、`revoked`（已撤销）。待登记节点即使安装码过期仍为 `pending`，可重新签发。列表为空返回 `[]`。

`name` 和 `region` 为去除首尾空格后 1–64 字符的文本。`origin` 取站点 HTTPS origin，例如浏览器的 `window.location.origin`。创建后展示可复制的 `install_command`，安装码单独展示，在目标节点执行命令后按提示输入。安装命令内无凭据；命令以当前用户身份安装并前台启动，凭据文件保存在该用户 Agent 目录，权限 0600。

`agent_ids` 需要 1–10 个不同的有效节点 ID。目标记录需使用有效主机名或 IP 加端口。在线和离线的已登记节点都能接单，离线时在有效期内等待重连。任务对象为 `{id, batch_id, domain_id, domain, port, agent_id, agent_name, region, status, created_at, deadline_at, finished_at, cert_starts_at, cert_expires_at, error}`。任务状态含 `queued`、`running`、`succeeded`、`failed`、`expired`、`canceled`。证书日期只在采集到匹配证书时返回，证书有效性可通过日期判断。前端可在区域复测页面每 5–10 秒刷新状态及当前批次，直到页面关闭或批次结束。

### Agent 端

| 路径 | 凭据 | 请求体 | 响应 data |
| --- | --- | --- | --- |
| GET `/api/getAgentRunner` | 无 | 空 | Python 源文件下载 |
| `/api/enrollAgent` | 安装码 | `{agent_id}` | `{agent_token, poll_interval_seconds}` |
| `/api/pollAgentTask` | 运行凭据 | `{agent_id}` | `{task, poll_interval_seconds}`，无任务时 `task=null` |
| `/api/submitAgentTaskResult` | 运行凭据 | `{agent_id, task_id, certificate_der}` 或 `{agent_id, task_id, error: "probe_failed"}` | 任务对象 |

`task` 为 `{id, type, domain, port, protocol}`，协议为 `tls`、`smtp_starttls` 或 `ftps`。默认轮询间隔为 10 秒，轮询成功即心跳。证书字段为 Base64 DER，解码前最多 96 KiB。Agent 访问控制端时拒绝重定向。任务输入为服务端从已有条目取得的主机名、端口、协议。Agent 只识别固定任务类型和协议。

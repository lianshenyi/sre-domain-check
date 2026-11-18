## Why

运维需要从不同地区复测同一域名的证书，并判断各节点是否与中心连通。每个地区只需运行独立 Agent。

## What Changes

- 管理员登记自有节点，生成短期一次性安装码，查看心跳并轮换或撤销凭据。
- 管理员从已有域名条目发起 TLS 证书复测，按所选节点分别收集结果。执行范围限于已有证书检查协议。
- Vue 按接口契约展示安装命令、节点状态及区域复测结果。前端由产品助手另行派发。
- 现有中心巡检、告警和证书摘要继续按原流程运行。

## Capabilities

### New Capabilities

- `regional-domain-checks` 提供 Agent 登记、连通状态与定向域名证书复测。

### Modified Capabilities

无。

## Impact

后端增加 API、独立 Python Agent 和两张表，沿用数据库启动初始化。现有 Compose 拓扑、环境变量和生产依赖无需调整。Agent 主机需要 Python 3.7+、curl 和可访问的 HTTPS 控制端。

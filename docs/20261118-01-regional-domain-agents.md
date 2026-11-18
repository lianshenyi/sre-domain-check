# VIDE-113 多地区 Agent 与域名证书复测

[API 契约](../openspec/changes/add-regional-domain-agents/design.md#api-契约)定义管理员登记、安装、状态和任务结果接口，以及独立 Agent 协议。管理员需拥有中心单条刷新对应的域名读取权限。每次主动发起复测时选择节点，区域结果按节点单独保存。

## 安装和重连

在自有 Linux 节点上以专用系统用户运行安装命令。管理端创建节点后提供命令和 15 分钟有效的一次性安装码，运行命令后按提示输入安装码。控制端必须提供受节点信任的 HTTPS。Agent 使用 Python 3.7+ 标准库，下载需 curl。首次启动保持前台运行。

同一节点重启时复用本地凭据，可将以下命令交给节点已有进程管理器：

```bash
python3 "$HOME/.domain-check-agent/<agent-id>/agent.py" \
  --server 'https://<control-origin>' --agent-id '<agent-id>'
```

凭据文件位于同一目录且权限为 0600。管理员续签安装码后，用新命令重新登记。最后一次心跳达到 60 秒后显示离线，凭据仍有效时下一次轮询会恢复在线。

## 验证与回滚

- 本地隔离 SQLite 自测共 7 项通过，涉及两个模拟地区的真实 HTTPS 控制连接和不同 TLS 证书、SMTP STARTTLS 与 FTPS 握手、安装码及节点权限、轮换撤销、离线重连、任务期限、目标信息改变、单条及批量中心刷新、MySQL 初始化互斥回归。后端语法按 Python 3.7 校验。
- 现有数据库初始化自动建立 `tb_agent_node` 和 `tb_agent_check`。隔离验证使用 Python 3.11，真实地区节点、生产镜像和实际 MySQL 部署由测试环境验收。
- 回滚时停止节点 runner，恢复此前后端版本。保留两张新增表以备重新启用。

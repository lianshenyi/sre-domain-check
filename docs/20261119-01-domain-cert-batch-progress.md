# VIDE-114 用户证书批量刷新与列表查询

## 根因与改动

- “全部更新”逐条执行 DNS 和证书读取；系统 DNS 和部分协议调用没有统一的域名级总时限，且地址级异常被转换为错误文本后不影响批次的成功统计。现在最多并发探测 4 项，每项网络探测进程 30 秒硬超时（杀掉并等待回收）；网络探测不持有数据库连接。查询预算为 55 分钟，预算耗尽后未执行项计为失败；预算不包含 Worker 排队及不可用数据库的等待上界。写入单个域名时使用短事务，超时保留原记录。
- 批次同时累计成功与失败，结束时 `completed = success + failed = total`；任意一项失败时批次为 `failed`，成功数据仍保存。Redis 执行结束后释放同用户提交标记，不再误把紧接着提交的新证书批次当成重复任务。既有 Worker 重启清空队列、进程崩溃和存储不可用的恢复策略不在本次范围。
- 普通用户证书列表使用同一份组关系计算可读范围和可编辑权限，避免重复查组；页码越界时不再查三张关联表。

## 前端对接

- `POST /api/updateAllDomainCertInfoOfUser` 返回 `data.task_id`。`POST /api/getDomainCertBatchProgress` 请求 `{ "task_id": 123 }`，仅发起人可读，响应 `data` 返回 `task_id`、`state`、`total`、`completed`、`success`、`failed`。`state` 为 `queued` / `running` / `succeeded` / `failed`；未取得总数时 `total` 为 `null`。
- 现有域名列表“全部更新”不使用任务 ID、不会展示实时进度。管理员可手动刷新异步日志查看 `result` 中的计数。前端待验收：提交后轮询、显示进度和成功/失败数、到终态停止轮询并刷新证书列表。未改定时任务、注册信息/ICP 批处理和前端。

## 验证

- 在 `domain-admin` 运行 `PYTHONPATH=. python tests/service/benchmark_domain_list.py`。SQLite 中生成 10,000 条域名，普通用户每页 50 条，每条 SELECT 模拟 2 毫秒往返，取 30 次中位数。正常页 88.41 → 74.54 毫秒（7 → 6 条 SELECT）；越界页 85.68 → 45.60 毫秒（7 → 3 条）。每页组关系查询均为 2 → 1。耗时受本地调度影响，不作为线上 MySQL SLA。
- `python -m pytest -q tests/service/test_domain_cert_batch.py tests/api/test_agent_api.py tests/test_hello.py`：10 通过。覆盖真实本地慢 TLS 连接超时回收、快项先计入进度、探测失败、局部成功保留、权限隔离、空批次、预算耗尽及 Redis 执行入口的收尾。测试用 SQLite 和模拟 Redis 锁，未运行生产 MySQL/Redis 环境。

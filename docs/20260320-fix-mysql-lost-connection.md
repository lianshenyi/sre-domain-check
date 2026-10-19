# 修复 Worker/Scheduler MySQL 连接丢失问题

## 问题

Worker 执行异步任务（如 `update_all_domain_cert_info_of_user`）时报错：

```
RuntimeError: (2013, 'Lost connection to MySQL server during query')
```

## 根因

`execute_async_task` 用 `with db.connection_context()` 包裹整个任务函数调用。
循环型任务（遍历域名做证书检测、WHOIS 查询、HTTP 监控等）在循环体内执行耗时网络 I/O，
导致数据库连接长时间空闲，最终被 MySQL 服务端断开。

## 修复方案

将数据库连接粒度从"包裹整个任务"下沉到"每次循环迭代独立管理"：

- 查询列表时用 `with db.connection_context()` 获取数据后立即释放连接
- 每次迭代处理单条记录时独立获取/释放连接
- 网络 I/O 期间不持有数据库连接

## 涉及文件

- `domain_admin/service/async_task_service.py` — 去掉 execute_async_task 中的大 connection_context
- `domain_admin/service/domain_service.py` — update_all_domain_cert_info / update_all_domain_cert_info_of_user / init_domain_cert_info_of_user / auto_import_from_domain_batch_async / auto_import_from_domain_async
- `domain_admin/service/domain_info_service.py` — update_all_domain_info / update_all_domain_info_of_user / update_all_domain_icp_of_user / handle_auto_import_domain_info
- `domain_admin/service/monitor_service.py` — run_monitor_task / run_init_monitor_task_async
- `domain_admin/service/issue_certificate_service.py` — renew_all_certificate
- `domain_admin/service/notify_service.py` — notify_all_event
- `domain_admin/service/auth_service.py` — send_verify_code_async
- `domain_admin/service/scheduler_service/scheduler_main.py` — run_task

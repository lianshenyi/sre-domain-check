# 修复异步任务重复提交导致 Worker 大量重复执行

## 问题

Worker 日志中 `update_all_domain_cert_info_of_user` 在同一秒内被执行了 20+ 次（async_task_row_id 连续递增），
证书只有 600 多个，但每次都完整遍历所有域名做证书检测，造成大量无意义的重复工作。

## 根因

`async_task_decorator` 中的 `submit` 锁（Redis lock）在任务提交到 RQ 队列后立即释放，
而 `execute_async_task` 中的 `execute` 锁只在 worker 实际执行时才获取。

两层锁之间存在时间窗口：

```
请求1 → 获取 submit 锁 → 提交到队列 → 释放 submit 锁
请求2 → 获取 submit 锁 → 提交到队列 → 释放 submit 锁  （此时请求1的任务还在排队）
请求3 → ...
```

RQ worker 串行消费队列，每个任务执行完释放 `execute` 锁后，下一个排队的任务又能获取到锁继续执行。
结果：所有提交的任务都成功执行（`Job OK`），域名被重复更新 N 次。

## 修复方案

引入 `pending flag`（Redis key），覆盖从提交到执行完成的整个生命周期：

- `async_task_decorator`：提交前检查 pending flag，存在则拒绝；不存在则设置 flag 后提交
- `execute_async_task`：在 `finally` 块中清除 pending flag，无论成功失败
- flag 带 TTL（3600s）作为安全兜底，防止异常情况下标记永不清除

```
请求1 → 检查 flag（无）→ 设置 flag → 提交到队列
请求2 → 检查 flag（有）→ 拒绝，返回"任务正在执行"
...
Worker 执行完成 → 清除 flag
请求N → 检查 flag（无）→ 可以提交
```

## 涉及文件

- `domain_admin/service/async_task_service.py` — async_task_decorator 增加 pending flag 检查，execute_async_task 增加 flag 清除
- `domain_admin/utils/redis_lock_util.py` — 新增 set_flag / clear_flag / has_flag 工具函数

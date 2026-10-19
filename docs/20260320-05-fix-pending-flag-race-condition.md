# 修复 pending flag 竞态条件导致任务仍然重复执行

## 问题

上一次修复（04）引入了 pending flag 机制防止重复提交，但 worker 日志仍然出现同一秒内多个相同任务被执行的情况：

```
02:01:02 execute_async_task('...update_all_domain_cert_info_of_user', 20135, ...)
02:01:02 Job OK (...)
02:01:02 execute_async_task('...update_all_domain_cert_info_of_user', 20136, ...)
02:01:02 Job OK (...)
02:01:02 execute_async_task('...update_all_domain_cert_info_of_user', 20137, ...)
...连续 5 个相同任务全部 Job OK
```

## 根因

`async_task_decorator` 中的 pending flag 检查和设置是两步非原子操作：

```python
# 步骤1：检查（GET）
if redis_lock_util.has_flag(pending_flag):
    raise AppException(...)

# 步骤2：设置（SET）
redis_lock_util.set_flag(pending_flag, timeout=3600)
```

Gunicorn 多 worker 进程场景下，多个请求可以同时通过步骤1（都返回 False），然后各自执行步骤2并提交任务到 RQ 队列。

RQ worker 串行消费时，每个任务执行完会清除 pending flag 和释放 execute lock，下一个排队的任务又能成功获取锁继续执行，导致所有重复任务都 `Job OK`。

## 修复方案

用 Redis `SET key value NX EX ttl` 原子命令替代 `has_flag` + `set_flag` 的两步操作：

- `redis_lock_util.py` 新增 `try_set_flag(name, timeout)` 函数，使用 `SET NX` 原子地检查并设置
- `async_task_decorator` 中用 `try_set_flag` 替代 `has_flag` + `set_flag`

```
请求1 → try_set_flag（成功，返回 True）→ 提交到队列
请求2 → try_set_flag（失败，返回 False）→ 拒绝
请求3 → try_set_flag（失败，返回 False）→ 拒绝
```

## 涉及文件

- `domain_admin/utils/redis_lock_util.py` — 新增 `try_set_flag` 原子操作函数
- `domain_admin/service/async_task_service.py` — `async_task_decorator` 改用 `try_set_flag`

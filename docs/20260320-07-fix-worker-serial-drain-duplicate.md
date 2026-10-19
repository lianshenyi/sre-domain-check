# 修复 Worker 串行消费导致残留任务逐个执行

## 问题

部署了 06 的修复（executing flag 去重）后，删除 Pod 重启，worker 日志仍然出现同一秒内多个相同任务全部 `Job OK`：

```
02:32:04 execute_async_task('...update_all_domain_cert_info_of_user', 7463, ...)
02:32:04 Job OK
02:32:04 execute_async_task('...update_all_domain_cert_info_of_user', 7464, ...)
02:32:04 Job OK
...连续 5 个相同任务全部 Job OK
```

## 根因分析

两个层面的问题：

### 1. executing flag 在 finally 中被立即清除

```python
# 旧代码
finally:
    redis_lock_util.clear_flag('executing:<scope_key>')  # ← 立即删除
    redis_lock_util.clear_flag(pending_flag)
```

RQ worker 是串行消费的，队列中有 5 个相同任务时：

```
任务 7463 执行完 → finally 清除 executing flag →
任务 7464 的 try_set_flag('executing:...') 成功（flag 刚被清除）→ 执行 → 清除 →
任务 7465 的 try_set_flag 成功 → 执行 → ...
```

`try_set_flag` 只能防止并发执行，但 RQ worker 串行消费时，前一个任务清完 flag 后一个就能拿到，所有残留任务逐个执行成功。

### 2. Pod 重启后队列残留任务被全部消费

Redis 队列（`rq:queue:domain-admin`）中的任务在 Pod 重启后仍然存在。Worker 启动后立刻开始消费这些残留任务，而此时所有 flag 和 lock 都已过期或不存在，没有任何去重保护。

## 修复方案

### 1. executing flag 冷却窗口（async_task_service.py）

任务执行完毕后，不立即清除 `executing` flag，而是将其 TTL 缩短为 30 秒：

```python
# 新代码
finally:
    # 不删除 executing flag，而是设置短 TTL 作为冷却窗口
    redis_lock_util.set_flag_ttl('executing:<scope_key>', timeout=30)
    redis_lock_util.clear_flag(pending_flag)
```

这样队列中紧随其后的残留任务在 30 秒内都会被 `try_set_flag` 拒绝并跳过。30 秒后 flag 自动过期，不影响正常的新任务提交。

### 2. Worker 启动时清空残留队列（worker.py）

在 worker 启动、开始消费之前，主动清空 RQ 队列中的残留任务：

```python
def _drain_stale_jobs(connection):
    queue = Queue(name=ASYNC_TASK_QUEUE_NAME, connection=connection)
    count = queue.count
    if count > 0:
        queue.empty()
        print('[worker] drained {} stale job(s)'.format(count))
```

这从源头上避免了 Pod 重启后消费历史残留任务的问题。

### 3. redis_lock_util 新增 set_flag_ttl（redis_lock_util.py）

新增 `set_flag_ttl` 函数，用于将已存在的 flag 重新设置 TTL 而不是删除：

```python
def set_flag_ttl(name, timeout):
    client = get_client()
    key = '{}:flag:{}'.format(REDIS_PREFIX, name)
    client.set(key, '1', ex=timeout)
```

## 涉及文件

- `domain_admin/service/async_task_service.py` — `execute_async_task` 的 finally 块改用 `set_flag_ttl` 冷却窗口
- `domain_admin/utils/redis_lock_util.py` — 新增 `set_flag_ttl` 函数
- `domain_admin/worker.py` — 启动时清空残留队列

## 部署

需要重新构建 backend + worker 镜像（`async_task_service.py` 和 `redis_lock_util.py` 两端都用到）。

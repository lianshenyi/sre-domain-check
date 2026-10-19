# 修复 Worker 端队列残留任务导致重复执行

## 问题

部署了 pending flag + try_set_flag 原子操作修复后，Worker 日志仍然出现同一秒内大量相同任务被执行的情况：

```
02:22:01 execute_async_task('...update_all_domain_cert_info_of_user', 4057, ...)
02:22:01 Job OK (...)
02:22:01 execute_async_task('...update_all_domain_cert_info_of_user', 4058, ...)
02:22:01 Job OK (...)
...连续 12 个相同任务全部 Job OK
```

async_task_row_id 从 349 暴涨到 4068，说明有大量任务被持续提交和执行。

## 根因分析

两个层面的问题：

### 1. 提交端：AsyncTaskModel.create 在 flag 检查之前

```python
# 旧代码顺序
async_task_row = AsyncTaskModel.create(...)  # ← 先创建记录（row_id 递增）
if not try_set_flag(pending_flag):           # ← 再检查 flag
    raise AppException(...)                   # ← 即使拒绝，记录已创建
```

每次请求都会创建一条 AsyncTaskModel 记录，即使后面被 flag 拒绝，row_id 也会无意义地递增。

### 2. 执行端：finally 无条件清除 flag 导致队列残留任务逐个执行

```python
# 旧代码
try:
    # 执行任务...
finally:
    redis_lock_util.clear_flag(pending_flag)  # ← 每个任务执行完都清除 flag
```

当 RQ 队列中已经堆积了多个相同任务时：

```
任务 4057 执行完 → clear_flag → 
任务 4058 开始执行（flag 已清除，execute lock 已释放）→ 执行完 → clear_flag →
任务 4059 开始执行 → ...
```

RQ worker 串行消费，每个任务执行完清除 flag 后，下一个排队的任务就能获取 execute lock 继续执行。所有残留任务都会逐个执行成功。

## 修复方案

### 1. 提交端：flag 检查前置

将 `try_set_flag` 移到 `AsyncTaskModel.create` 之前，被拒绝时不创建数据库记录：

```python
# 新代码顺序
if not try_set_flag(pending_flag):    # ← 先检查 flag
    raise AppException(...)            # ← 拒绝，不创建记录
async_task_row = AsyncTaskModel.create(...)  # ← 通过后才创建
```

### 2. 执行端：Worker 去重保护

在 `execute_async_task` 入口处用 `try_set_flag` 原子操作获取执行权：

```python
got_execution_right = try_set_flag('executing:<scope_key>', timeout=3600)
if not got_execution_right:
    # 已有相同任务在执行，当前是队列残留的重复项，直接跳过
    _update_async_task(row_id, status=False, result='跳过：队列中的重复任务')
    return 'skipped duplicate'
```

执行完毕后在 `finally` 中同时清除 `executing` 和 `pending` 标记。

这样即使队列中有 N 个相同任务排队，只有第一个能获取执行权，其余全部被跳过。

## 涉及文件

- `domain_admin/service/async_task_service.py`
  - `async_task_decorator`：flag 检查前置到 create 之前
  - `execute_async_task`：新增 `executing` flag 去重保护

## 重要：之前的修复可能未生效

之前的修复（04、05）只修改了源码，但如果没有重新构建镜像并部署，生产环境运行的仍然是旧代码。
旧代码中 `async_task_decorator` 没有任何防重复检查，每次 API 调用都会无条件创建记录并提交到 RQ 队列。

本次修复（06）连同之前的修复一起，需要重新构建 backend + worker 镜像并部署。

## 部署步骤

1. 重新构建镜像（backend + worker 都需要，因为 `async_task_service.py` 两端都用到）
2. 部署前先清理 Redis 中的残留
3. 部署新镜像

```bash
# 进入 Redis 清理残留
redis-cli -n 1 keys "domain_admin:flag:pending:*" | xargs -r redis-cli -n 1 del
redis-cli -n 1 keys "domain_admin:flag:executing:*" | xargs -r redis-cli -n 1 del
redis-cli -n 1 keys "domain_admin:lock:execute:*" | xargs -r redis-cli -n 1 del
redis-cli -n 1 del "rq:queue:domain-admin"
```

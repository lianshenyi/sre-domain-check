# 修复 Worker 异步任务失败时 RuntimeError 信息为空

## 问题

Worker 执行 `update_all_domain_cert_info_of_user` 任务失败，但 `kubectl logs` 中只看到：

```
RuntimeError
```

没有任何错误详情，无法定位根因。

## 根因分析

两个层面的问题：

### 1. 异常信息丢失

`execute_async_task` 的 `except` 块中：

```python
except Exception as e:
    is_success = False
    result = e                          # 保存异常对象
    logger.error(traceback.format_exc())
```

后续处理：

```python
if result:
    result = six.text_type(result)      # str(e) 可能返回空字符串
else:
    result = ''

if not is_success:
    raise RuntimeError(result)          # RuntimeError('') → 日志只显示 "RuntimeError"
```

某些异常的 `str()` 返回空字符串（如 `Exception()` 无参数、部分 pymysql 异常），
导致 `six.text_type(e)` 为 `''`，最终 `raise RuntimeError('')` 没有任何有用信息。

### 2. 完整堆栈不可见

`logger` 在生产模式下只写文件（`domain-admin.log`），不输出到 stdout。
`logger.error(traceback.format_exc())` 记录了完整堆栈，但 `kubectl logs` 看不到。

## 修复方案

### 1. 用完整堆栈替代 str(e) 作为 result（async_task_service.py）

```python
except Exception as e:
    is_success = False
    tb_text = traceback.format_exc()
    result = tb_text or six.text_type(e) or repr(e)
    logger.error(tb_text)
    print('[execute_async_task] task failed: func={}, row_id={}\n{}'.format(
        function_name, async_task_row_id, tb_text
    ))
```

- `traceback.format_exc()` 包含完整异常类型、消息和调用栈，不会为空
- `print` 直接输出到 stdout，确保 `kubectl logs` 可见
- 三级 fallback：`traceback` → `str(e)` → `repr(e)`

### 2. result 截断保护

数据库字段可能有长度限制，将 result 截断到 2000 字符：

```python
_update_async_task(async_task_row_id, {
    'result': result[:2000] if result else '',
    ...
})
```

### 3. RuntimeError 兜底消息

```python
if not is_success:
    raise RuntimeError(result or 'unknown error (no detail captured)')
```

## 涉及文件

- `domain_admin/service/async_task_service.py` — `execute_async_task` 的异常处理和 result 逻辑

## 部署

需要重新构建 backend + worker 镜像。

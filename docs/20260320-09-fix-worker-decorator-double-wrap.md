# 修复 Worker 执行任务时装饰器双重执行导致 AppException

## 问题

Worker 执行 `update_all_domain_cert_info_of_user` 任务时抛出 `AppException`：

```
File "/app/domain_admin/service/async_task_service.py", line 264, in execute_async_task
    result = func(*args, **kwargs)
File "/app/domain_admin/service/async_task_service.py", line 326, in wrapper
    raise AppException(_busy_message(function_name, args, kwargs))
```

错误信息为"当前用户的证书更新任务正在执行，请稍后再试"。

## 根因分析

`domain_service.update_all_domain_cert_info_of_user` 被 `@async_task_decorator("更新证书信息")` 装饰。

### API 端提交流程

1. API 调用 `domain_service.update_all_domain_cert_info_of_user(user_id=1)`
2. 实际进入 `wrapper`，设置 `pending` flag，创建 AsyncTask 记录
3. 将 `function_name = 'domain_admin.service.domain_service.update_all_domain_cert_info_of_user'` 序列化入队

### Worker 端执行流程（出错）

1. `execute_async_task` 调用 `_resolve_function(function_name)`
2. `_resolve_function` 通过 `getattr(module, func_name)` 获取模块属性
3. 但模块级别的 `update_all_domain_cert_info_of_user` 已经被装饰器替换为 `wrapper`
4. Worker 调用 `func(*args, **kwargs)` → 实际调用 `wrapper(*args, **kwargs)`
5. `wrapper` 再次检查 `pending` flag → 发现已存在（API 端设置的）→ 抛出 `AppException`

本质上是装饰器的 `wrapper` 在 API 端和 Worker 端被执行了两次：
- API 端：`wrapper` 负责提交任务（正确）
- Worker 端：`wrapper` 应该被跳过，直接执行原始业务函数

## 修复方案

修改 `_resolve_function`，利用 `@wraps` 自动设置的 `__wrapped__` 属性获取原始函数：

```python
def _resolve_function(function_name):
    module_name, func_name = function_name.rsplit('.', 1)
    module = importlib.import_module(module_name)
    func = getattr(module, func_name)
    # async_task_decorator 用 @wraps 装饰了 wrapper，
    # 所以 __wrapped__ 指向原始业务函数。
    # Worker 端必须调用原始函数，否则会再次进入 wrapper
    # 导致重复检查 pending flag 并抛出 AppException。
    return getattr(func, '__wrapped__', func)
```

`functools.wraps` 会自动将原始函数保存在 `wrapper.__wrapped__` 上，`getattr(func, '__wrapped__', func)` 安全地取出原始函数，如果不存在则返回函数本身。

## 涉及文件

- `domain_admin/service/async_task_service.py` — `_resolve_function` 函数

## 部署

需要重新构建 backend + worker 镜像。

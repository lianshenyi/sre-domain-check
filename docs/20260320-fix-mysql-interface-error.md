# 修复 Worker MySQL InterfaceError(0, '') 自动重连

## 问题

Worker 执行异步任务时报错：

```
pymysql.err.InterfaceError: (0, '')
peewee.InterfaceError: (0, '')
```

报错位置在 `async_task_service._update_async_task`，虽然已经用了 `db.connection_context()`，
但 Peewee 的 `connection_context()` 在底层连接已断开时不会自动重连，直接复用损坏的连接对象导致失败。

## 与上次修复的关系

上次修复（`20260320-fix-mysql-lost-connection.md`）将连接粒度从"包裹整个任务"拆分到"每次迭代独立管理"，
解决了长时间持有连接导致超时的问题。但没有处理"连接对象已失效后重连"的场景。

这次是补充修复：当连接已经断开时，自动关闭旧连接并重新建立新连接。

## 根因

- `playhouse.db_url.connect` 创建的是普通 Peewee 数据库实例，没有重连能力
- `connection_context()` 只管打开/关闭，不检测连接健康状态
- pymysql 在连接完全断开时抛出 `InterfaceError(0, '')`，Peewee 不会自动重试

## 修复方案

新增 `reconnect_db.py`，封装带自动重连能力的数据库创建函数：

- 重写 `execute_sql`，捕获 `OperationalError` 和 `InterfaceError`
- 匹配 pymysql 特定错误码（0, 2006, 2013, 2014）
- 关闭旧连接，重新建立连接，重试 SQL
- 仅对 MySQL 类数据库启用，SQLite 不受影响

## 涉及文件

- `domain_admin/model/reconnect_db.py` — 新增，自动重连数据库封装
- `domain_admin/model/base_model.py` — 修改，使用 `reconnect_connect` 替代 `connect`

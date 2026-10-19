# 修复 Worker 启动时 execute_sql 参数不匹配问题

## 问题

Worker 启动时在 `init_database()` 阶段崩溃：

```
File "/app/domain_admin/model/reconnect_db.py", line 39, in execute_sql
    return super().execute_sql(sql, params, commit)
TypeError: execute_sql() takes from 2 to 3 positional arguments but 4 were given
```

触发路径：`init_database()` → `db.get_tables()` → `execute_sql(query, ('VIEW',))`

## 根因

`reconnect_db.py` 中重写的 `execute_sql` 签名为 `(self, sql, params=None, commit=None)`，
并以位置参数方式调用 `super().execute_sql(sql, params, commit)`。

但当前 Peewee 版本的 `MySQLDatabase.execute_sql` 只接受 `(self, sql, params=None)` 两个位置参数，
不接受 `commit` 作为第三个位置参数，导致 TypeError。

## 修复方案

将 `commit=None` 改为 `**kwargs`，透传给 `super().execute_sql()`，
兼容不同 Peewee 版本的签名差异。

## 涉及文件

- `domain_admin/model/reconnect_db.py` — 修改 `execute_sql` 签名，使用 `**kwargs` 透传

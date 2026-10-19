# 首次空库初始化并发竞态修复

- 文档编号：20261019-06
- 关联缺陷：VIDE-31 / DEF-001
- 影响范围：MySQL 空库首次启动时的 backend、worker、scheduler

## 问题

三个业务进程在依赖健康后并行调用 `init_database()`。它们可能在同一时刻读到空表清单，并发执行 Peewee 的建表及索引创建，从而报出重复索引错误并导致进程重启。

## 修复

MySQL 初始化改为使用连接级命名锁 `domain_admin:init_database`。获得锁后才读取表清单并创建缺失表，完成后在 `finally` 中释放锁并关闭连接。SQLite 不使用该锁，保持原有行为。

## 回归

新增 `tests/model/database_test.py`，验证 MySQL 路径会获取并释放命名锁，且只创建缺失表和执行对应初始数据函数。部署复验应在全新 `data/mysql` 目录执行单次 `docker compose up -d --build`，确认 6 个容器均启动且日志不包含 `Duplicate key name`。

# -*- coding: utf-8 -*-
"""数据库初始化的跨进程互斥回归测试。"""
from __future__ import print_function, unicode_literals, absolute_import, division

from types import SimpleNamespace
from unittest.mock import patch

from domain_admin.model import database


class FakeCursor(object):
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeDatabase(object):
    def __init__(self, table_names):
        self.table_names = table_names
        self.queries = []
        self.connected = False
        self.closed = False

    def connect(self):
        self.connected = True

    def get_tables(self):
        return self.table_names

    def execute_sql(self, sql, params):
        self.queries.append((sql, params))
        return FakeCursor((1,))

    def close(self):
        self.closed = True


def test_init_database_serializes_mysql_schema_creation():
    """MySQL 空库初始化必须在命名锁内完成，并在结束后释放锁。"""
    created = []
    initialized = []

    class ExistingModel(object):
        _meta = SimpleNamespace(table_name='existing')

        @staticmethod
        def create_table():
            created.append('existing')

    class NewModel(object):
        _meta = SimpleNamespace(table_name='new')

        @staticmethod
        def create_table():
            created.append('new')

    fake_db = FakeDatabase(['existing'])

    with patch.object(database.base_model, 'db', fake_db), \
            patch.object(database, 'DB_CONNECT_URL', 'mysql://user:pass@mysql/data'), \
            patch.object(database, 'tables', [
                (ExistingModel, None),
                (NewModel, lambda: initialized.append('new')),
            ]):
        database.init_database()

    assert created == ['new']
    assert initialized == ['new']
    assert fake_db.queries == [
        ('SELECT GET_LOCK(%s, %s)', ('domain_admin:init_database', 120)),
        ('SELECT RELEASE_LOCK(%s)', ('domain_admin:init_database',)),
    ]
    assert fake_db.connected is True
    assert fake_db.closed is True

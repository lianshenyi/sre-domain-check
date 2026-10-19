# -*- coding: utf-8 -*-
"""
基于 Peewee ReconnectMixin 的自动重连数据库封装。

原始 ReconnectMixin 只捕获 OperationalError，
但 pymysql 在连接完全断开时抛出 InterfaceError(0, '')，
这里扩展为同时捕获 InterfaceError，确保 Worker/Scheduler
长时间运行后仍能自动恢复数据库连接。

execute_sql 使用 **kwargs 透传额外参数，兼容不同 Peewee 版本
（部分版本的 execute_sql 不接受 commit 位置参数）。
"""
from __future__ import print_function, unicode_literals, absolute_import, division

import logging

from peewee import InterfaceError, OperationalError
from playhouse.db_url import connect, schemes

logger = logging.getLogger('peewee')

# 需要自动重连的异常类型
_RECONNECT_ERRORS = (OperationalError, InterfaceError)

# pymysql 特有的可重连错误码
_PYMYSQL_RECONNECT_CODES = frozenset([
    0,     # InterfaceError(0, '') — 连接已断开
    2006,  # MySQL server has gone away
    2013,  # Lost connection to MySQL server during query
    2014,  # Commands out of sync
])


def _make_reconnect_class(base_class):
    """
    动态为给定的 Database 子类混入自动重连能力。
    """

    class ReconnectDatabase(base_class):
        def execute_sql(self, sql, params=None, **kwargs):
            try:
                return super().execute_sql(sql, params, **kwargs)
            except _RECONNECT_ERRORS as exc:
                exc_args = getattr(exc, 'args', ())
                code = exc_args[0] if exc_args else -1

                if code not in _PYMYSQL_RECONNECT_CODES:
                    raise

                logger.warning(
                    'Database connection lost (code=%s), reconnecting...', code
                )

                if not self.is_closed():
                    self.close()
                self.connect()

                return super().execute_sql(sql, params, **kwargs)

    ReconnectDatabase.__name__ = 'Reconnect' + base_class.__name__
    return ReconnectDatabase


def reconnect_connect(url, **kwargs):
    """
    替代 playhouse.db_url.connect，返回带自动重连能力的数据库实例。

    仅对 MySQL 类数据库启用重连（sqlite 不需要）。
    """
    # 解析 scheme 判断数据库类型
    scheme = url.split('://')[0] if '://' in url else ''

    if scheme in ('mysql', 'mysql+pool'):
        # 找到 playhouse 注册的原始 Database 类
        original_class = schemes.get(scheme)
        if original_class:
            reconnect_class = _make_reconnect_class(original_class)
            # 临时替换 schemes 中的类
            schemes[scheme] = reconnect_class
            try:
                return connect(url=url, **kwargs)
            finally:
                schemes[scheme] = original_class

    # 非 MySQL 或未识别的 scheme，走原始逻辑
    return connect(url=url, **kwargs)

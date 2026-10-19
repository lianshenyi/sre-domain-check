# -*- coding: utf-8 -*-
from __future__ import print_function, unicode_literals, absolute_import, division

from contextlib import contextmanager

from domain_admin.config import REDIS_URL, REDIS_ASYNC_DB, REDIS_PREFIX, REDIS_LOCK_TTL

try:
    from redis import Redis
except ImportError:  # pragma: no cover
    Redis = None


def is_enabled():
    return bool(Redis and REDIS_URL)


def get_client():
    if not Redis:
        raise RuntimeError('redis package is required for redis locks')

    if not REDIS_URL:
        raise RuntimeError('REDIS_URL is required for redis locks')

    return Redis.from_url(REDIS_URL, db=REDIS_ASYNC_DB, decode_responses=True)


@contextmanager
def lock(name, timeout=None, blocking=False):
    if not is_enabled():
        yield True
        return

    client = get_client()
    lock_name = '{}:lock:{}'.format(REDIS_PREFIX, name)
    redis_lock = client.lock(lock_name, timeout=timeout or REDIS_LOCK_TTL, blocking=blocking)
    acquired = redis_lock.acquire(blocking=blocking)

    try:
        yield acquired
    finally:
        if acquired:
            try:
                redis_lock.release()
            except Exception:
                pass


def is_locked(name):
    """检查指定名称的锁是否已被持有"""
    if not is_enabled():
        return False

    client = get_client()
    lock_name = '{}:lock:{}'.format(REDIS_PREFIX, name)
    return client.exists(lock_name) > 0


def set_flag(name, timeout=None):
    """设置一个带 TTL 的标记，用于跨进程状态传递"""
    if not is_enabled():
        return

    client = get_client()
    key = '{}:flag:{}'.format(REDIS_PREFIX, name)
    client.set(key, '1', ex=timeout or REDIS_LOCK_TTL)


def try_set_flag(name, timeout=None):
    """
    原子地设置标记（SET NX）。
    如果标记不存在则设置并返回 True，已存在则返回 False。
    用于替代 has_flag + set_flag 的非原子组合，避免竞态条件。
    """
    if not is_enabled():
        return True

    client = get_client()
    key = '{}:flag:{}'.format(REDIS_PREFIX, name)
    return client.set(key, '1', nx=True, ex=timeout or REDIS_LOCK_TTL)


def clear_flag(name):
    """清除标记"""
    if not is_enabled():
        return

    client = get_client()
    key = '{}:flag:{}'.format(REDIS_PREFIX, name)
    client.delete(key)


def set_flag_ttl(name, timeout):
    """
    将已存在的标记重新设置 TTL，而不是删除它。
    如果标记不存在则创建。用于执行完毕后保留短暂冷却窗口。
    """
    if not is_enabled():
        return

    client = get_client()
    key = '{}:flag:{}'.format(REDIS_PREFIX, name)
    client.set(key, '1', ex=timeout)


def has_flag(name):
    """检查标记是否存在"""
    if not is_enabled():
        return False

    client = get_client()
    key = '{}:flag:{}'.format(REDIS_PREFIX, name)
    return client.exists(key) > 0

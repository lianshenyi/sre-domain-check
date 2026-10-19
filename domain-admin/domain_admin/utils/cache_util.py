# -*- coding: utf-8 -*-
"""
cache_util.py
"""
from __future__ import print_function, unicode_literals, absolute_import, division

import json

from diskcache import Cache

from domain_admin.config import CACHE_DIR, CACHE_BACKEND, REDIS_URL, REDIS_PREFIX, REDIS_CACHE_DB

try:
    from redis import Redis
except ImportError:  # pragma: no cover
    Redis = None


class BaseCacheBackend(object):
    def set(self, key, value, expire=None):
        raise NotImplementedError

    def get(self, key):
        raise NotImplementedError

    def delete(self, key):
        raise NotImplementedError


class DiskCacheBackend(BaseCacheBackend):
    def __init__(self):
        self.cache = Cache(CACHE_DIR)

    def set(self, key, value, expire=None):
        self.cache.set(key=key, value=value, expire=expire)

    def get(self, key):
        return self.cache.get(key=key)

    def delete(self, key):
        self.cache.delete(key)


class RedisCacheBackend(BaseCacheBackend):
    def __init__(self, redis_url, prefix, db):
        if not Redis:
            raise RuntimeError('redis package is required when CACHE_BACKEND=redis')

        if not redis_url:
            raise RuntimeError('REDIS_URL is required when CACHE_BACKEND=redis')

        self.prefix = '{}:cache'.format(prefix)
        self.client = Redis.from_url(redis_url, db=db, decode_responses=True)
        self.client.ping()

    def _key(self, key):
        return '{}:{}'.format(self.prefix, key)

    def set(self, key, value, expire=None):
        payload = json.dumps(value, ensure_ascii=False)
        self.client.set(name=self._key(key), value=payload, ex=expire)

    def get(self, key):
        value = self.client.get(self._key(key))
        if value is None:
            return None
        return json.loads(value)

    def delete(self, key):
        self.client.delete(self._key(key))


def _build_backend():
    backend = (CACHE_BACKEND or 'diskcache').lower().strip()

    if backend == 'redis':
        return RedisCacheBackend(
            redis_url=REDIS_URL,
            prefix=REDIS_PREFIX,
            db=REDIS_CACHE_DB,
        )

    return DiskCacheBackend()


cache_backend = _build_backend()


def set_value(key, value, expire=None):
    """
    存，单位：秒s
    """
    cache_backend.set(key=key, value=value, expire=expire)


def get_value(key):
    """
    取
    """
    return cache_backend.get(key=key)


def delete_value(key):
    """
    删
    """
    return cache_backend.delete(key=key)

# -*- coding: utf-8 -*-
"""
@File    : env_config.py
@Date    : 2023-06-13
"""
from __future__ import print_function, unicode_literals, absolute_import, division
from environs import Env
from .default_config import *

env = Env()

# read .env file, if it exists
env.read_env()

# database
DB_CONNECT_URL = env.str("DB_CONNECT_URL", DEFAULT_DB_CONNECT_URL)

# 初始化 管理员账号，用户名
ADMIN_USERNAME = env.str("ADMIN_USERNAME", DEFAULT_ADMIN_USERNAME)
ADMIN_PASSWORD = env.str("ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD)

# prometheus key
PROMETHEUS_KEY = env.str("PROMETHEUS_KEY", DEFAULT_PROMETHEUS_KEY)

# secret_key
SECRET_KEY = env.str("SECRET_KEY", DEFAULT_SECRET_KEY)

# token_expire_days
TOKEN_EXPIRE_DAYS = env.int("TOKEN_EXPIRE_DAYS", DEFAULT_TOKEN_EXPIRE_DAYS)

# APP_MODE : production, development
APP_MODE = env.str("APP_MODE", 'production')

# cache backend: diskcache / redis
CACHE_BACKEND = env.str("CACHE_BACKEND", DEFAULT_CACHE_BACKEND)

# async task backend: local / redis
ASYNC_TASK_BACKEND = env.str("ASYNC_TASK_BACKEND", DEFAULT_ASYNC_TASK_BACKEND)
ASYNC_TASK_QUEUE_NAME = env.str("ASYNC_TASK_QUEUE_NAME", DEFAULT_ASYNC_TASK_QUEUE_NAME)

# redis config
REDIS_URL = env.str("REDIS_URL", DEFAULT_REDIS_URL)
REDIS_PREFIX = env.str("REDIS_PREFIX", DEFAULT_REDIS_PREFIX)
REDIS_CACHE_DB = env.int("REDIS_CACHE_DB", DEFAULT_REDIS_CACHE_DB)
REDIS_ASYNC_DB = env.int("REDIS_ASYNC_DB", DEFAULT_REDIS_ASYNC_DB)
REDIS_TASK_RESULT_TTL = env.int("REDIS_TASK_RESULT_TTL", DEFAULT_REDIS_TASK_RESULT_TTL)
REDIS_LOCK_TTL = env.int("REDIS_LOCK_TTL", DEFAULT_REDIS_LOCK_TTL)

# scheduler
SCHEDULER_ENABLED = env.bool("SCHEDULER_ENABLED", DEFAULT_SCHEDULER_ENABLED)
SCHEDULER_ROLE = env.str("SCHEDULER_ROLE", DEFAULT_SCHEDULER_ROLE)

# ALLOW_COMMANDS
ALLOW_COMMANDS = [cmd.strip() for cmd in env.str("ALLOW_COMMANDS", '').split(';') if cmd.strip()]

# ENABLED_REGISTER
ENABLED_REGISTER = env.bool("ENABLED_REGISTER", False)

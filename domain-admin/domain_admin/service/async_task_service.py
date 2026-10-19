# -*- coding: utf-8 -*-
"""
异步任务
async_task_service.py
"""

from __future__ import print_function, unicode_literals, absolute_import, division

import importlib
import traceback
from concurrent.futures.thread import ThreadPoolExecutor
from functools import wraps

import six
from flask import g

from domain_admin.config import (
    ASYNC_TASK_BACKEND,
    ASYNC_TASK_QUEUE_NAME,
    REDIS_URL,
    REDIS_PREFIX,
    REDIS_ASYNC_DB,
    REDIS_TASK_RESULT_TTL,
)
from domain_admin.log import logger
from domain_admin.model.base_model import db
from domain_admin.model.log_async_task_model import AsyncTaskModel
from domain_admin.utils import datetime_util, json_util
from domain_admin.utils import redis_lock_util
from domain_admin.utils.flask_ext.app_exception import AppException

try:
    from redis import Redis
    from rq import Queue
except ImportError:  # pragma: no cover
    Redis = None
    Queue = None


executor = ThreadPoolExecutor()


class RedisAsyncTaskExecutor(object):
    def __init__(self):
        if not Redis or not Queue:
            raise RuntimeError('redis and rq packages are required when ASYNC_TASK_BACKEND=redis')

        if not REDIS_URL:
            raise RuntimeError('REDIS_URL is required when ASYNC_TASK_BACKEND=redis')

        self.connection = Redis.from_url(REDIS_URL, db=REDIS_ASYNC_DB, decode_responses=False)
        self.connection.ping()
        self.queue = Queue(
            name=ASYNC_TASK_QUEUE_NAME,
            connection=self.connection,
            default_timeout=3600,
        )

    def submit(self, fn, *args, **kwargs):
        function_name = '{}.{}'.format(fn.__module__, fn.__name__)
        async_task_row_id = kwargs.pop('_async_task_row_id')

        return self.queue.enqueue(
            execute_async_task,
            function_name,
            async_task_row_id,
            args,
            kwargs,
            result_ttl=REDIS_TASK_RESULT_TTL,
            job_timeout=3600,
            meta={
                'function_name': function_name,
                'async_task_row_id': async_task_row_id,
                'redis_prefix': REDIS_PREFIX,
            }
        )


redis_executor = None


def _get_redis_executor():
    global redis_executor

    if redis_executor is None:
        redis_executor = RedisAsyncTaskExecutor()

    return redis_executor


def submit_task(fn, *args, **kwargs):
    """
    执行异步任务
    """
    backend = (ASYNC_TASK_BACKEND or 'local').lower().strip()

    if backend == 'redis':
        return _get_redis_executor().submit(fn, *args, **kwargs)

    return executor.submit(fn, *args, **kwargs)


def _update_async_task(async_task_row_id, data):
    with db.connection_context():
        AsyncTaskModel.update(data).where(AsyncTaskModel.id == async_task_row_id).execute()


def _serialize_params(args, kwargs):
    return json_util.json_encode(
        data={
            'args': list(args),
            'kwargs': kwargs,
        },
        ensure_ascii=False,
    )


def _resolve_function(function_name):
    module_name, func_name = function_name.rsplit('.', 1)
    module = importlib.import_module(module_name)
    func = getattr(module, func_name)
    # async_task_decorator 用 @wraps 装饰了 wrapper，
    # 所以 __wrapped__ 指向原始业务函数。
    # Worker 端必须调用原始函数，否则会再次进入 wrapper
    # 导致重复检查 pending flag 并抛出 AppException。
    return getattr(func, '__wrapped__', func)


def _guess_user_id(args, kwargs):
    user_id = kwargs.get('user_id')

    if user_id is None:
        user_id = kwargs.get('current_user_id')

    if user_id is None and args:
        for value in reversed(args):
            if isinstance(value, int) and value >= 0:
                user_id = value
                break

    return user_id if user_id is not None else 0


def _task_scope_key(function_name, args, kwargs):
    user_id = _guess_user_id(args, kwargs)

    if user_id:
        return 'user:{}:{}'.format(user_id, function_name)

    if function_name.endswith('send_verify_code_async') or function_name.endswith('send_verify_code'):
        email = kwargs.get('email')
        if email is None and args:
            email = args[0]
        if email:
            return 'email:{}:{}'.format(email, function_name)

    if function_name.endswith('auto_import_from_domain_async'):
        root_domain = kwargs.get('root_domain')
        if root_domain is None and args:
            root_domain = args[0]
        if root_domain:
            return 'domain:{}:{}'.format(root_domain, function_name)

    return 'global:{}'.format(function_name)


def _busy_message(function_name, args, kwargs):
    user_id = _guess_user_id(args, kwargs)

    if function_name.endswith('send_verify_code_async') or function_name.endswith('send_verify_code'):
        return '验证码发送任务正在处理中，请稍后再试'

    if function_name.endswith('update_all_domain_cert_info_of_user'):
        return '当前用户的证书更新任务正在执行，请稍后再试'

    if function_name.endswith('update_all_domain_info_of_user'):
        return '当前用户的域名信息同步任务正在执行，请稍后再试'

    if function_name.endswith('update_all_domain_icp_of_user'):
        return '当前用户的ICP备案补全任务正在执行，请稍后再试'

    if function_name.endswith('handle_auto_import_domain_info'):
        return '当前用户的域名导入初始化任务正在执行，请稍后再试'

    if function_name.endswith('run_init_monitor_task_async'):
        return '当前用户的监控初始化任务正在执行，请稍后再试'

    if function_name.endswith('auto_import_from_domain_batch_async'):
        return '当前用户的子域名批量导入任务正在执行，请稍后再试'

    if function_name.endswith('auto_import_from_domain_async'):
        return '当前用户的子域名导入任务正在执行，请稍后再试'

    if user_id:
        return '当前用户已有同类任务正在执行，请稍后再试'

    return '已有同类任务正在执行，请稍后再试'


def _get_worker_app():
    """
    获取 worker 进程的 Flask app 实例。
    RQ fork 子进程后 app context 会丢失，需要重新创建。
    """
    from domain_admin.utils.flask_ext.flask_app import FlaskApp
    return FlaskApp(import_name=__name__)


def execute_async_task(function_name, async_task_row_id, args=None, kwargs=None):
    """
    Redis worker entrypoint
    """
    if not function_name:
        logger.error(
            'execute_async_task called without function_name, '
            'async_task_row_id=%s',
            async_task_row_id,
        )
        raise RuntimeError(
            'function_name is required. '
            'This job may be a stale entry from an older version. '
            'Please clear the Redis queue and retry.'
        )

    args = tuple(args or [])
    kwargs = kwargs or {}

    result = ''
    is_success = None
    scope_key = _task_scope_key(function_name, args, kwargs)
    lock_name = 'execute:{}'.format(scope_key)
    pending_flag = 'pending:{}'.format(scope_key)

    # Worker 端去重：用原子 SET NX 获取执行权。
    # 如果 flag 已存在，说明有相同任务正在执行或已提交，
    # 当前任务是队列中的残留重复项，直接跳过。
    got_execution_right = redis_lock_util.try_set_flag(
        'executing:{}'.format(scope_key), timeout=3600
    )
    if not got_execution_right:
        logger.info(
            'skip duplicate queued task: %s (row_id=%s)',
            function_name, async_task_row_id,
        )
        _update_async_task(async_task_row_id, {
            'status': False,
            'result': '跳过：队列中的重复任务',
            'end_time': datetime_util.get_datetime(),
            'update_time': datetime_util.get_datetime(),
        })
        return 'skipped duplicate'

    # RQ worker fork 子进程执行任务时 Flask app context 会丢失，
    # 而被 @async_task_decorator 装饰的函数内部会访问 flask.g，
    # 所以这里需要手动推入 app context。
    worker_app = _get_worker_app()

    try:
        with worker_app.app_context():
            with redis_lock_util.lock(lock_name, blocking=False) as acquired:
                if not acquired:
                    result = _busy_message(function_name, args, kwargs)
                    is_success = False
                else:
                    func = _resolve_function(function_name)
                    # 不再用 connection_context 包裹整个任务函数，
                    # 避免长时间网络 I/O 导致 MySQL 连接超时断开。
                    # 各任务函数自行管理数据库连接。
                    result = func(*args, **kwargs)
                    is_success = True
    except Exception as e:
        is_success = False
        # 保存完整堆栈作为 result，避免某些异常 str() 返回空字符串
        # （如 Exception() 无参数、InterfaceError(0, '') 等）导致丢失错误信息
        tb_text = traceback.format_exc()
        result = tb_text or six.text_type(e) or repr(e)
        logger.error(tb_text)
        # 生产模式 logger 只写文件，print 确保 kubectl logs 可见
        print('[execute_async_task] task failed: func={}, row_id={}\n{}'.format(
            function_name, async_task_row_id, tb_text
        ))
    finally:
        # 任务执行完毕，清除 pending 标记允许后续提交新任务。
        # executing flag 不立即清除，而是设置短 TTL（30s）作为冷却窗口，
        # 让队列中紧随其后的残留重复任务在此窗口内被 try_set_flag 拒绝。
        # 如果立即清除，RQ 串行消费时下一个残留任务会立刻获取到 flag 继续执行。
        redis_lock_util.set_flag_ttl('executing:{}'.format(scope_key), timeout=30)
        redis_lock_util.clear_flag(pending_flag)

    if result:
        result = six.text_type(result)
    else:
        result = ''

    _update_async_task(async_task_row_id, {
        'status': is_success,
        'result': result[:2000] if result else '',
        'end_time': datetime_util.get_datetime(),
        'update_time': datetime_util.get_datetime(),
    })

    if not is_success:
        raise RuntimeError(result or 'unknown error (no detail captured)')

    return result


def async_task_decorator(task_name):
    """
    执行异步任务的装饰器
    """

    def outer_wrapper(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if hasattr(g, 'user_id'):
                current_user_id = g.user_id
            else:
                current_user_id = 0

            backend = (ASYNC_TASK_BACKEND or 'local').lower().strip()

            if backend == 'redis':
                function_name = '{}.{}'.format(func.__module__, func.__name__)
                scope_key = _task_scope_key(function_name, args, kwargs)
                pending_flag = 'pending:{}'.format(scope_key)

                # 先检查 pending 标记，避免创建无意义的数据库记录
                # 原子地检查并设置（SET NX），防止并发提交
                if not redis_lock_util.try_set_flag(pending_flag, timeout=3600):
                    raise AppException(_busy_message(function_name, args, kwargs))

                async_task_row = AsyncTaskModel.create(
                    user_id=current_user_id,
                    task_name=task_name,
                    function_name=function_name,
                    params=_serialize_params(args, kwargs),
                    start_time=datetime_util.get_datetime()
                )

                try:
                    submit_task(func, *args, _async_task_row_id=async_task_row.id, **kwargs)
                except Exception:
                    # 提交失败时清除标记
                    redis_lock_util.clear_flag(pending_flag)
                    raise

                return async_task_row

            # local 模式
            async_task_row = AsyncTaskModel.create(
                user_id=current_user_id,
                task_name=task_name,
                function_name='{}.{}'.format(func.__module__, func.__name__),
                params=_serialize_params(args, kwargs),
                start_time=datetime_util.get_datetime()
            )

            def done_callback(future):
                is_success = None
                result = ''

                try:
                    result = future.result()
                    is_success = True
                except Exception as e:
                    is_success = False
                    result = e
                    logger.error(traceback.format_exc())

                if result:
                    result = six.text_type(result)
                else:
                    result = ''

                _update_async_task(async_task_row.id, {
                    'status': is_success,
                    'result': result,
                    'end_time': datetime_util.get_datetime(),
                    'update_time': datetime_util.get_datetime(),
                })

            ret = submit_task(func, *args, **kwargs)
            ret.add_done_callback(done_callback)
            return ret

        return wrapper

    return outer_wrapper


def sync_task_decorator(task_name):
    """
    同步任务的日志装饰器
    """

    def outer_wrapper(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            current_user_id = 0

            try:
                current_user_id = g.user_id
            except Exception:
                pass

            async_task_row = AsyncTaskModel.create(
                user_id=current_user_id,
                task_name=task_name,
                function_name='{}.{}'.format(func.__module__, func.__name__),
                start_time=datetime_util.get_datetime()
            )

            result = ''
            error = None

            try:
                result = func(*args, **kwargs)
            except Exception as e:
                error = e

            if error:
                result = six.text_type(error)

            data = {
                'status': False if error else True,
                'params': _serialize_params(args, kwargs),
                'result': result or '',
                'end_time': datetime_util.get_datetime(),
                'update_time': datetime_util.get_datetime(),
            }

            AsyncTaskModel.update(data).where(
                AsyncTaskModel.id == async_task_row.id
            ).execute()

            if error:
                raise error
            else:
                return result

        return wrapper

    return outer_wrapper

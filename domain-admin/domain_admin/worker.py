# -*- coding: utf-8 -*-
"""
Redis async worker for domain-admin
"""
from __future__ import print_function, unicode_literals, absolute_import, division

from redis import Redis
from rq import Connection, Queue, Worker

from domain_admin.config import REDIS_URL, REDIS_ASYNC_DB, ASYNC_TASK_QUEUE_NAME
from domain_admin.model.database import init_database
from domain_admin.service.system_service import init_system_config
from domain_admin.utils.flask_ext.flask_app import FlaskApp

app = FlaskApp(import_name=__name__)


def _drain_stale_jobs(connection):
    """
    Worker 启动时清空队列中的残留任务。
    Pod 重启后队列里可能有上一轮堆积的重复任务，
    如果不清理，worker 会逐个消费导致重复执行。
    """
    queue = Queue(name=ASYNC_TASK_QUEUE_NAME, connection=connection)
    count = queue.count
    if count > 0:
        queue.empty()
        print('[worker] drained {} stale job(s) from queue "{}"'.format(count, ASYNC_TASK_QUEUE_NAME))
    else:
        print('[worker] queue "{}" is clean, no stale jobs'.format(ASYNC_TASK_QUEUE_NAME))


def main():
    if not REDIS_URL:
        raise RuntimeError('REDIS_URL is required to start async worker')

    init_database()
    init_system_config(app)

    connection = Redis.from_url(REDIS_URL, db=REDIS_ASYNC_DB, decode_responses=False)

    _drain_stale_jobs(connection)

    with app.app_context():
        with Connection(connection):
            worker = Worker([ASYNC_TASK_QUEUE_NAME])
            worker.work()


if __name__ == '__main__':
    main()

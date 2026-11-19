import json
import socket
import subprocess
from contextlib import nullcontext
from threading import Event
from time import monotonic

import pytest
from flask import Flask, g
from peewee import SqliteDatabase

from domain_admin.api import domain_api
from domain_admin.enums.role_enum import RoleEnum
from domain_admin.enums.source_enum import SourceEnum
from domain_admin.model.address_model import AddressModel
from domain_admin.model.domain_info_model import DomainInfoModel
from domain_admin.model.domain_model import DomainModel
from domain_admin.model.group_model import GroupModel
from domain_admin.model.group_user_model import GroupUserModel
from domain_admin.model.log_async_task_model import AsyncTaskModel
from domain_admin.service import async_task_service, domain_service
from domain_admin.utils.flask_ext.app_exception import DataNotFoundAppException


@pytest.fixture
def database(tmp_path, monkeypatch):
    database = SqliteDatabase(str(tmp_path / 'batch.db'))
    models = [DomainModel, AddressModel, AsyncTaskModel, GroupUserModel, DomainInfoModel, GroupModel]
    monkeypatch.setattr(domain_service, 'db', database)
    monkeypatch.setattr(async_task_service, 'db', database)
    with database.bind_ctx(models):
        with database.connection_context():
            database.create_tables(models)
        yield database
        database.close()


@pytest.fixture
def app():
    return Flask(__name__)


def _status(app, task_id, user_id=1):
    with app.test_request_context(json={'task_id': task_id}):
        g.user_id = user_id
        return domain_api.get_domain_cert_batch_progress.__wrapped__()


def test_local_batch_counts_failure_and_continues_after_slow_item(app, database, monkeypatch):
    monkeypatch.setattr(async_task_service, 'ASYNC_TASK_BACKEND', 'local')
    fast_progress = Event()
    terminal = Event()
    wait_for_poll = Event()
    slow = DomainModel.create(user_id=1, domain='slow.example.test')
    broken = DomainModel.create(user_id=1, domain='broken.example.test')
    fast = DomainModel.create(user_id=1, domain='fast.example.test')
    DomainModel.create(user_id=1, domain='later.example.test')
    DomainModel.create(user_id=2, domain='private.example.test')
    AddressModel.create(domain_id=str(slow.id), host='192.0.2.2')
    AddressModel.create(domain_id=str(fast.id), host='192.0.2.1', source=SourceEnum.MANUAL, comment='保留')
    database.close()
    monkeypatch.setattr(domain_service, 'BATCH_PROBE_WORKERS', 3)

    def probe(row, hosts, timeout):
        if row.id == slow.id:
            assert wait_for_poll.wait(5)
            raise subprocess.TimeoutExpired('probe', timeout)
        if row.id == broken.id:
            return dict(root_domain='example.test', resolved_hosts=['192.0.2.3'],
                        certificates={'192.0.2.3': None})
        assert hosts == (['192.0.2.1'] if row.id == fast.id else [])
        return dict(root_domain='example.test', resolved_hosts=['192.0.2.1'], certificates={
            '192.0.2.1': {'start_date': '2026-01-01T00:00:00', 'expire_date': '2099-01-01T00:00:00'},
        })

    update_task = async_task_service._update_async_task

    def observe(task_id, values):
        update_task(task_id, values)
        if 'status' in values:
            terminal.set()
        elif json.loads(values['result'])['completed'] == 2:
            fast_progress.set()

    monkeypatch.setattr(domain_service, '_run_batch_probe', probe)
    monkeypatch.setattr(async_task_service, '_update_async_task', observe)

    with app.test_request_context(json={}):
        g.user_id = 1
        task_id = domain_api.update_all_domain_cert_info_of_user.__wrapped__()['task_id']

    try:
        assert fast_progress.wait(5)
        assert _status(app, task_id) == dict(task_id=task_id, state='running', total=4,
                                             completed=2, success=1, failed=1)
        with pytest.raises(DataNotFoundAppException):
            _status(app, task_id, user_id=2)
    finally:
        wait_for_poll.set()
        assert terminal.wait(5)

    assert _status(app, task_id) == dict(task_id=task_id, state='failed', total=4,
                                         completed=4, success=2, failed=2)
    assert AsyncTaskModel.get_by_id(task_id).end_time is not None
    assert AddressModel.get(AddressModel.domain_id == str(slow.id)).host == '192.0.2.2'
    assert AddressModel.get(AddressModel.domain_id == str(fast.id)).comment == '保留'
    assert DomainModel.get_by_id(fast.id).connect_status is True


def test_probe_process_has_wall_clock_timeout(database):
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        row = DomainModel(domain='127.0.0.1', port=listener.getsockname()[1], root_domain='example.test')
        started = monotonic()
        with pytest.raises(subprocess.TimeoutExpired):
            domain_service._run_batch_probe(row, [], 1)
        assert monotonic() - started < 4
        listener.settimeout(1)
        connection, _ = listener.accept()
        with connection:
            connection.settimeout(1)
            assert connection.recv(4096)
            assert connection.recv(1) == b''


def test_redis_batch_reports_empty_success_and_releases_scope(app, database, monkeypatch):
    function_name = 'domain_admin.service.domain_service.update_all_domain_cert_info_of_user'
    task = AsyncTaskModel.create(user_id=1, task_name='更新证书信息', function_name=function_name)
    assert _status(app, task.id)['state'] == 'queued'
    database.close()
    pending_flag = f'pending:user:1:{function_name}'
    flags = {pending_flag}

    def claim(name, timeout):
        if name in flags:
            return False
        flags.add(name)
        return True

    monkeypatch.setattr(async_task_service, '_get_worker_app', lambda: app)
    monkeypatch.setattr(async_task_service.redis_lock_util, 'try_set_flag', claim)
    monkeypatch.setattr(async_task_service.redis_lock_util, 'clear_flag', flags.discard)
    monkeypatch.setattr(async_task_service.redis_lock_util, 'lock', lambda *args, **kwargs: nullcontext(True))

    for task_id in (task.id, AsyncTaskModel.create(user_id=1, task_name='更新证书信息',
                                                 function_name=function_name).id):
        database.close()
        flags.add(pending_flag)
        async_task_service.execute_async_task(function_name, task_id, kwargs={'user_id': 1})
        assert _status(app, task_id) == dict(task_id=task_id, state='succeeded', total=0,
                                             completed=0, success=0, failed=0)
        assert flags == set()

    DomainModel.create(user_id=1, domain='expired-budget.example.test')
    task = AsyncTaskModel.create(user_id=1, task_name='更新证书信息', function_name=function_name)
    database.close()
    monkeypatch.setattr(domain_service, 'BATCH_PROBE_BUDGET', 0)
    flags.add(pending_flag)
    with pytest.raises(RuntimeError, match='"failed": 1'):
        async_task_service.execute_async_task(function_name, task.id, kwargs={'user_id': 1})
    assert _status(app, task.id) == dict(task_id=task.id, state='failed', total=1,
                                         completed=1, success=0, failed=1)
    assert flags == set()


def test_list_filters_keep_read_and_edit_scope(app, database):
    GroupUserModel.create(user_id=1, group_id=2, has_edit_permission=False)
    owned = DomainModel.create(user_id=1, group_id=2, domain='own.example.test')
    shared = DomainModel.create(user_id=2, group_id=2, domain='shared.example.test')
    DomainModel.create(user_id=2, group_id=3, domain='private.example.test')
    with app.test_request_context(json={'role': RoleEnum.USER, 'group_ids': [2]}):
        g.user_id = 1
        assert {row['id']: row['has_edit_permission'] for row in domain_api.get_domain_list.__wrapped__()['list']} == {
            owned.id: True, shared.id: False,
        }

# -*- coding: utf-8 -*-
import json
import re
from functools import wraps

from flask import current_app, g, request, send_file

from domain_admin import agent_runner
from domain_admin.enums.role_enum import RoleEnum
from domain_admin.service import agent_service, auth_service
from domain_admin.utils.flask_ext.app_exception import (
    AppException,
    UnauthorizedAppException,
)

MAX_BODY_BYTES = 128 * 1024


def _admin_only(function):
    permission = auth_service.permission(role=RoleEnum.ADMIN)(function)

    @wraps(function)
    def wrapped():
        if not getattr(g, 'user_id', None):
            raise UnauthorizedAppException()
        return permission()

    return wrapped


def _body() -> dict:
    if request.content_length and request.content_length > MAX_BODY_BYTES:
        raise AppException('请求体过大', 413)
    raw = request.stream.read(MAX_BODY_BYTES + 1)
    if len(raw) > MAX_BODY_BYTES:
        raise AppException('请求体过大', 413)
    try:
        value = json.loads(raw)
    except (ValueError, RecursionError):
        raise AppException('需要 JSON 对象', 400) from None
    if not isinstance(value, dict):
        raise AppException('需要 JSON 对象', 400)
    return value


def _id(value) -> int:
    if type(value) is not int or not 1 <= value <= 2147483647:
        raise AppException('ID 必须是正整数', 400)
    return value


def _label(value) -> str:
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 64:
        raise AppException('名称和地区需要 1–64 个字符', 400)
    return value.strip()


def _origin(value) -> str:
    try:
        return agent_runner.normalize_origin(value)
    except ValueError:
        raise AppException('需要 HTTPS 控制端 origin', 400) from None


def _agent_secret() -> str:
    auth = request.headers.get('Authorization', '')
    scheme, _, token = auth.partition(' ')
    if scheme.lower() != 'bearer' or not agent_runner.SECRET_PATTERN.fullmatch(token):
        raise AppException('Agent 凭据无效', 401)
    return token


def _secret_response(payload: dict):
    response = current_app.make_response(payload)
    response.headers['Cache-Control'] = 'no-store'
    return response


@_admin_only
def create_agent():
    body = _body()
    return _secret_response(agent_service.issue_enrollment(
        _origin(body.get('origin')), name=_label(body.get('name')), region=_label(body.get('region')),
    ))


@_admin_only
def renew_agent_enrollment():
    body = _body()
    return _secret_response(agent_service.issue_enrollment(
        _origin(body.get('origin')), node_id=_id(body.get('agent_id')),
    ))


@_admin_only
def revoke_agent():
    return agent_service.revoke(_id(_body().get('agent_id')))


@_admin_only
def get_agent_list():
    return agent_service.list_agents()


@_admin_only
def start_agent_domain_check():
    body = _body()
    ids = body.get('agent_ids')
    if not isinstance(ids, list) or not 1 <= len(ids) <= 10:
        raise AppException('请选择 1–10 个 Agent', 400)
    agent_ids = [_id(value) for value in ids]
    if len(set(agent_ids)) != len(agent_ids):
        raise AppException('Agent ID 不能重复', 400)
    return agent_service.start_check(_id(body.get('domain_id')), agent_ids, g.user_id)


@_admin_only
def get_agent_check_results():
    body = _body()
    batch_id = body.get('batch_id')
    if batch_id is not None and (not isinstance(batch_id, str) or not re.fullmatch(r'[a-f0-9]{32}', batch_id)):
        raise AppException('批次 ID 无效', 400)
    return agent_service.list_results(_id(body.get('domain_id')), batch_id, g.user_id)


def get_agent_runner():
    return send_file(agent_runner.__file__, mimetype='text/x-python', as_attachment=True, download_name='agent.py')


def enroll_agent():
    code = _agent_secret()
    return _secret_response(agent_service.enroll(_id(_body().get('agent_id')), code))


def poll_agent_task():
    token = _agent_secret()
    return agent_service.poll(_id(_body().get('agent_id')), token)


def submit_agent_task_result():
    token = _agent_secret()
    body = _body()
    return agent_service.submit_result(_id(body.get('agent_id')), token, _id(body.get('task_id')), body)

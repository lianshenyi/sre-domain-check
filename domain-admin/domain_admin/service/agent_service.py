# -*- coding: utf-8 -*-
import base64
import binascii
import hashlib
import shlex
from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe
from typing import List, Optional
from uuid import uuid4

from OpenSSL import crypto

from domain_admin.agent_runner import normalize_target
from domain_admin.enums.ssl_type_enum import SSLTypeEnum
from domain_admin.model.agent_model import AgentCheck, AgentNode
from domain_admin.model.base_model import db
from domain_admin.model.domain_model import DomainModel
from domain_admin.service import domain_service
from domain_admin.utils.cert_util import cert_openssl_v2
from domain_admin.utils.flask_ext.app_exception import (
    AppException,
    DataNotFoundAppException,
    ForbiddenAppException,
)

POLL_INTERVAL_SECONDS = 10
ONLINE_WINDOW = timedelta(seconds=60)
ENROLLMENT_TTL = timedelta(minutes=15)
CHECK_TTL = timedelta(minutes=5)
ACTIVE_STATES = ('queued', 'running')
MAX_CERTIFICATE_LENGTH = 96 * 1024


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def _digest(secret: str) -> str:
    return hashlib.sha256(secret.encode('ascii')).hexdigest()


def _utc_label(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat(timespec='seconds') + 'Z' if value is not None else None


def agent_view(node: AgentNode, now: datetime) -> dict:
    if node.credential_hash:
        status = 'online' if node.last_seen_at and now - node.last_seen_at < ONLINE_WINDOW else 'offline'
    else:
        status = 'pending' if node.enrollment_expires_at is not None else 'revoked'
    return {
        'id': node.id,
        'name': node.name,
        'region': node.region,
        'status': status,
        'last_seen_at': _utc_label(node.last_seen_at),
        'enrollment_expires_at': _utc_label(node.enrollment_expires_at),
    }


def list_agents() -> List[dict]:
    now = now_utc()
    return [agent_view(node, now) for node in AgentNode.select().order_by(AgentNode.id)]


def _check_view(check: AgentCheck, node: AgentNode, now: datetime) -> dict:
    expired = check.status in ACTIVE_STATES and check.deadline_at <= now
    return {
        'id': check.id,
        'batch_id': check.batch_id,
        'domain_id': check.domain_id,
        'domain': check.domain,
        'port': check.port,
        'agent_id': node.id,
        'agent_name': node.name,
        'region': node.region,
        'status': 'expired' if expired else check.status,
        'created_at': _utc_label(check.created_at),
        'deadline_at': _utc_label(check.deadline_at),
        'finished_at': _utc_label(check.deadline_at if expired else check.finished_at),
        'cert_starts_at': _utc_label(check.cert_starts_at),
        'cert_expires_at': _utc_label(check.cert_expires_at),
        'error': 'deadline_exceeded' if expired else check.error,
    }


def _install_command(node_id: int, origin: str) -> str:
    install_dir = f'"$HOME/.domain-check-agent/{node_id}"'
    source = shlex.quote(origin + '/api/getAgentRunner')
    return (
        f'umask 077; mkdir -p {install_dir} && cd {install_dir} && '
        f'curl --proto "=https" -fsS {source} -o agent.py.download && '
        f'mv agent.py.download agent.py && python3 agent.py --server {shlex.quote(origin)} --agent-id {node_id} --enroll'
    )


def _set_credentials(node_id: int, code: Optional[str], now: datetime) -> AgentNode:
    # 节点行先加写锁，使轮换、领取、回报和入队按同一顺序串行化。
    AgentNode.update(
        credential_hash=None,
        enrollment_hash=_digest(code) if code else None,
        enrollment_expires_at=now + ENROLLMENT_TTL if code else None,
        last_seen_at=None,
    ).where(AgentNode.id == node_id).execute()
    node = AgentNode.get_by_id(node_id)
    AgentCheck.update(status='canceled', finished_at=now, error='credential_revoked').where(
        AgentCheck.agent_id == node_id,
        AgentCheck.status.in_(ACTIVE_STATES),
        AgentCheck.deadline_at > now,
    ).execute()
    return node


def issue_enrollment(origin: str, *, node_id: Optional[int] = None, name: Optional[str] = None, region: Optional[str] = None) -> dict:
    now = now_utc()
    code = token_urlsafe(32)
    with db.atomic():
        if node_id is None:
            node_id = AgentNode.create(name=name, region=region).id
        node = _set_credentials(node_id, code, now)
    return {
        'agent': agent_view(node, now),
        'enrollment_code': code,
        'install_command': _install_command(node.id, origin),
    }


def revoke(node_id: int) -> dict:
    now = now_utc()
    with db.atomic():
        node = _set_credentials(node_id, None, now)
    return agent_view(node, now)


def enroll(node_id: int, code: str) -> dict:
    now = now_utc()
    token = token_urlsafe(32)
    updated = AgentNode.update(
        credential_hash=_digest(token),
        enrollment_hash=None,
        enrollment_expires_at=None,
        last_seen_at=now,
    ).where(
        AgentNode.id == node_id,
        AgentNode.enrollment_hash == _digest(code),
        AgentNode.enrollment_expires_at > now,
    ).execute()
    if not updated:
        raise AppException('安装码无效或已过期', 401)
    return {'agent_token': token, 'poll_interval_seconds': POLL_INTERVAL_SECONDS}


def _heartbeat(node_id: int, token: str, now: datetime) -> AgentNode:
    match = (AgentNode.id == node_id) & (AgentNode.credential_hash == _digest(token))
    AgentNode.update(last_seen_at=now).where(match).execute()
    node = AgentNode.get_or_none(match)
    if node is None:
        raise AppException('Agent 凭据无效', 401)
    return node


def _matches_current_domain(check: AgentCheck) -> bool:
    entry = DomainModel.get_or_none(DomainModel.id == check.domain_id)
    return entry is not None and (entry.create_time, entry.domain, entry.port, entry.ssl_type) == (
        check.domain_created_at, check.domain, check.port, check.ssl_type,
    )


def _protocol(port: int, ssl_type: int) -> str:
    if port == 21:
        return 'ftps'
    return 'smtp_starttls' if ssl_type == SSLTypeEnum.START_TLS else 'tls'


def start_check(domain_id: int, node_ids: List[int], user_id: int) -> dict:
    now = now_utc()
    batch_id = uuid4().hex
    with db.atomic():
        for node_id in sorted(node_ids):
            # 空更新锁住节点配置，防止入队与凭据撤销交错。
            AgentNode.update(last_seen_at=AgentNode.last_seen_at).where(AgentNode.id == node_id).execute()
        nodes = {node.id: node for node in AgentNode.select().where(AgentNode.id.in_(node_ids))}
        if len(nodes) != len(node_ids) or any(not node.credential_hash for node in nodes.values()):
            raise AppException('请选择已完成登记的 Agent', 400)
        entry = _get_domain(domain_id, user_id)
        try:
            normalize_target(entry.domain, entry.port)
        except ValueError:
            raise AppException('域名记录的主机名或端口无效', 400) from None
        if entry.ssl_type not in (SSLTypeEnum.SSL_TLS, SSLTypeEnum.START_TLS):
            raise AppException('域名记录的证书协议无效', 400)
        checks = [
            AgentCheck.create(
                batch_id=batch_id, domain_id=entry.id, domain_created_at=entry.create_time,
                domain=entry.domain, port=entry.port, ssl_type=entry.ssl_type,
                agent_id=node_id, created_at=now, deadline_at=now + CHECK_TTL,
            )
            for node_id in node_ids
        ]
    return {'batch_id': batch_id, 'results': [_check_view(check, nodes[check.agent_id], now) for check in checks]}


def _get_domain(domain_id: int, user_id: int) -> DomainModel:
    entry = DomainModel.get_or_none(DomainModel.id == domain_id)
    if entry is None:
        raise DataNotFoundAppException()
    if not domain_service.has_read_permission(entry, user_id):
        raise ForbiddenAppException()
    return entry


def list_results(domain_id: int, batch_id: Optional[str], user_id: int) -> List[dict]:
    entry = _get_domain(domain_id, user_id)
    query = AgentCheck.select().where(
        AgentCheck.domain_id == domain_id,
        AgentCheck.domain_created_at == entry.create_time,
    )
    if batch_id is not None:
        query = query.where(AgentCheck.batch_id == batch_id)
    checks = list(query.order_by(AgentCheck.id.desc()).limit(50))
    if not checks:
        return []
    node_ids = {check.agent_id for check in checks}
    nodes = {node.id: node for node in AgentNode.select().where(AgentNode.id.in_(node_ids))}
    now = now_utc()
    return [_check_view(check, nodes[check.agent_id], now) for check in checks]


def poll(node_id: int, token: str) -> dict:
    now = now_utc()
    task = None
    with db.atomic():
        _heartbeat(node_id, token, now)
        check = AgentCheck.select().where(
            AgentCheck.agent_id == node_id,
            AgentCheck.status == 'queued',
            AgentCheck.deadline_at > now,
        ).order_by(AgentCheck.id).first()
        if check is not None:
            if _matches_current_domain(check):
                check.status = 'running'
                check.save(only=[AgentCheck.status])
                task = {
                    'id': check.id,
                    'type': 'domain_tls',
                    'domain': normalize_target(check.domain, check.port),
                    'port': check.port,
                    'protocol': _protocol(check.port, check.ssl_type),
                }
            else:
                _cancel_changed_domain(check, now)
    return {'task': task, 'poll_interval_seconds': POLL_INTERVAL_SECONDS}


def _cancel_changed_domain(check: AgentCheck, now: datetime) -> None:
    check.status = 'canceled'
    check.error = 'domain_changed'
    check.finished_at = now
    check.save(only=[AgentCheck.status, AgentCheck.error, AgentCheck.finished_at])


def _read_certificate(check: AgentCheck, encoded: str) -> None:
    if not isinstance(encoded, str) or not encoded or len(encoded) > MAX_CERTIFICATE_LENGTH:
        raise AppException('证书载荷无效', 400)
    try:
        cert = crypto.load_certificate(crypto.FILETYPE_ASN1, base64.b64decode(encoded, validate=True))
        starts = datetime.strptime(cert.get_notBefore().decode('ascii'), '%Y%m%d%H%M%SZ')
        expires = datetime.strptime(cert.get_notAfter().decode('ascii'), '%Y%m%d%H%M%SZ')
    except (binascii.Error, crypto.Error, AttributeError, ValueError):
        check.error = 'invalid_certificate'
        return
    domain = normalize_target(check.domain, check.port)
    try:
        matches = cert_openssl_v2.verify_cert(cert, domain)
    except (AttributeError, UnicodeError, ValueError, crypto.Error):
        matches = False
    if not matches:
        check.error = 'name_mismatch'
        return
    check.cert_starts_at = starts
    check.cert_expires_at = expires


def submit_result(node_id: int, token: str, check_id: int, payload: dict) -> dict:
    now = now_utc()
    with db.atomic():
        node = _heartbeat(node_id, token, now)
        check = AgentCheck.get_or_none(AgentCheck.id == check_id, AgentCheck.agent_id == node_id)
        if check is None:
            raise AppException('任务不可回报', 409)
        if check.status in ('succeeded', 'failed'):
            return _check_view(check, node, now)
        if check.status != 'running' or check.deadline_at <= now:
            raise AppException('任务不可回报', 409)
        if not _matches_current_domain(check):
            _cancel_changed_domain(check, now)
        else:
            if 'certificate_der' in payload and 'error' not in payload:
                _read_certificate(check, payload['certificate_der'])
            elif payload.get('error') == 'probe_failed' and 'certificate_der' not in payload:
                check.error = 'probe_failed'
            else:
                raise AppException('任务结果无效', 400)
            check.status = 'failed' if check.error else 'succeeded'
            check.finished_at = now
            check.save(only=[
                AgentCheck.status, AgentCheck.error, AgentCheck.finished_at,
                AgentCheck.cert_starts_at, AgentCheck.cert_expires_at,
            ])
        return _check_view(check, node, now)

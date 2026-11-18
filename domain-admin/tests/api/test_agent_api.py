# -*- coding: utf-8 -*-
import ipaddress
import socket
import ssl
from contextlib import ExitStack, contextmanager
from datetime import datetime, timedelta
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import StreamRequestHandler, TCPServer
from threading import Thread

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from domain_admin import agent_runner
from domain_admin.enums.role_enum import RoleEnum
from domain_admin.main import app
from domain_admin.model.agent_model import AgentCheck, AgentNode
from domain_admin.model.domain_model import DomainModel
from domain_admin.model.user_model import UserModel
from domain_admin.service import agent_service, token_service
from domain_admin.utils.cert_util import cert_openssl_v2, cert_socket_v2
from werkzeug.serving import make_server

ORIGIN = 'https://control.example.test'
DOMAIN = 'regional.example.test'


@pytest.fixture
def web_tokens(tmp_path):
    tokens = []
    for role in (RoleEnum.ADMIN, RoleEnum.USER):
        user = UserModel.create(username=f'{tmp_path.name}-{role}', password='', role=role)
        with app.app_context():
            tokens.append(token_service.encode_token({'user_id': user.id}))
    return tokens


@pytest.fixture
def domain(web_tokens):
    with app.app_context():
        owner = token_service.decode_token(web_tokens[0])['user_id']
    row = DomainModel.create(domain=DOMAIN, user_id=owner, auto_update=False)
    yield row
    row.delete_instance()


def post(client, path, payload=None, *, user=None, credential=None):
    headers = {}
    if user:
        headers['X-Token'] = user
    if credential:
        headers['Authorization'] = f'Bearer {credential}'
    return client.post('/api/' + path, json=payload if payload is not None else {}, headers=headers).json


def create_node(client, admin, region, origin=ORIGIN):
    response = client.post(
        '/api/createAgent', json={'name': f'节点-{region}', 'region': region, 'origin': origin},
        headers={'X-Token': admin},
    )
    assert response.headers['Cache-Control'] == 'no-store'
    assert response.json['code'] == 0
    data = response.json['data']
    assert data['agent']['status'] == 'pending'
    assert data['enrollment_code'] not in data['install_command']
    assert f'{origin}/api/getAgentRunner' in data['install_command']
    assert data['install_command'].endswith(f"--agent-id {data['agent']['id']} --enroll")
    return data


def test_enrollment_permissions_rotation_and_revocation(client, web_tokens, domain, monkeypatch):
    admin, user = web_tokens
    payload = {'name': 'node', 'region': 'East', 'origin': ORIGIN}
    assert post(client, 'createAgent', payload)['code'] == 401
    assert post(client, 'createAgent', payload, user=user)['code'] != 0
    assert post(client, 'createAgent', {**payload, 'origin': 'http://control.example.test'}, user=admin)['code'] == 400

    east = create_node(client, admin, 'East')
    west = create_node(client, admin, 'West')
    east_id, west_id = east['agent']['id'], west['agent']['id']
    east_code = east['enrollment_code']
    original_time = agent_service.now_utc()
    monkeypatch.setattr(agent_service, 'now_utc', lambda: original_time + timedelta(minutes=15))
    assert post(client, 'enrollAgent', {'agent_id': west_id}, credential=west['enrollment_code'])['code'] == 401
    monkeypatch.setattr(agent_service, 'now_utc', lambda: original_time)

    assert post(client, 'pollAgentTask', {'agent_id': east_id}, credential=east_code)['code'] == 401
    assert post(client, 'enrollAgent', {'agent_id': west_id}, credential=east_code)['code'] == 401
    enrollment = post(client, 'enrollAgent', {'agent_id': east_id}, credential=east_code)
    assert enrollment['code'] == 0
    token = enrollment['data']['agent_token']
    assert AgentNode.get_by_id(east_id).credential_hash != token
    assert post(client, 'enrollAgent', {'agent_id': east_id}, credential=east_code)['code'] == 401
    assert post(client, 'getAgentList', credential=token)['code'] == 401
    assert post(client, 'getAgentList', user=token)['code'] != 0
    assert post(client, 'pollAgentTask', {'agent_id': west_id}, credential=token)['code'] == 401
    assert post(client, 'startAgentDomainCheck', {'domain_id': domain.id, 'agent_ids': [west_id]}, user=admin)['code'] == 400

    with app.app_context():
        other_user_id = token_service.decode_token(user)['user_id']
    other_domain = DomainModel.create(domain='other.example.test', user_id=other_user_id, auto_update=False)
    assert post(
        client, 'startAgentDomainCheck', {'domain_id': other_domain.id, 'agent_ids': [east_id]}, user=admin,
    )['code'] == 403
    assert post(client, 'getAgentCheckResults', {'domain_id': other_domain.id}, user=admin)['code'] == 403

    batch = post(client, 'startAgentDomainCheck', {'domain_id': domain.id, 'agent_ids': [east_id]}, user=admin)['data']
    renewed = post(client, 'renewAgentEnrollment', {'agent_id': east_id, 'origin': ORIGIN}, user=admin)['data']
    assert renewed['agent']['status'] == 'pending'
    assert post(client, 'pollAgentTask', {'agent_id': east_id}, credential=token)['code'] == 401
    results = post(client, 'getAgentCheckResults', {'domain_id': domain.id, 'batch_id': batch['batch_id']}, user=admin)
    assert [item['status'] for item in results['data']] == ['canceled']
    new_token = post(client, 'enrollAgent', {'agent_id': east_id}, credential=renewed['enrollment_code'])['data']['agent_token']
    assert post(client, 'revokeAgent', {'agent_id': east_id}, user=admin)['data']['status'] == 'revoked'
    assert post(client, 'pollAgentTask', {'agent_id': east_id}, credential=new_token)['code'] == 401


def write_cert(directory, host, not_after):
    directory.mkdir()
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, host)])
    host_san = x509.IPAddress(ipaddress.ip_address(host)) if host == '127.0.0.1' else x509.DNSName(host)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime(2020, 1, 1))
        .not_valid_after(not_after)
        .add_extension(x509.SubjectAlternativeName([host_san]), critical=False)
        .sign(private_key, hashes.SHA256())
    )
    cert_path, key_path = directory / 'cert.pem', directory / 'private.pem'
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(private_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption(),
    ))
    return cert_path, key_path


@contextmanager
def serve(server):
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


@contextmanager
def certificate_endpoint(cert_chain):
    server = HTTPServer(('127.0.0.1', 0), SimpleHTTPRequestHandler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(*map(str, cert_chain))
    server.socket = context.wrap_socket(server.socket, server_side=True)
    with serve(server) as port:
        yield port


def test_two_regions_heartbeat_and_old_refresh_path(client, web_tokens, domain, tmp_path, monkeypatch):
    admin, _ = web_tokens
    controller_cert, controller_key = write_cert(tmp_path / 'controller', '127.0.0.1', datetime(2040, 1, 1))
    east_cert = write_cert(tmp_path / 'east', DOMAIN, datetime(2037, 1, 1))
    west_cert = write_cert(tmp_path / 'west', DOMAIN, datetime(2038, 1, 1))
    monkeypatch.setenv('SSL_CERT_FILE', str(controller_cert))
    monkeypatch.setenv('NO_PROXY', '127.0.0.1')

    moment = agent_service.now_utc()
    monkeypatch.setattr(agent_service, 'now_utc', lambda: moment)
    controller = make_server('127.0.0.1', 0, app, ssl_context=(str(controller_cert), str(controller_key)))
    with ExitStack() as stack:
        controller_port = stack.enter_context(serve(controller))
        east_port = stack.enter_context(certificate_endpoint(east_cert))
        west_port = stack.enter_context(certificate_endpoint(west_cert))
        origin = f'https://127.0.0.1:{controller_port}'
        agents = {}
        for region in ('East', 'West'):
            enrollment = create_node(client, admin, region, origin)
            agent = agent_runner.ControlClient(origin, enrollment['agent']['id'])
            runtime_token = agent.request('enrollAgent', enrollment['enrollment_code'])['agent_token']
            agents[region] = agent, runtime_token

        runner_response = client.get('/api/getAgentRunner')
        assert runner_response.headers['Content-Disposition'] == 'attachment; filename=agent.py'
        compile(runner_response.data, 'agent.py', 'exec')
        moment += timedelta(seconds=60)
        selected_ids = [agent.agent_id for agent, _ in agents.values()]
        node_states = {node['id']: node['status'] for node in post(client, 'getAgentList', user=admin)['data']}
        assert all(node_states[agent_id] == 'offline' for agent_id in selected_ids)
        batch = post(client, 'startAgentDomainCheck', {'domain_id': domain.id, 'agent_ids': selected_ids}, user=admin)['data']
        assert [result['status'] for result in batch['results']] == ['queued', 'queued']
        assert post(
            client, 'startAgentDomainCheck', {'domain_id': 2147483647, 'agent_ids': selected_ids}, user=admin,
        )['code'] != 0

        real_getaddrinfo = socket.getaddrinfo

        def run_agent(region, target_port):
            agent, token = agents[region]

            def region_dns(host, port, *args, **kwargs):
                if host == DOMAIN:
                    assert port == domain.port
                    return real_getaddrinfo('127.0.0.1', target_port, *args, **kwargs)
                return real_getaddrinfo(host, port, *args, **kwargs)

            monkeypatch.setattr(socket, 'getaddrinfo', region_dns)
            task = agent.request('pollAgentTask', token)['task']
            assert task['type'] == 'domain_tls'
            assert task['domain'] == DOMAIN
            assert task['protocol'] == 'tls'
            remote_result = agent_runner.execute_check(task)
            receipt = agent.request('submitAgentTaskResult', token, task_id=task['id'], **remote_result)
            assert receipt['region'] == region
            assert receipt['status'] == 'succeeded'
            assert agent.request('pollAgentTask', token)['task'] is None
            return task['id']

        east_task = run_agent('East', east_port)
        west, west_token = agents['West']
        assert post(
            client, 'submitAgentTaskResult', {'agent_id': west.agent_id, 'task_id': east_task, 'error': 'probe_failed'},
            credential=west_token,
        )['code'] == 409
        run_agent('West', west_port)
        east, east_token = agents['East']
        retry = east.request('submitAgentTaskResult', east_token, task_id=east_task, error='probe_failed')
        assert retry['status'] == 'succeeded'

        result = post(client, 'getAgentCheckResults', {'domain_id': domain.id, 'batch_id': batch['batch_id']}, user=admin)
        assert {item['region']: item['cert_expires_at'] for item in result['data']} == {
            'East': '2037-01-01T00:00:00Z', 'West': '2038-01-01T00:00:00Z',
        }
        node_states = {node['id']: node['status'] for node in post(client, 'getAgentList', user=admin)['data']}
        assert all(node_states[agent_id] == 'online' for agent_id in selected_ids)

    assert DomainModel.get_by_id(domain.id).expire_time is None
    monkeypatch.setattr(cert_socket_v2, 'get_domain_host_list', lambda **kwargs: ['192.0.2.10'])
    central_expiry = datetime(2039, 1, 1)
    monkeypatch.setattr(
        cert_openssl_v2, 'get_ssl_cert_by_openssl',
        lambda **kwargs: {'start_date': datetime(2020, 1, 1), 'expire_date': central_expiry},
    )
    assert post(client, 'updateDomainRowInfoById', {'id': domain.id}, user=admin)['code'] == 0
    assert DomainModel.get_by_id(domain.id).expire_time == central_expiry
    DomainModel.update(auto_update=True).where(DomainModel.id == domain.id).execute()
    central_expiry = datetime(2040, 1, 1)
    assert post(client, 'updateAllDomainCertInfo', user=admin)['code'] == 0
    assert DomainModel.get_by_id(domain.id).expire_time == central_expiry
    assert AgentCheck.select().where(AgentCheck.batch_id == batch['batch_id']).count() == 2


def test_expired_changed_and_failed_tasks(client, web_tokens, domain, monkeypatch):
    admin, _ = web_tokens
    moment = agent_service.now_utc()
    monkeypatch.setattr(agent_service, 'now_utc', lambda: moment)
    node = create_node(client, admin, 'East')
    agent_id = node['agent']['id']
    token = post(client, 'enrollAgent', {'agent_id': agent_id}, credential=node['enrollment_code'])['data']['agent_token']

    def dispatch():
        request_body = {'domain_id': domain.id, 'agent_ids': [agent_id]}
        return post(client, 'startAgentDomainCheck', request_body, user=admin)['data']['results'][0]

    def poll():
        return post(client, 'pollAgentTask', {'agent_id': agent_id}, credential=token)['data']['task']

    expired = dispatch()
    assert poll()['id'] == expired['id']
    moment += timedelta(minutes=5)
    payload = {'agent_id': agent_id, 'task_id': expired['id'], 'error': 'probe_failed'}
    assert post(client, 'submitAgentTaskResult', payload, credential=token)['code'] == 409

    changed = dispatch()
    DomainModel.update(port=8443).where(DomainModel.id == domain.id).execute()
    assert poll() is None
    failed = dispatch()
    assert poll()['port'] == 8443
    assert post(client, 'submitAgentTaskResult', {
        'agent_id': agent_id, 'task_id': failed['id'], 'error': 'probe_failed',
    }, credential=token)['data']['status'] == 'failed'
    response = post(client, 'getAgentCheckResults', {'domain_id': domain.id}, user=admin)
    assert {item['id']: item['status'] for item in response['data']} == {
        expired['id']: 'expired', changed['id']: 'canceled', failed['id']: 'failed',
    }


@pytest.mark.parametrize('protocol', ['smtp_starttls', 'ftps'])
def test_agent_collects_upgrade_protocol_certificates(protocol, tmp_path):
    cert, key = write_cert(tmp_path / protocol, '127.0.0.1', datetime(2040, 1, 1))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(cert), str(key))

    class UpgradeHandler(StreamRequestHandler):
        def handle(self):
            self.wfile.write(b'220 probe fixture ready\r\n')
            if protocol == 'smtp_starttls':
                assert self.rfile.readline().startswith(b'ehlo ')
                self.wfile.write(b'250-probe fixture\r\n250 STARTTLS\r\n')
                assert self.rfile.readline() == b'STARTTLS\r\n'
                self.wfile.write(b'220 Ready for TLS\r\n')
            else:
                assert self.rfile.readline() == b'AUTH TLS\r\n'
                self.wfile.write(b'234 Ready for TLS\r\n')
            with context.wrap_socket(self.request, server_side=True):
                pass

    with serve(TCPServer(('127.0.0.1', 0), UpgradeHandler)) as port:
        result = agent_runner.execute_check({
            'type': 'domain_tls', 'domain': '127.0.0.1', 'port': port, 'protocol': protocol,
        })
    assert list(result) == ['certificate_der']

# -*- coding: utf-8 -*-
"""独立区域探针。此文件可直接在节点运行，只依赖 Python 标准库。"""

import argparse
import base64
import ftplib
import getpass
import ipaddress
import json
import os
import re
import smtplib
import socket
import ssl
import sys
import tempfile
import time
from contextlib import closing
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

POLL_INTERVAL_SECONDS = 10
SOCKET_TIMEOUT = 5
API_TIMEOUT = 15
PROTOCOLS = {'tls', 'smtp_starttls', 'ftps'}
HOST_LABEL = re.compile(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', re.ASCII)
SECRET_PATTERN = re.compile(r'[A-Za-z0-9_-]{43}', re.ASCII)


class AgentAPIError(Exception):
    def __init__(self, code: int):
        self.code = code
        super().__init__(f'控制端业务码 {code}')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # 重定向目标不应收到原请求中的 Agent 凭据。
        return None


def normalize_target(domain: str, port: int) -> str:
    if not isinstance(domain, str) or type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('无效的检查目标')
    try:
        return ipaddress.ip_address(domain).compressed
    except ValueError:
        pass

    try:
        hostname = domain.encode('idna').decode('ascii').lower()
        if hostname.endswith('.'):
            hostname = hostname[:-1]
    except UnicodeError:
        raise ValueError('无效的主机名') from None
    if len(hostname) > 253 or not all(HOST_LABEL.fullmatch(label) for label in hostname.split('.')):
        raise ValueError('无效的主机名')
    return hostname


def normalize_origin(origin: str) -> str:
    if not isinstance(origin, str) or any(char.isspace() for char in origin):
        raise ValueError('需要 HTTPS 控制端地址')
    parts = urlsplit(origin)
    if (
        parts.scheme != 'https' or not parts.hostname or parts.username is not None
        or parts.path or '?' in origin or '#' in origin
    ):
        raise ValueError('需要 HTTPS 控制端 origin')
    port = parts.port
    hostname = normalize_target(parts.hostname, 443 if port is None else port)
    if ':' in hostname:
        hostname = f'[{hostname}]'
    return 'https://{}{}'.format(hostname, f':{port}' if port is not None else '')


def _read_certificate(domain: str, port: int, protocol: str) -> bytes:
    # 采集证书有效期时也需要读取已过期证书。控制端 HTTPS 使用独立的默认信任配置。
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    if protocol == 'smtp_starttls':
        with closing(smtplib.SMTP(domain, port, timeout=SOCKET_TIMEOUT)) as server:
            server.starttls(context=context)
            return server.sock.getpeercert(binary_form=True)
    if protocol == 'ftps':
        with closing(ftplib.FTP_TLS(context=context, timeout=SOCKET_TIMEOUT)) as server:
            server.connect(domain, port)
            server.auth()
            return server.sock.getpeercert(binary_form=True)
    with socket.create_connection((domain, port), timeout=SOCKET_TIMEOUT) as sock, context.wrap_socket(
        sock, server_hostname=domain,
    ) as tls_socket:
        return tls_socket.getpeercert(binary_form=True)


def execute_check(task: dict) -> dict:
    if task.get('type') != 'domain_tls' or task.get('protocol') not in PROTOCOLS:
        return {'error': 'probe_failed'}
    try:
        domain = normalize_target(task['domain'], task['port'])
        certificate = _read_certificate(domain, task['port'], task['protocol'])
        if certificate:
            encoded = base64.b64encode(certificate).decode('ascii')
            if len(encoded) <= 96 * 1024:
                return {'certificate_der': encoded}
    except (OSError, ValueError, ftplib.Error, EOFError):
        pass
    return {'error': 'probe_failed'}


class ControlClient:
    def __init__(self, origin: str, agent_id: int):
        self.origin = normalize_origin(origin)
        self.agent_id = agent_id
        self.opener = build_opener(NoRedirect())

    def request(self, endpoint: str, token: str, **payload) -> dict:
        body = json.dumps({'agent_id': self.agent_id, **payload}).encode('utf-8')
        req = Request(
            self.origin + '/api/' + endpoint,
            data=body,
            headers={
                'Authorization': 'Bearer ' + token,
                'Content-Type': 'application/json',
            },
        )
        with self.opener.open(req, timeout=API_TIMEOUT) as response:
            result = json.loads(response.read(128 * 1024))
        if result['code'] != 0:
            raise AgentAPIError(result['code'])
        return result['data']


def _save_credentials(path: Path, origin: str, agent_id: int, token: str) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=str(path.parent), delete=False) as file:
        temporary_path = Path(file.name)
        try:
            json.dump({'origin': origin, 'agent_id': agent_id, 'token': token}, file)
            file.flush()
            os.fsync(file.fileno())
            os.replace(str(temporary_path), str(path))
        finally:
            if temporary_path.exists():
                temporary_path.unlink()


def _load_credentials(path: Path, client: ControlClient) -> str:
    saved = json.loads(path.read_text(encoding='utf-8'))
    if saved['origin'] != client.origin or saved['agent_id'] != client.agent_id:
        raise ValueError('本地凭据与控制端或 Agent ID 不匹配')
    token = saved['token']
    if not isinstance(token, str) or not SECRET_PATTERN.fullmatch(token):
        raise ValueError('本地凭据格式无效')
    return token


def run(client: ControlClient, token: str) -> None:
    result = None
    interval = POLL_INTERVAL_SECONDS
    while True:
        try:
            if result is None:
                response = client.request('pollAgentTask', token)
                interval = response['poll_interval_seconds']
                task = response['task']
                if task is not None:
                    result = {'task_id': task['id'], **execute_check(task)}
            if result is not None:
                client.request('submitAgentTaskResult', token, **result)
                result = None
        except AgentAPIError as error:
            if error.code == 401:
                raise
            if error.code in (400, 409, 413):
                result = None
            print(str(error), file=sys.stderr)
        except (URLError, OSError, ValueError, KeyError):
            print('暂时无法与控制端通信，稍后重试', file=sys.stderr)
        time.sleep(interval)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server', required=True, help='控制端 HTTPS origin')
    parser.add_argument('--agent-id', required=True, type=int)
    parser.add_argument('--enroll', action='store_true', help='用一次性安装码登记')
    args = parser.parse_args()
    path = Path(__file__).resolve().with_name('credentials.json')
    try:
        client = ControlClient(args.server, args.agent_id)
        if args.enroll:
            code = getpass.getpass('Agent 安装码：').strip()
            if not SECRET_PATTERN.fullmatch(code):
                raise ValueError('安装码格式无效')
            token = client.request('enrollAgent', code)['agent_token']
            _save_credentials(path, client.origin, client.agent_id, token)
        else:
            token = _load_credentials(path, client)
        print(f'Agent {client.agent_id} 已启动', flush=True)
        run(client, token)
    except AgentAPIError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (URLError, OSError, ValueError, KeyError):
        print('启动失败，请检查控制端地址、网络及本地凭据', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == '__main__':
    sys.exit(main())

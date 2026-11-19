import json
import sys
from contextlib import redirect_stdout

from domain_admin.utils import domain_util
from domain_admin.utils.cert_util import cert_ftp, cert_openssl_v2, cert_socket_v2


def fetch_address_cert(domain, port, ssl_type, host):
    if port == 21:
        return cert_ftp.get_ftp_cert_by_ftplib(domain=domain, host=host, port=port)
    return cert_openssl_v2.get_ssl_cert_by_openssl(
        domain=domain, host=host, port=port, ssl_type=ssl_type,
    )


def probe(domain, port, ssl_type, manual_hosts, root_domain):
    try:
        resolved_hosts = cert_socket_v2.get_domain_host_list(domain, port)
    except OSError:
        resolved_hosts = []

    certificates = {}
    for host in dict.fromkeys(manual_hosts + resolved_hosts):
        for _ in range(3):
            try:
                cert = fetch_address_cert(domain, port, ssl_type, host)
                certificates[host] = {key: value.isoformat() for key, value in cert.items()}
                break
            except Exception:
                certificates[host] = None

    return {
        'root_domain': root_domain or domain_util.get_root_domain(domain),
        'resolved_hosts': resolved_hosts,
        'certificates': certificates,
    }


if __name__ == '__main__':
    payload = json.load(sys.stdin)
    with redirect_stdout(sys.stderr):
        result = probe(**payload)
    json.dump(result, sys.stdout)

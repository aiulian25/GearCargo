"""GC-104: forwarded headers are believed only from a peer that
TRUSTED_PROXY_COUNT trusts as a proxy.

Public peers here are real global addresses: ipaddress counts the TEST-NET
documentation ranges and the 198.18.0.0/15 benchmarking range as non-public.
"""
import pytest
from flask import Flask, request
from werkzeug.test import Client
from werkzeug.wrappers import Response

from app.routes.auth import get_real_client_ip
from app.services.proxy_trust import (
    AUTOMATIC_PROXY_TRUST,
    IGNORED_FORWARDED_FOR_WARNING,
    UNPROXIED_PUBLIC_PEER_WARNING,
    ProxyTrustMiddleware,
    install_proxy_trust,
    is_non_public_address,
    parse_trusted_proxy_count,
)

SPOOFED = '1.1.1.1'
CLIENT = '9.9.9.9'           # appended by the proxy: the rightmost entry
FORWARDED_FOR = f'{SPOOFED}, {CLIENT}'
PUBLIC_PEER = '8.8.8.8'
DOCKER_PROXY = '172.18.0.2'
LOOPBACK = '127.0.0.1'


def request_through_app(setting, peer, path='/client-ip', headers=None):
    app = Flask(__name__)
    app.config['TRUSTED_PROXY_COUNT'] = setting
    app.add_url_rule('/client-ip', view_func=get_real_client_ip)
    app.add_url_rule('/url-root', endpoint='url_root', view_func=lambda: request.url_root)
    install_proxy_trust(app)
    response = app.test_client().get(path, headers=headers or {}, environ_base={'REMOTE_ADDR': peer})
    return response.get_data(as_text=True)


class RecordingLogger:
    def __init__(self):
        self.warnings = []

    def warning(self, message, *arguments):
        self.warnings.append(message)


def empty_wsgi_app(environ, start_response):
    return Response()(environ, start_response)


def warnings_for(setting, connections):
    logger = RecordingLogger()
    client = Client(ProxyTrustMiddleware(empty_wsgi_app, parse_trusted_proxy_count(setting), logger))
    for peer, forwarded_for in connections:
        headers = {'X-Forwarded-For': forwarded_for} if forwarded_for else {}
        client.get('/', headers=headers, environ_base={'REMOTE_ADDR': peer})
    return logger.warnings


@pytest.mark.parametrize('peer', [
    LOOPBACK, '::1', '10.0.0.5', DOCKER_PROXY, '192.168.1.20', 'fd00::5',
    '100.100.1.1',  # a Tailscale/CGNAT proxy
])
def test_auto_trusts_one_hop_from_a_non_public_peer(peer):
    headers = {'X-Forwarded-For': FORWARDED_FOR}
    assert request_through_app(AUTOMATIC_PROXY_TRUST, peer, headers=headers) == CLIENT


@pytest.mark.parametrize('peer', [PUBLIC_PEER, '2001:4860:4860::8888', f'::ffff:{PUBLIC_PEER}'])
def test_auto_ignores_forwarded_for_from_a_public_peer(peer):
    headers = {'X-Forwarded-For': FORWARDED_FOR}
    assert request_through_app(AUTOMATIC_PROXY_TRUST, peer, headers=headers) == peer


@pytest.mark.parametrize('peer', [None, '', '/run/gunicorn.sock'])
def test_an_empty_or_unreadable_peer_is_never_a_proxy(peer):
    assert not is_non_public_address(peer)


def test_auto_lets_a_public_peer_set_neither_scheme_host_nor_prefix():
    headers = {'X-Forwarded-Proto': 'https', 'X-Forwarded-Host': 'cars.example', 'X-Forwarded-Prefix': '/cars'}
    assert request_through_app(AUTOMATIC_PROXY_TRUST, PUBLIC_PEER, '/url-root', headers) == 'http://localhost/'
    assert request_through_app(AUTOMATIC_PROXY_TRUST, DOCKER_PROXY, '/url-root', headers) == 'https://cars.example/cars/'


def test_zero_never_lets_the_header_choose_the_client_address():
    headers = {'X-Forwarded-For': FORWARDED_FOR}
    assert request_through_app('0', DOCKER_PROXY, headers=headers) == DOCKER_PROXY


@pytest.mark.parametrize('setting, forwarded_for', [('1', FORWARDED_FOR), ('2', f'{FORWARDED_FOR}, 10.0.0.7')])
def test_an_explicit_count_keeps_its_meaning_for_every_peer(setting, forwarded_for):
    headers = {'X-Forwarded-For': forwarded_for}
    assert request_through_app(setting, PUBLIC_PEER, headers=headers) == CLIENT


def test_an_ignored_forwarded_for_warns_once():
    assert warnings_for('0', [(DOCKER_PROXY, FORWARDED_FOR)] * 2) == [IGNORED_FORWARDED_FOR_WARNING]
    assert warnings_for(AUTOMATIC_PROXY_TRUST, [(PUBLIC_PEER, FORWARDED_FOR)] * 2) == [IGNORED_FORWARDED_FOR_WARNING]


def test_a_trusted_count_reached_directly_from_a_public_peer_warns_once():
    assert warnings_for('1', [(PUBLIC_PEER, None)] * 2) == [UNPROXIED_PUBLIC_PEER_WARNING]


@pytest.mark.parametrize('setting, peer, forwarded_for', [
    (AUTOMATIC_PROXY_TRUST, DOCKER_PROXY, FORWARDED_FOR),
    (AUTOMATIC_PROXY_TRUST, PUBLIC_PEER, None),
    ('0', PUBLIC_PEER, None),
    ('1', DOCKER_PROXY, FORWARDED_FOR),
    ('1', PUBLIC_PEER, FORWARDED_FOR),  # a CDN
    ('1', LOOPBACK, None),  # a request from inside the container
])
def test_a_consistent_topology_logs_nothing(setting, peer, forwarded_for):
    assert warnings_for(setting, [(peer, forwarded_for)]) == []


@pytest.mark.parametrize('configured, expected', [
    ('auto', AUTOMATIC_PROXY_TRUST),
    (' AUTO ', AUTOMATIC_PROXY_TRUST),
    ('', AUTOMATIC_PROXY_TRUST),  # a blank TRUSTED_PROXY_COUNT= in .env
    ('0', 0),
    ('2', 2),
    (1, 1),
])
def test_the_setting_is_auto_or_a_whole_number(configured, expected):
    assert parse_trusted_proxy_count(configured) == expected


@pytest.mark.parametrize('configured', ['-1', 'one', '1.5', 'true'])
def test_an_unreadable_setting_stops_startup(configured):
    app = Flask(__name__)
    app.config['TRUSTED_PROXY_COUNT'] = configured
    with pytest.raises(ValueError, match='TRUSTED_PROXY_COUNT'):
        install_proxy_trust(app)


def test_health_probes_are_answered_before_proxy_trust(app, caplog):
    spoofed = {'headers': {'X-Forwarded-For': SPOOFED}, 'environ_base': {'REMOTE_ADDR': PUBLIC_PEER}}
    client = app.test_client()

    client.get('/health/live', **spoofed)
    assert IGNORED_FORWARDED_FOR_WARNING not in [record.msg for record in caplog.records]

    # Positive control: the same request to any other path is checked.
    client.get('/api/config', **spoofed)
    assert IGNORED_FORWARDED_FOR_WARNING in [record.msg for record in caplog.records]

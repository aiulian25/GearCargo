"""SSRF hardening tests for WebDAV backup destinations (SEC-01 / SEC-02).

Covers the DNS-rebinding front-door check in ``_is_allowed_webdav_url`` and the
connection-pinning + no-redirect behaviour of ``_safe_webdav_request``. Network
resolution (``socket.getaddrinfo``) is monkeypatched so the tests are fast and
offline; no real outbound request is made.
"""

import socket

import pytest
import requests

import app.routes.backup as bk


def _fake_getaddrinfo(mapping):
    """Return a getaddrinfo stub that maps host -> list of IPs (or raises)."""
    def _stub(host, port, *a, **k):
        if host not in mapping:
            raise socket.gaierror('name resolution failed')
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', (ip, port))
                for ip in mapping[host]]
    return _stub


# --------------------------------------------------------------------------
# _ip_is_internal
# --------------------------------------------------------------------------

@pytest.mark.parametrize('ip', [
    '127.0.0.1', '10.0.0.5', '192.168.1.10', '172.16.0.1',
    '169.254.169.254',            # cloud metadata (link-local)
    '::1', 'fe80::1', '0.0.0.0', 'not-an-ip',
])
def test_internal_ips_flagged(ip):
    assert bk._ip_is_internal(ip) is True


@pytest.mark.parametrize('ip', ['8.8.8.8', '1.1.1.1', '2606:4700:4700::1111'])
def test_public_ips_allowed(ip):
    assert bk._ip_is_internal(ip) is False


# --------------------------------------------------------------------------
# _is_allowed_webdav_url — cheap, NETWORK-FREE config-time validation (S09).
# It must NOT do DNS (saving settings can't block on the network); the
# authoritative resolve+validate+pin is in _safe_webdav_request (below).
# --------------------------------------------------------------------------

def test_rejects_non_https():
    assert bk._is_allowed_webdav_url('http://example.com/dav') is False


def test_rejects_internal_ip_literal():
    assert bk._is_allowed_webdav_url('https://169.254.169.254/latest/meta-data') is False
    assert bk._is_allowed_webdav_url('https://10.1.2.3/dav') is False


def test_allows_public_ip_literal():
    assert bk._is_allowed_webdav_url('https://8.8.8.8/dav') is True


def test_hostname_passes_frontdoor_without_dns(monkeypatch):
    # Config-time validation is network-free: a hostname passes the front door
    # (scheme/IP-literal only) and is NOT resolved here. Any getaddrinfo call
    # would be a bug — blow up if it happens.
    def _boom(*a, **k):
        raise AssertionError('config-time validation must not resolve DNS')
    monkeypatch.setattr(bk.socket, 'getaddrinfo', _boom)
    assert bk._is_allowed_webdav_url('https://backup.example.com/webdav') is True


def test_empty_and_hostless_rejected():
    assert bk._is_allowed_webdav_url('') is False
    assert bk._is_allowed_webdav_url('https:///dav') is False


# --------------------------------------------------------------------------
# _safe_webdav_request — connection guard (SEC-01/02)
# --------------------------------------------------------------------------

def test_safe_request_refuses_internal_ip_literal():
    with pytest.raises(requests.exceptions.ConnectionError):
        bk._safe_webdav_request('GET', 'https://127.0.0.1/dav', timeout=5)


def test_safe_request_refuses_non_https():
    with pytest.raises(requests.exceptions.ConnectionError):
        bk._safe_webdav_request('GET', 'http://example.com/dav', timeout=5)


def test_safe_request_refuses_rebind_host(monkeypatch):
    monkeypatch.setattr(bk.socket, 'getaddrinfo',
                        _fake_getaddrinfo({'rebind.attacker.com': ['169.254.169.254']}))
    with pytest.raises(requests.exceptions.ConnectionError):
        bk._safe_webdav_request('GET', 'https://rebind.attacker.com/dav', timeout=5)


def test_safe_request_pins_ip_and_forbids_redirects(monkeypatch):
    """A public host is pinned to its validated IP, the real Host header is set,
    and allow_redirects is forced False."""
    monkeypatch.setattr(bk.socket, 'getaddrinfo',
                        _fake_getaddrinfo({'good.example.com': ['93.184.216.34']}))

    captured = {}

    class _FakeSession:
        def mount(self, prefix, adapter):
            captured['adapter_host'] = adapter._pinned_hostname

        def request(self, method, url, **kwargs):
            captured['method'] = method
            captured['url'] = url
            captured['headers'] = kwargs.get('headers')
            captured['allow_redirects'] = kwargs.get('allow_redirects')

            class _Resp:
                status_code = 200
            return _Resp()

        def close(self):
            captured['closed'] = True

    monkeypatch.setattr(bk.requests, 'Session', lambda: _FakeSession())

    resp = bk._safe_webdav_request('PUT', 'https://good.example.com/dav/file',
                                   data=b'x', timeout=5)
    assert resp.status_code == 200
    assert captured['method'] == 'PUT'
    # URL is rewritten to the validated IP; Host header preserves the real name.
    assert '93.184.216.34' in captured['url']
    assert 'good.example.com' not in captured['url']
    assert captured['headers']['Host'] == 'good.example.com'
    assert captured['allow_redirects'] is False
    assert captured['adapter_host'] == 'good.example.com'
    assert captured['closed'] is True

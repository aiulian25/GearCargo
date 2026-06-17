"""Tests for the backend→Ollama transport hardening (CHAT_HARDENING_PLAN §14).

Covers `_ollama_post`: (connect, read) timeout tuple, ONE retry on connect-level
errors, NO retry on read timeouts, breaker tripping only on connect failure, and
the keep-alive Session (§14.5). `app.services.ollama` imports cleanly (stdlib +
requests), so this runs without the full app.

§14.8 distributed test matrix coverage:
  - Connection refused / unreachable / bad DNS → connect-timeout fast-fail + 1
    retry + breaker trip:        test_connect_error_retries_once_then_trips_breaker
  - Remote slow (read timeout) → no retry, no breaker trip:
                                 test_read_timeout_no_retry_no_breaker
  - Network blip → retry recovers cleanly:  test_network_blip_retry_recovers
  - TLS misconfig (bad cert) → clear bounded error: test_tls_misconfig_clear_bounded_error
  - (connect, read) tuple actually applied:  test_uses_connect_read_timeout_tuple
  - Endpoint-level: breaker fast-fail / main down / classifier missing+fail-open
    are in test_chat_endpoint.py + test_chat_classifier.py.
  - Worker-pool probe (N>workers concurrent slow chats; non-AI routes still
    respond) is a LOAD/integration test (needs a running gunicorn + concurrency
    harness), not unit-automatable here — run manually; the defence pieces
    (connect timeout, breaker fast-fail, per-user rate limit) are unit-covered.
"""

import pytest
import requests

import app.services.ollama as o


class _FakeResp:
    status_code = 200


class _FakeSession:
    def __init__(self, post_fn):
        self.post = post_fn


def _patch(monkeypatch, post_fn):
    """Route _ollama_post through a fake keep-alive session + count breaker trips."""
    calls = {'fail': 0}
    monkeypatch.setattr(o, 'ollama_record_failure', lambda: calls.__setitem__('fail', calls['fail'] + 1))
    monkeypatch.setattr(o, '_get_session', lambda: _FakeSession(post_fn))
    return calls


def test_success_returns_response(monkeypatch):
    posts = {'n': 0}

    def _post(*a, **k):
        posts['n'] += 1
        return _FakeResp()
    calls = _patch(monkeypatch, _post)
    resp = o._ollama_post('http://x/api/chat', {}, 5, 30)
    assert resp.status_code == 200
    assert posts['n'] == 1 and calls['fail'] == 0


def test_connect_error_retries_once_then_trips_breaker(monkeypatch):
    posts = {'n': 0}

    def _post(*a, **k):
        posts['n'] += 1
        raise requests.ConnectionError('refused')
    calls = _patch(monkeypatch, _post)
    with pytest.raises(o.OllamaError):
        o._ollama_post('http://x/api/chat', {}, 5, 30)
    assert posts['n'] == 2   # one retry
    assert calls['fail'] == 1  # breaker tripped once


def test_read_timeout_no_retry_no_breaker(monkeypatch):
    posts = {'n': 0}

    def _post(*a, **k):
        posts['n'] += 1
        raise requests.exceptions.ReadTimeout('slow model')
    calls = _patch(monkeypatch, _post)
    with pytest.raises(o.OllamaError):
        o._ollama_post('http://x/api/generate', {}, 5, 30)
    assert posts['n'] == 1   # NOT retried
    assert calls['fail'] == 0  # breaker NOT tripped (remote up, just slow)


def test_uses_connect_read_timeout_tuple(monkeypatch):
    seen = {}

    def _post(*a, **k):
        seen.update(k)
        return _FakeResp()
    _patch(monkeypatch, _post)
    o._ollama_post('http://x/api/chat', {}, 5, 42)
    assert seen.get('timeout') == (5, 42)


def test_network_blip_retry_recovers(monkeypatch):
    # §14.8 "Network blip" → the single connect retry recovers cleanly.
    attempts = {'n': 0}

    def _post(*a, **k):
        attempts['n'] += 1
        if attempts['n'] == 1:
            raise requests.ConnectionError('transient blip')
        return _FakeResp()  # 2nd attempt succeeds
    calls = _patch(monkeypatch, _post)
    resp = o._ollama_post('http://x/api/chat', {}, 5, 30)
    assert resp.status_code == 200
    assert attempts['n'] == 2      # retried once
    assert calls['fail'] == 0      # recovered → breaker NOT tripped


def test_tls_misconfig_clear_bounded_error(monkeypatch):
    # §14.8 "TLS misconfig (https + bad cert)" → clear error, bounded (no hang).
    # requests.exceptions.SSLError subclasses ConnectionError → retried once, then
    # surfaced as OllamaError.
    posts = {'n': 0}

    def _post(*a, **k):
        posts['n'] += 1
        raise requests.exceptions.SSLError('certificate verify failed')
    calls = _patch(monkeypatch, _post)
    with pytest.raises(o.OllamaError):
        o._ollama_post('https://ollama.internal/api/chat', {}, 5, 30)
    assert posts['n'] == 2         # bounded: at most one retry
    assert calls['fail'] == 1      # treated as connect-level → breaker trips


def test_session_is_per_process_and_reused(monkeypatch):
    # Same PID → same Session instance (keep-alive reuse).
    o._session = None
    o._session_pid = None
    s1 = o._get_session()
    s2 = o._get_session()
    assert s1 is s2 and isinstance(s1, requests.Session)
    # Simulate a fork (different PID) → a fresh Session.
    monkeypatch.setattr(o.os, 'getpid', lambda: o._session_pid + 1)
    s3 = o._get_session()
    assert s3 is not s1

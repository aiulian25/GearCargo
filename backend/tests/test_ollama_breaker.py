"""Tests for the half-open Ollama circuit breaker (self-heal follow-up).

Previously the breaker could only be cleared by an UNRELATED successful
Ollama call or the 4 h TTL — chat fast-failed before ever calling Ollama, so
it could never reset itself. Now, after a cooldown since the last failure,
exactly one request is allowed through as a probe.
"""

from datetime import datetime, timedelta, timezone

import pytest

import app.services.ollama as ollama_svc
from app.services.ollama import (
    ollama_breaker_allows_probe,
    ollama_downtime_info,
    ollama_record_failure,
    ollama_record_success,
    _OLLAMA_OFFLINE_KEY,
    _OLLAMA_LAST_FAILURE_KEY,
    _OLLAMA_PROBE_LOCK_KEY,
)


class FakeRedis:
    """Just enough redis for the breaker: get/set(nx,ex)/setnx/expire/delete."""

    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    def setnx(self, key, value):
        if key in self.store:
            return False
        self.store[key] = value
        return True

    def expire(self, key, ttl):
        return key in self.store

    def delete(self, *keys):
        removed = 0
        for key in keys:
            removed += 1 if self.store.pop(key, None) is not None else 0
        return removed


@pytest.fixture
def fake_redis(monkeypatch):
    r = FakeRedis()
    monkeypatch.setattr(ollama_svc, '_get_redis', lambda: r)
    return r


def _age_last_failure(r, seconds):
    """Backdate the last-failure timestamp by *seconds*."""
    r.store[_OLLAMA_LAST_FAILURE_KEY] = (
        datetime.now(timezone.utc) - timedelta(seconds=seconds)
    ).isoformat()


def test_fresh_failure_blocks_probe(fake_redis):
    ollama_record_failure()
    assert ollama_downtime_info()['down'] is True
    assert ollama_breaker_allows_probe() is False      # cooldown not elapsed


def test_cooldown_elapsed_allows_exactly_one_probe(fake_redis):
    ollama_record_failure()
    _age_last_failure(fake_redis, 300)                 # > 120 s cooldown

    assert ollama_breaker_allows_probe() is True       # first claims the slot
    assert ollama_breaker_allows_probe() is False      # everyone else fast-fails
    assert _OLLAMA_PROBE_LOCK_KEY in fake_redis.store


def test_failed_probe_rearms_cooldown_and_frees_slot(fake_redis):
    ollama_record_failure()
    _age_last_failure(fake_redis, 300)
    assert ollama_breaker_allows_probe() is True       # probe goes out…

    ollama_record_failure()                            # …and fails
    assert _OLLAMA_PROBE_LOCK_KEY not in fake_redis.store   # slot freed
    assert ollama_breaker_allows_probe() is False      # fresh cooldown running

    _age_last_failure(fake_redis, 300)
    assert ollama_breaker_allows_probe() is True       # next cycle probes again


def test_successful_probe_clears_all_state(fake_redis):
    ollama_record_failure()
    _age_last_failure(fake_redis, 300)
    assert ollama_breaker_allows_probe() is True

    ollama_record_success()                            # probe succeeded
    assert ollama_downtime_info()['down'] is False
    assert fake_redis.store == {}                      # every breaker key gone


def test_legacy_marker_without_last_failure_allows_probe(fake_redis):
    """State written by the PREVIOUS version (offline_since only) must not
    stay dark: with no last-failure key the cooldown is treated as elapsed."""
    fake_redis.store[_OLLAMA_OFFLINE_KEY] = datetime.now(timezone.utc).isoformat()
    assert ollama_downtime_info()['down'] is True
    assert ollama_breaker_allows_probe() is True


def test_no_redis_never_blocks(monkeypatch):
    monkeypatch.setattr(ollama_svc, '_get_redis', lambda: None)
    assert ollama_breaker_allows_probe() is True       # no state → no breaker


def test_chat_route_fast_fails_closed_and_probes_half_open(
        app, client, user, auth_headers, monkeypatch):
    from datetime import date
    from app import db
    from app.models import Vehicle
    import app.routes.vehicles as v

    with app.app_context():
        veh = Vehicle(user_id=user.id, name='Probe', make='VW', model='Golf')
        db.session.add(veh)
        db.session.commit()
        vid = veh.id

    app.config['OLLAMA_ENABLED'] = True
    app.config['OLLAMA_BASE_URL'] = 'http://localhost:11434'
    called = []
    try:
        monkeypatch.setattr(v, 'resolve_model', lambda *a, **k: 'test-model')
        monkeypatch.setattr(v, 'ai_cache_get', lambda *a, **k: None)
        monkeypatch.setattr(v, 'ai_cache_set', lambda *a, **k: None)
        monkeypatch.setattr(v, 'ollama_downtime_info', lambda: {'down': True})
        monkeypatch.setattr(v, 'ollama_chat',
                            lambda **k: called.append(1) or (_ for _ in ()).throw(
                                v.OllamaError('probe failed')))

        # Breaker closed (no probe slot) → fast-fail, model never touched.
        monkeypatch.setattr(v, 'ollama_breaker_allows_probe', lambda: False)
        resp = client.post(f'/api/vehicles/{vid}/chat', json={'question': 'hi?'},
                           headers=auth_headers(user.id))
        assert resp.status_code == 503
        assert resp.get_json()['code'] == 'ai_unavailable'
        assert called == []

        # Half-open (probe slot claimed) → the request reaches the model
        # (the route makes up to two calls: topic guard + answer).
        monkeypatch.setattr(v, 'ollama_breaker_allows_probe', lambda: True)
        resp = client.post(f'/api/vehicles/{vid}/chat', json={'question': 'hi?'},
                           headers=auth_headers(user.id))
        assert len(called) >= 1
        assert resp.status_code == 503                 # probe failed upstream
    finally:
        app.config['OLLAMA_ENABLED'] = False

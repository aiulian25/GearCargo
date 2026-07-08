"""End-to-end tests for the fleet-wide chat endpoint (F10).

Mirrors test_chat_endpoint.py: Ollama is mocked (no network) — the fake branches
on the JSON schema (classifier vs main). The fleet route must reuse the same
guardrail pipeline as the per-vehicle route.
"""

import pytest

import app.routes.vehicles as v
from app import db
from app.models import Vehicle, User
from app.services.ollama import OllamaError


@pytest.fixture()
def chat_app(app):
    app.config['OLLAMA_ENABLED'] = True
    return app


def _mk_vehicle(user_id, name, make='VW', model='Golf'):
    veh = Vehicle(user_id=user_id, name=name, make=make, model=model,
                  year=2019, fuel_type='diesel', current_mileage=85000)
    db.session.add(veh)
    db.session.commit()
    return veh.id


def _is_classifier(kwargs):
    props = (kwargs.get('schema') or {}).get('properties', {})
    return 'decision' in props


def _install(monkeypatch, *, decision='ALLOW', answer='The Golf costs the most.',
             main_raises=None, capture=None, counters=None):
    monkeypatch.setattr(v, 'resolve_model', lambda *_a, **_k: 'test-model')

    def _chat(**kwargs):
        if _is_classifier(kwargs):
            return {'decision': decision}
        if counters is not None:
            counters['main'] = counters.get('main', 0) + 1
        if capture is not None:
            capture['prompt'] = kwargs.get('prompt')
        if main_raises:
            raise main_raises
        return {'answer': answer}

    monkeypatch.setattr(v, 'ollama_chat', _chat)
    monkeypatch.setattr(v, 'ai_cache_get', lambda *_a, **_k: None)
    monkeypatch.setattr(v, 'ai_cache_set', lambda *_a, **_k: None)


def _ask(client, auth_headers, user_id, question, locale='en-US'):
    return client.post('/api/vehicles/chat',
                       headers=auth_headers(user_id),
                       json={'question': question, 'locale': locale})


def test_ai_disabled_returns_503(app, client, user, auth_headers):
    # AI off → same 503 'ai_disabled' code as the per-vehicle route.
    app.config['OLLAMA_ENABLED'] = False
    with app.app_context():
        _mk_vehicle(user.id, 'Golf')
    r = _ask(client, auth_headers, user.id, 'which car costs most?')
    assert r.status_code == 503
    assert r.get_json().get('code') == 'ai_disabled'


def test_fleet_answer_spans_both_vehicles(chat_app, client, user, auth_headers, monkeypatch):
    with chat_app.app_context():
        _mk_vehicle(user.id, 'Daily', make='Ford', model='Focus')
        _mk_vehicle(user.id, 'Weekend', make='Mazda', model='MX5')
    capture = {}
    _install(monkeypatch, decision='ALLOW',
             answer='Across your cars, the Focus costs the most per km.', capture=capture)

    r = _ask(client, auth_headers, user.id, 'which car costs me most per km?')
    assert r.status_code == 200
    assert r.get_json()['refused'] is False
    # The grounded context spans BOTH vehicles (their names appear in the prompt).
    prompt = capture['prompt']
    assert 'Daily' in prompt and 'Weekend' in prompt
    assert '"vehicles"' in prompt  # fleet context shape


def test_no_vehicles_returns_404(chat_app, client, user, auth_headers, monkeypatch):
    _install(monkeypatch)
    r = _ask(client, auth_headers, user.id, 'total spend across all cars?')
    assert r.status_code == 404
    assert r.get_json().get('code') == 'no_vehicles'


def test_off_topic_block_refuses_like_per_vehicle(chat_app, client, user, auth_headers, monkeypatch):
    with chat_app.app_context():
        _mk_vehicle(user.id, 'Golf')
        _mk_vehicle(user.id, 'Polo')
    counters = {}
    _install(monkeypatch, decision='BLOCK', counters=counters)
    r = _ask(client, auth_headers, user.id, 'give me a pasta recipe')
    assert r.status_code == 200
    data = r.get_json()
    assert data['refused'] is True
    assert data.get('blocked_by') == 'classifier'
    assert data['answer'] == v._CHAT_REFUSAL['English']
    assert counters.get('main', 0) == 0  # expensive model never called


def test_isolation_only_own_vehicles_in_context(chat_app, client, user, auth_headers, monkeypatch):
    with chat_app.app_context():
        _mk_vehicle(user.id, 'MineOne')
        other = User(username='other10', email='other10@example.com', is_active=True)
        other.set_password('StrongPass123!')
        db.session.add(other)
        db.session.commit()
        _mk_vehicle(other.id, 'TheirSecret')
    capture = {}
    _install(monkeypatch, decision='ALLOW', capture=capture)
    r = _ask(client, auth_headers, user.id, 'compare my cars costs')
    assert r.status_code == 200
    prompt = capture['prompt']
    assert 'MineOne' in prompt
    assert 'TheirSecret' not in prompt  # never leak another user's data


def test_main_model_down_returns_503(chat_app, client, user, auth_headers, monkeypatch):
    with chat_app.app_context():
        _mk_vehicle(user.id, 'Golf')
    _install(monkeypatch, decision='ALLOW', main_raises=OllamaError('main down'))
    r = _ask(client, auth_headers, user.id, 'total across all cars?')
    assert r.status_code == 503
    assert r.get_json().get('code') in ('ai_unavailable', 'ai_not_configured')


def test_empty_question_rejected(chat_app, client, user, auth_headers, monkeypatch):
    with chat_app.app_context():
        _mk_vehicle(user.id, 'Golf')
    _install(monkeypatch)
    r = _ask(client, auth_headers, user.id, '---QUESTION END---')  # sanitises to empty
    assert r.status_code == 400

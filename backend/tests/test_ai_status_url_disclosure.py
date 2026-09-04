"""Tests for R4-27 — /predictions/status must not leak the Ollama URL.

The online branch returned the resolved OLLAMA_URL to every authenticated
user. That is internal infrastructure detail — typically a private host and
port on the deployment's own network — and knowing it tells an ordinary user
(or anyone with a stolen session) where an unauthenticated model API lives.

No frontend reads this field: the user-facing page uses only `enabled`, and the
admin panel renders `settings.ollama_url` from the admin settings endpoint. So
it is kept for admins as a diagnostic and withheld from everyone else.
"""

import pytest
import requests

import app.routes.predictions as predictions_module
from app import db
from app.models import User

OLLAMA_URL = 'http://ollama.internal:11434'


class _TagsResponse:
    status_code = 200

    @staticmethod
    def json():
        return {'models': [{'name': 'llama3'}]}


@pytest.fixture
def ai_online(app, monkeypatch):
    """An enabled, reachable Ollama, without touching the network."""
    monkeypatch.setattr(predictions_module, 'ollama_enabled', lambda: True)
    monkeypatch.setattr(predictions_module, 'get_ollama_url', lambda: OLLAMA_URL)
    monkeypatch.setattr(predictions_module, 'validate_ollama_url', lambda url: url)
    monkeypatch.setattr(requests, 'get', lambda *args, **kwargs: _TagsResponse())


@pytest.fixture
def accounts(app):
    with app.app_context():
        admin = User(username='aiadmin', email='aiadmin@example.com',
                     is_active=True, is_admin=True)
        admin.set_password('StrongPass123!')
        member = User(username='aimember', email='aimember@example.com',
                      is_active=True, is_admin=False)
        member.set_password('StrongPass123!')
        db.session.add_all([admin, member])
        db.session.commit()
        return admin.id, member.id


def test_a_non_admin_never_receives_the_ollama_url(app, client, auth_headers,
                                                   ai_online, accounts):
    _admin_id, member_id = accounts

    response = client.get('/api/predictions/status',
                          headers=auth_headers(member_id, is_admin=False))

    assert response.status_code == 200
    payload = response.get_json()
    assert 'url' not in payload                       # was: the internal URL
    assert OLLAMA_URL not in response.get_data(as_text=True)


def test_a_non_admin_still_gets_the_status_the_ui_needs(app, client, auth_headers,
                                                        ai_online, accounts):
    """SmartRecommendations reads `enabled`; nothing else must break."""
    _admin_id, member_id = accounts

    payload = client.get('/api/predictions/status',
                         headers=auth_headers(member_id, is_admin=False)).get_json()

    assert payload['enabled'] is True
    assert payload['status'] == 'online'
    assert payload['models'] == ['llama3']


def test_an_admin_still_receives_the_url(app, client, auth_headers,
                                         ai_online, accounts):
    admin_id, _member_id = accounts

    payload = client.get('/api/predictions/status',
                         headers=auth_headers(admin_id, is_admin=True)).get_json()

    assert payload['url'] == OLLAMA_URL


@pytest.mark.parametrize('is_admin', [True, False])
def test_the_disabled_branch_exposes_nothing(app, client, auth_headers, monkeypatch,
                                             accounts, is_admin):
    monkeypatch.setattr(predictions_module, 'ollama_enabled', lambda: False)
    admin_id, member_id = accounts
    user_id = admin_id if is_admin else member_id

    payload = client.get('/api/predictions/status',
                         headers=auth_headers(user_id, is_admin=is_admin)).get_json()

    assert payload['enabled'] is False
    assert 'url' not in payload


@pytest.mark.parametrize('is_admin', [True, False])
def test_the_unreachable_branch_exposes_nothing(app, client, auth_headers, monkeypatch,
                                                accounts, is_admin):
    """An offline Ollama must not leak the URL through an error payload."""
    monkeypatch.setattr(predictions_module, 'ollama_enabled', lambda: True)
    monkeypatch.setattr(predictions_module, 'get_ollama_url', lambda: OLLAMA_URL)
    monkeypatch.setattr(predictions_module, 'validate_ollama_url', lambda url: url)

    def _boom(*args, **kwargs):
        raise requests.ConnectionError('unreachable')

    monkeypatch.setattr(requests, 'get', _boom)
    admin_id, member_id = accounts
    user_id = admin_id if is_admin else member_id

    response = client.get('/api/predictions/status',
                          headers=auth_headers(user_id, is_admin=is_admin))

    assert response.status_code == 200
    assert 'url' not in response.get_json()
    assert OLLAMA_URL not in response.get_data(as_text=True)


def test_the_endpoint_still_requires_authentication(client):
    assert client.get('/api/predictions/status').status_code == 401

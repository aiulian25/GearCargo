"""SEC-04: get_session_data must never eval Redis contents.

Sessions are written as JSON. A non-JSON Redis value is treated as corrupt and
ignored (no eval, no raise) — control falls through to the durable DB mirror,
which returns None when there is no valid session → safe re-login.
"""

import json

import app.routes.auth as auth


class _FakeRedis:
    """Minimal stand-in for the module-level redis_client."""
    def __init__(self, value):
        self._value = value

    def get(self, key):
        return self._value


def test_valid_json_session_is_parsed(app, monkeypatch):
    with app.app_context():
        monkeypatch.setattr(auth, 'redis_client',
                            _FakeRedis(json.dumps({'jti': 'abc', 'device': 'x'})))
        data = auth.get_session_data(1, 'abc')
        assert data == {'jti': 'abc', 'device': 'x'}


def test_non_json_blob_is_ignored_and_not_evaled(app, monkeypatch):
    # A legacy Python-dict-string (repr) is NOT valid JSON. It must be ignored
    # (not eval'd) and fall through to the DB mirror → None for a fresh app.
    with app.app_context():
        monkeypatch.setattr(auth, 'redis_client',
                            _FakeRedis("{'jti': 'abc', 'device': 'x'}"))
        monkeypatch.setattr(auth, '_db_get_session_data', lambda uid, jti: None)
        assert auth.get_session_data(1, 'abc') is None


def test_malicious_blob_is_not_executed(app, monkeypatch):
    # Defense-in-depth: even a value crafted to look like a call is inert —
    # json.loads rejects it and we never parse it any other way.
    sentinel = {'never': 'called'}
    called = {'db': False}

    def _fake_db(uid, jti):
        called['db'] = True
        return sentinel

    with app.app_context():
        monkeypatch.setattr(auth, 'redis_client', _FakeRedis("__import__('os').system('id')"))
        monkeypatch.setattr(auth, '_db_get_session_data', _fake_db)
        result = auth.get_session_data(1, 'abc')
        assert result is sentinel and called['db'] is True


def test_bytes_json_is_decoded_and_parsed(app, monkeypatch):
    with app.app_context():
        monkeypatch.setattr(auth, 'redis_client',
                            _FakeRedis(json.dumps({'jti': 'z'}).encode('utf-8')))
        assert auth.get_session_data(1, 'z') == {'jti': 'z'}

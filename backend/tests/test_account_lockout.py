"""Unit tests for the DB-backed account lockout fallback (app/routes/auth.py).

This is the "fail safe when Redis is down" path (IMPROVEMENTS top priority). We
force ``redis_client = None`` so the DB fallback is exercised, then assert the
account locks after MAX_LOGIN_ATTEMPTS and reports as locked.
"""

import app.routes.auth as auth_module
from app import db
from app.models import User


def _create_user(email):
    u = User(username=email.split("@")[0], email=email, is_active=True)
    u.set_password("StrongPass123!")
    db.session.add(u)
    db.session.commit()


def test_locks_after_max_attempts(app, monkeypatch):
    monkeypatch.setattr(auth_module, "redis_client", None)
    with app.app_context():
        _create_user("lock@example.com")

        locked = False
        remaining = 0
        for _ in range(auth_module.MAX_LOGIN_ATTEMPTS):
            locked, remaining, _attempts = auth_module.record_failed_login("lock@example.com")

        assert locked is True
        assert remaining > 0

        is_locked, rem = auth_module.is_account_locked("lock@example.com")
        assert is_locked is True
        assert rem > 0


def test_not_locked_before_threshold(app, monkeypatch):
    monkeypatch.setattr(auth_module, "redis_client", None)
    with app.app_context():
        _create_user("safe@example.com")

        for _ in range(auth_module.MAX_LOGIN_ATTEMPTS - 1):
            locked, _rem, _attempts = auth_module.record_failed_login("safe@example.com")
            assert locked is False

        is_locked, _ = auth_module.is_account_locked("safe@example.com")
        assert is_locked is False


def test_unknown_email_does_not_crash(app, monkeypatch):
    monkeypatch.setattr(auth_module, "redis_client", None)
    with app.app_context():
        # No user row — must report not-locked rather than raising.
        is_locked, rem = auth_module.is_account_locked("ghost@example.com")
        assert is_locked is False
        assert rem == 0

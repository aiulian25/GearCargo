"""Regression tests for M7: failed 2FA attempts count toward the email-keyed
account lockout, so a phished-password attacker cannot grind the 6-digit TOTP
(previously bounded only by the global per-IP rate limit). redis_client is
forced None to exercise the DB-backed lockout fallback (same as
test_account_lockout.py).
"""

import pyotp

import app.routes.auth as auth_module
from app import db
from app.models import User


def _user_with_2fa(email):
    """Create an active user with 2FA enabled; return the TOTP secret."""
    from app.routes.auth import _set_totp_secret

    secret = pyotp.random_base32()
    u = User(username=email.split("@")[0], email=email, is_active=True)
    u.set_password("StrongPass123!")
    _set_totp_secret(u, secret)          # encrypt + store
    u.two_factor_enabled = True
    db.session.add(u)
    db.session.commit()
    return secret


def test_failed_2fa_attempts_lock_account(app, client, monkeypatch):
    """Correct password + wrong TOTP, repeated, locks the account (429)."""
    monkeypatch.setattr(auth_module, "redis_client", None)  # DB fallback
    with app.app_context():
        _user_with_2fa("tfa@example.com")

    locked = False
    for _ in range(auth_module.MAX_LOGIN_ATTEMPTS):
        resp = client.post("/api/auth/login", json={
            "email": "tfa@example.com", "password": "StrongPass123!", "totp_code": "000000",
        })
        if resp.status_code == 429:
            locked = True
            assert resp.get_json().get("locked") is True
            break
        assert resp.status_code == 401  # invalid 2FA code, not yet locked
    assert locked, "account must lock after repeated failed 2FA attempts"


def test_correct_2fa_after_failures_succeeds_and_clears_counter(app, client, monkeypatch):
    """A valid code below the threshold logs in AND resets the failed counter."""
    monkeypatch.setattr(auth_module, "redis_client", None)
    with app.app_context():
        secret = _user_with_2fa("tfa2@example.com")

    for _ in range(2):  # two wrong attempts (below the 5-attempt threshold)
        r = client.post("/api/auth/login", json={
            "email": "tfa2@example.com", "password": "StrongPass123!", "totp_code": "000000",
        })
        assert r.status_code == 401

    valid = pyotp.TOTP(secret).now()
    r = client.post("/api/auth/login", json={
        "email": "tfa2@example.com", "password": "StrongPass123!", "totp_code": valid,
    })
    assert r.status_code == 200, r.get_json()

    with app.app_context():
        u = User.query.filter_by(email="tfa2@example.com").first()
        assert (u.failed_login_attempts or 0) == 0  # cleared on success

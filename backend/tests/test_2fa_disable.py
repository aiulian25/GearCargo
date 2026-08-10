"""Regression tests for L7: disabling 2FA must require a second factor, not
just the account password.

Password-only disable meant a phished password plus a hijacked session could
strip the second factor — the exact attack 2FA defends against. `disable_2fa`
now also demands a live TOTP or an unused backup code while 2FA is enabled.
"""

import pyotp
from werkzeug.security import generate_password_hash

from app import db
from app.models import User
from app.routes.auth import _set_totp_secret

PASSWORD = "StrongPass123!"
DISABLE_URL = "/api/auth/2fa/disable"


def _enable_2fa(uid, backup_plain="DEADBEEF"):
    """Put the user into a realistic enabled-2FA state: encrypted TOTP secret
    (as production stores it) + one hashed backup code. Returns the plaintext
    TOTP secret so the caller can mint live codes."""
    u = db.session.get(User, uid)
    secret = pyotp.random_base32()
    u.two_factor_enabled = True
    _set_totp_secret(u, secret)  # encrypt_field, exactly like /2fa/verify
    u.two_factor_backup_codes = [
        generate_password_hash(backup_plain, method="pbkdf2:sha256")
    ]
    db.session.commit()
    return secret


def _still_enabled(app, uid):
    with app.app_context():
        db.session.remove()
        return db.session.get(User, uid).two_factor_enabled is True


def test_password_only_is_rejected_when_enabled(app, client, user, auth_headers):
    """The core L7 fix: password without a second factor no longer disables."""
    with app.app_context():
        _enable_2fa(user.id)
        uid = user.id

    resp = client.post(DISABLE_URL, json={"password": PASSWORD}, headers=auth_headers(uid))
    assert resp.status_code == 401, resp.get_json()
    assert _still_enabled(app, uid)  # untouched


def test_valid_totp_disables(app, client, user, auth_headers):
    with app.app_context():
        secret = _enable_2fa(user.id)
        uid = user.id

    resp = client.post(
        DISABLE_URL,
        json={"password": PASSWORD, "totp_code": pyotp.TOTP(secret).now()},
        headers=auth_headers(uid),
    )
    assert resp.status_code == 200, resp.get_json()
    with app.app_context():
        db.session.remove()
        u = db.session.get(User, uid)
        assert u.two_factor_enabled is False
        assert u.two_factor_secret is None
        assert u.two_factor_backup_codes is None  # fully torn down


def test_valid_backup_code_disables_and_normalizes(app, client, user, auth_headers):
    """A backup code works too (the lost-device recovery path), and the same
    upper()/strip-dashes normalization as login is applied."""
    with app.app_context():
        _enable_2fa(user.id, backup_plain="DEADBEEF")
        uid = user.id

    # sent lower-case with a dash → normalized to DEADBEEF server-side
    resp = client.post(
        DISABLE_URL,
        json={"password": PASSWORD, "backup_code": "dead-beef"},
        headers=auth_headers(uid),
    )
    assert resp.status_code == 200, resp.get_json()
    assert not _still_enabled(app, uid)


def test_wrong_totp_is_rejected(app, client, user, auth_headers):
    with app.app_context():
        secret = _enable_2fa(user.id)
        uid = user.id

    real = pyotp.TOTP(secret).now()
    wrong = str((int(real) + 1) % 1_000_000).zfill(6)  # guaranteed != real
    resp = client.post(
        DISABLE_URL,
        json={"password": PASSWORD, "totp_code": wrong},
        headers=auth_headers(uid),
    )
    assert resp.status_code == 401, resp.get_json()
    assert _still_enabled(app, uid)


def test_wrong_password_still_rejected_first(app, client, user, auth_headers):
    """A valid code cannot substitute for the password (password gate unchanged)."""
    with app.app_context():
        secret = _enable_2fa(user.id)
        uid = user.id

    resp = client.post(
        DISABLE_URL,
        json={"password": "NotMyPassword!", "totp_code": pyotp.TOTP(secret).now()},
        headers=auth_headers(uid),
    )
    assert resp.status_code == 401
    assert "Password" in (resp.get_json() or {}).get("error", "")
    assert _still_enabled(app, uid)


def test_disable_when_not_enabled_is_noop(app, client, user, auth_headers):
    """With 2FA already off there is no factor to challenge — password alone
    stays a harmless no-op (the challenge is gated on two_factor_enabled)."""
    with app.app_context():
        uid = user.id  # fixture user has 2FA disabled

    resp = client.post(DISABLE_URL, json={"password": PASSWORD}, headers=auth_headers(uid))
    assert resp.status_code == 200, resp.get_json()

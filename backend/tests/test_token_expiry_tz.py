"""Regression tests for C1: naive/aware datetime crash in token verification.

Token-expiry columns (password_reset_expires, email_verification_expires,
notification_email_token_exp) are written with an aware ``datetime.now(utc)``
but stored in a tz-naive ``db.DateTime`` column, so SQLAlchemy reads them back
WITHOUT tzinfo. Comparing that naive value against an aware ``datetime.now(utc)``
raised ``TypeError`` and 500'd every valid reset/verification request.

The key ingredient the rest of the suite lacked is ``db.session.remove()``
BETWEEN generating the token and verifying it — that forces a fresh DB load so
the datetime comes back naive, exactly as it does across separate HTTP requests
in production.
"""

from datetime import datetime, timedelta, timezone

from app import db
from app.models import BlockedDevice, BlockedIP, User


def _make_user(email="reset@example.com"):
    u = User(username=email.split("@")[0], email=email, is_active=True)
    u.set_password("StrongPass123!")
    db.session.add(u)
    db.session.commit()
    return u


def test_password_reset_verify_accepts_valid_token(app):
    """A valid reset token, loaded fresh from the DB, resets the password (200)."""
    with app.app_context():
        u = _make_user()
        raw = u.generate_reset_token()
        db.session.remove()  # fresh, tz-naive reload — the condition that 500'd

        client = app.test_client()
        resp = client.post(
            "/api/auth/password-reset/verify",
            json={"token": raw, "new_password": "An0therStrongPass!"},
        )
        assert resp.status_code == 200, resp.get_json()

        # And the new password actually works.
        db.session.remove()
        reloaded = User.query.filter_by(email="reset@example.com").first()
        assert reloaded.check_password("An0therStrongPass!")


def test_password_reset_verify_rejects_expired_token_without_500(app):
    """An expired reset token is rejected with 401, never a 500."""
    with app.app_context():
        u = _make_user("expired@example.com")
        raw = u.generate_reset_token()
        u.password_reset_expires = datetime.now(timezone.utc) - timedelta(hours=1)
        db.session.commit()
        db.session.remove()

        client = app.test_client()
        resp = client.post(
            "/api/auth/password-reset/verify",
            json={"token": raw, "new_password": "An0therStrongPass!"},
        )
        assert resp.status_code == 401, resp.get_json()


def test_email_verify_accepts_valid_token(app):
    """A valid email-verification token, loaded fresh, verifies the email (200)."""
    with app.app_context():
        u = _make_user("verify@example.com")
        token = u.generate_verification_token()
        db.session.remove()

        client = app.test_client()
        resp = client.post("/api/auth/email/verify", json={"token": token})
        assert resp.status_code == 200, resp.get_json()

        db.session.remove()
        reloaded = User.query.filter_by(email="verify@example.com").first()
        assert reloaded.email_verified is True


def test_notification_email_verify_accepts_valid_token(app, client, user, auth_headers):
    """Authenticated notification-email verify (double opt-in step 2).

    This is the endpoint whose expiry check lives in ``auth.py`` — the third
    token path fixed for C1. Requires an authenticated client; the token is
    generated, committed, then the session is cleared so the reload is naive.
    """
    uid = user.id
    with app.app_context():
        u = db.session.get(User, uid)
        token = u.generate_notification_email_token(expires_hours=72)
        db.session.commit()
        db.session.remove()  # fresh, tz-naive reload — exercises auth.py _as_utc

    resp = client.post(
        "/api/auth/notification-email/verify",
        json={"token": token},
        headers=auth_headers(uid),
    )
    assert resp.status_code == 200, resp.get_json()

    with app.app_context():
        assert db.session.get(User, uid).notification_email_verified is True


def test_notification_email_verify_rejects_expired_token_without_500(app, client, user, auth_headers):
    """An expired notification-email token is rejected with 401, never a 500."""
    uid = user.id
    with app.app_context():
        u = db.session.get(User, uid)
        token = u.generate_notification_email_token(expires_hours=72)
        u.notification_email_token_exp = datetime.now(timezone.utc) - timedelta(hours=1)
        db.session.commit()
        db.session.remove()

    resp = client.post(
        "/api/auth/notification-email/verify",
        json={"token": token},
        headers=auth_headers(uid),
    )
    assert resp.status_code == 401, resp.get_json()


# ---------------------------------------------------------------------------
# C1 follow-up: BlockedIP / BlockedDevice.is_blocked() had the identical
# naive/aware comparison. A manual admin block WITH an expiry stores an aware
# datetime into a naive column; the next login attempt from that IP/device
# calls is_blocked() on a fresh (naive) reload and used to 500 inside login().
# ---------------------------------------------------------------------------

def test_blocked_ip_with_future_expiry_does_not_crash(app):
    """A still-active timed block reports blocked (True) without TypeError."""
    with app.app_context():
        db.session.add(BlockedIP(
            ip_address="203.0.113.7", is_active=True, block_type="manual",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        ))
        db.session.commit()
        db.session.remove()  # fresh, tz-naive reload — the condition that 500'd

        blocked, record = BlockedIP.is_blocked("203.0.113.7")
        assert blocked is True and record is not None


def test_blocked_ip_with_past_expiry_auto_deactivates(app):
    """An expired timed block reports not-blocked (False) and self-clears."""
    with app.app_context():
        db.session.add(BlockedIP(
            ip_address="203.0.113.8", is_active=True, block_type="manual",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        ))
        db.session.commit()
        db.session.remove()

        blocked, _ = BlockedIP.is_blocked("203.0.113.8")
        assert blocked is False
        db.session.remove()
        assert BlockedIP.query.filter_by(ip_address="203.0.113.8").first().is_active is False


def test_blocked_device_with_future_expiry_does_not_crash(app):
    """The device path shares the identical method body — same guard."""
    with app.app_context():
        fp = BlockedDevice.generate_fingerprint("Mozilla/5.0 Test")
        db.session.add(BlockedDevice(
            device_fingerprint=fp, is_active=True, block_type="manual",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        ))
        db.session.commit()
        db.session.remove()

        blocked, record = BlockedDevice.is_blocked("Mozilla/5.0 Test")
        assert blocked is True and record is not None

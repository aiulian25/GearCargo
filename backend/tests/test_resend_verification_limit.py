"""R4: the public resend-verification endpoint must not be an email bomb.

It mails an address the caller supplies and rotates the account's verification
token on every call, but carried no per-endpoint limit — so an attacker could
both flood an unverified address and keep invalidating the victim's outstanding
link. Two independent controls now apply:

  * a per-IP limit registered in create_app() ('5 per hour'), and
  * a per-ACCOUNT cooldown (RESEND_VERIFICATION_COOLDOWN) that a distributed
    attacker can't dodge by rotating IPs.

Rate limiting is disabled under TestingConfig, so the per-IP half is asserted by
checking the registration rather than by hammering the endpoint.
"""

from datetime import datetime, timedelta, timezone

import app.routes.auth as auth_module
from app import db
from app.models import User

URL = "/api/auth/email/resend-verification"


def _unverified(email="unv@example.com"):
    u = User(username=email.split("@")[0], email=email, is_active=True)
    u.set_password("StrongPass123!")
    u.email_verified = False
    db.session.add(u)
    db.session.commit()
    return u.id


def test_per_ip_limit_is_registered(app):
    """create_app() must attach the limit to this endpoint (it is a no-op while
    RATELIMIT_ENABLED is false, so assert the wiring exists)."""
    import inspect

    from app import create_app  # noqa: F401  (import kept for symmetry)

    source = inspect.getsource(create_app)
    assert "auth.resend_verification_email" in source
    assert "5 per hour" in source.split("auth.resend_verification_email")[1][:120]


def test_first_resend_sends_and_rotates(app, client, monkeypatch):
    sent = []
    app.config["MAIL_ENABLED"] = True

    from app.services import email_service
    monkeypatch.setattr(email_service.EmailVerificationService, "send_verification_email",
                        staticmethod(lambda user, token: sent.append(token) or True))

    with app.app_context():
        uid = _unverified()

    resp = client.post(URL, json={"email": "unv@example.com"})
    assert resp.status_code == 200
    assert len(sent) == 1

    with app.app_context():
        db.session.remove()
        assert db.session.get(User, uid).email_verification_token is not None


def test_second_resend_within_cooldown_is_silently_skipped(app, client, monkeypatch):
    """No second email, and the victim's existing token must SURVIVE."""
    sent = []
    app.config["MAIL_ENABLED"] = True

    from app.services import email_service
    monkeypatch.setattr(email_service.EmailVerificationService, "send_verification_email",
                        staticmethod(lambda user, token: sent.append(token) or True))

    with app.app_context():
        uid = _unverified("unv2@example.com")

    assert client.post(URL, json={"email": "unv2@example.com"}).status_code == 200
    with app.app_context():
        db.session.remove()
        first_token = db.session.get(User, uid).email_verification_token

    resp = client.post(URL, json={"email": "unv2@example.com"})
    assert resp.status_code == 200                      # same generic response
    assert len(sent) == 1, "second email must not be sent inside the cooldown"

    with app.app_context():
        db.session.remove()
        # The link already in the victim's inbox still works.
        assert db.session.get(User, uid).email_verification_token == first_token


def test_resend_allowed_again_after_cooldown(app, client, monkeypatch):
    sent = []
    app.config["MAIL_ENABLED"] = True

    from app.services import email_service
    monkeypatch.setattr(email_service.EmailVerificationService, "send_verification_email",
                        staticmethod(lambda user, token: sent.append(token) or True))

    with app.app_context():
        uid = _unverified("unv3@example.com")

    assert client.post(URL, json={"email": "unv3@example.com"}).status_code == 200
    assert len(sent) == 1

    # Age the outstanding token past the cooldown (issue time is derived from expiry).
    with app.app_context():
        u = db.session.get(User, uid)
        u.email_verification_expires = (
            u.email_verification_expires - auth_module.RESEND_VERIFICATION_COOLDOWN - timedelta(minutes=1)
        )
        db.session.commit()

    assert client.post(URL, json={"email": "unv3@example.com"}).status_code == 200
    assert len(sent) == 2, "a genuine resend after the cooldown must still work"


def test_response_is_identical_for_unknown_address(app, client):
    """Enumeration guard unchanged: same body whether or not the account exists."""
    app.config["MAIL_ENABLED"] = True
    with app.app_context():
        _unverified("unv4@example.com")

    known = client.post(URL, json={"email": "unv4@example.com"})
    unknown = client.post(URL, json={"email": "nobody@example.com"})
    assert known.status_code == unknown.status_code == 200
    assert known.get_json() == unknown.get_json()

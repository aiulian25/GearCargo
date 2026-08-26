"""Emailed links must land on the domain the recipient is allowed to log in on.

Bug: every link builder hardcoded USER_DOMAIN, so an admin verification email
(admin console → admin.py:153 → send_verification_email) pointed at the USER
domain. `_enforce_login_domain_policy` refuses admin logins there ("Admin
accounts must login from the admin domain"), so the admin could never complete
verification — and the admin's verification token was delivered onto the
user-facing host. `link_domain_for(user)` now picks ADMIN_DOMAIN for admins.
"""

import pytest

from app import db
from app.models import User
from app.services import email_service
from app.services.email_service import link_domain_for

ADMIN_DOMAIN = "admin.example.com"
USER_DOMAIN = "app.example.com"


@pytest.fixture()
def domains(app):
    app.config["ADMIN_DOMAIN"] = ADMIN_DOMAIN
    app.config["USER_DOMAIN"] = USER_DOMAIN
    app.config["MAIL_ENABLED"] = True
    return app


def _mk(is_admin, email):
    u = User(username=email.split("@")[0], email=email, is_active=True, is_admin=is_admin)
    u.set_password("StrongPass123!")
    db.session.add(u)
    db.session.commit()
    return u


def test_admin_link_uses_admin_domain(domains, app):
    with app.app_context():
        assert link_domain_for(_mk(True, "boss@example.com")) == f"https://{ADMIN_DOMAIN}"


def test_regular_user_link_still_uses_user_domain(domains, app):
    with app.app_context():
        assert link_domain_for(_mk(False, "joe@example.com")) == f"https://{USER_DOMAIN}"


def test_admin_falls_back_to_user_domain_when_no_admin_domain(domains, app):
    """No domain split configured → unchanged behaviour for everyone."""
    with app.app_context():
        app.config["ADMIN_DOMAIN"] = ""
        assert link_domain_for(_mk(True, "boss2@example.com")) == f"https://{USER_DOMAIN}"


def test_commented_out_admin_domain_is_ignored(domains, app):
    """config.py keeps '#...' values; they must not become the link host."""
    with app.app_context():
        app.config["ADMIN_DOMAIN"] = "#admin.example.com"
        assert link_domain_for(_mk(True, "boss3@example.com")) == f"https://{USER_DOMAIN}"


def test_verification_email_to_admin_points_at_admin_domain(domains, app, monkeypatch):
    """End-to-end through the builder the admin console actually calls."""
    sent = {}
    monkeypatch.setattr(
        email_service.EmailService, "send_email",
        staticmethod(lambda to, subject, content_html, **kw: sent.update(html=content_html) or True),
    )

    with app.app_context():
        admin = _mk(True, "admin@example.com")
        token = admin.generate_verification_token()
        email_service.email_verification_service.send_verification_email(admin, token)

    assert f"https://{ADMIN_DOMAIN}/verify-email?token=" in sent["html"]
    assert USER_DOMAIN not in sent["html"]      # the bug: link landed on the user domain


def test_password_reset_email_to_admin_points_at_admin_domain(domains, app, monkeypatch):
    """Sibling caller — same bug class, same fix."""
    sent = {}
    monkeypatch.setattr(
        email_service.EmailService, "send_email",
        staticmethod(lambda to, subject, content_html, **kw: sent.update(html=content_html) or True),
    )

    with app.app_context():
        admin = _mk(True, "admin2@example.com")
        email_service.password_reset_email_service.send_password_reset_email(admin, "tok123")

    assert ADMIN_DOMAIN in sent["html"]
    assert USER_DOMAIN not in sent["html"]

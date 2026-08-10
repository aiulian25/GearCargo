"""Regression tests for M10: user-controlled values must be HTML-escaped in the
f-string-built notification-email verification bodies.

`BASE_TEMPLATE` renders the assembled body with `{{ content | safe }}`, so the
raw f-string `content_html` is delivered verbatim. A display name like
`<img src=x onerror=...>` would otherwise reach a third-party address of the
user's choosing — a phishing canvas on the instance's own mail domain. The
bodies now wrap `current_user.display_name` in `markupsafe.escape`.

We capture the `content_html` handed to EmailService.send_email and assert the
payload arrives escaped. Note the body also contains a legitimate
`<img src="…/icons/logo.png">`, so we assert specifically on the payload's raw
vs. escaped form rather than "no <img at all".
"""

from app import db
from app.models import User

PASSWORD = "StrongPass123!"
PAYLOAD = "<img src=x onerror=alert(1)>"


def _capture_send_email(monkeypatch):
    """Patch EmailService.send_email to record the inner content_html."""
    captured = {}
    from app.services import email_service

    def _fake(to, subject, content_html, **kwargs):
        captured["to"] = to
        captured["html"] = content_html
        return True

    monkeypatch.setattr(
        email_service.EmailService, "send_email", staticmethod(_fake)
    )
    return captured


def test_set_notification_email_escapes_display_name(app, client, user, auth_headers, monkeypatch):
    captured = _capture_send_email(monkeypatch)

    app.config["MAIL_ENABLED"] = True  # route is gated behind this
    with app.app_context():
        u = db.session.get(User, user.id)
        u.first_name = PAYLOAD  # display_name = "<payload> Doe"
        u.last_name = "Doe"
        db.session.commit()
        uid = u.id

    resp = client.post(
        "/api/auth/notification-email",
        json={"email": "canvas@example.com", "consent": True},
        headers=auth_headers(uid),
    )
    assert resp.status_code == 200, resp.get_json()

    html = captured["html"]
    assert "&lt;img src=x onerror" in html          # escaped
    assert "<img src=x onerror" not in html          # raw payload gone
    assert captured["to"] == "canvas@example.com"    # went to the chosen address


def test_resend_notification_verification_escapes_display_name(app, client, user, auth_headers, monkeypatch):
    captured = _capture_send_email(monkeypatch)

    app.config["MAIL_ENABLED"] = True
    with app.app_context():
        u = db.session.get(User, user.id)
        u.first_name = PAYLOAD
        u.last_name = "Doe"
        u.set_notification_email_encrypted("canvas@example.com")
        u.notification_email_verified = False
        db.session.commit()
        uid = u.id

    resp = client.post(
        "/api/auth/notification-email/resend",
        headers=auth_headers(uid),
    )
    assert resp.status_code == 200, resp.get_json()

    html = captured["html"]
    assert "&lt;img src=x onerror" in html
    assert "<img src=x onerror" not in html

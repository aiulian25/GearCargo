"""R7: verification tokens are stored as SHA-256 hashes, not plaintext.

`password_reset_token` was hashed by S08, but `email_verification_token` and
`notification_email_token` still held the raw value — so a DB or backup leak
handed the reader working verification links. Both now store only the hash and
return the raw token to the caller (which goes in the email and is never
persisted).
"""

import hashlib

from app import db
from app.models import User

PASSWORD = "StrongPass123!"


def _user(email="tok@example.com", verified=False):
    u = User(username=email.split("@")[0], email=email, is_active=True)
    u.set_password(PASSWORD)
    u.email_verified = verified
    db.session.add(u)
    db.session.commit()
    return u


def _sha(raw):
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# --- account email verification ----------------------------------------------

def test_email_token_is_stored_hashed(app):
    with app.app_context():
        user = _user()
        raw = user.generate_verification_token()

        stored = db.session.get(User, user.id).email_verification_token
        assert stored != raw, "raw token must not be persisted"
        assert stored == _sha(raw)
        assert len(stored) == 64


def test_email_verification_round_trip_still_works(app, client):
    """The emailed (raw) token still verifies the account."""
    with app.app_context():
        user = _user("tok2@example.com")
        raw = user.generate_verification_token()
        uid = user.id

    resp = client.post("/api/auth/email/verify", json={"token": raw})
    assert resp.status_code == 200, resp.data[:150]

    with app.app_context():
        db.session.remove()
        assert db.session.get(User, uid).email_verified is True


def test_leaked_stored_hash_cannot_be_replayed(app, client):
    """The whole point: what a DB leak exposes must NOT work as a link token."""
    with app.app_context():
        user = _user("tok3@example.com")
        user.generate_verification_token()
        stored = user.email_verification_token
        uid = user.id

    resp = client.post("/api/auth/email/verify", json={"token": stored})
    assert resp.status_code == 401, resp.data[:150]

    with app.app_context():
        db.session.remove()
        assert db.session.get(User, uid).email_verified is False


# --- notification email verification -----------------------------------------

def test_notification_token_is_stored_hashed_and_verifies(app, client, auth_headers):
    app.config["MAIL_ENABLED"] = True
    with app.app_context():
        uid = _user("tok4@example.com").id

    from app.services import email_service
    # Capture the raw token handed to the email layer via the verify link.
    sent = {}
    original = email_service.EmailService.send_email
    email_service.EmailService.send_email = staticmethod(
        lambda to, subject, content_html, **kw: sent.update(html=content_html) or True
    )
    try:
        resp = client.post("/api/auth/notification-email",
                           json={"email": "alerts@example.com", "consent": True},
                           headers=auth_headers(uid))
        assert resp.status_code == 200, resp.get_json()
    finally:
        email_service.EmailService.send_email = original

    raw = sent["html"].split("verify_notification=")[1].split('"')[0]

    with app.app_context():
        db.session.remove()
        stored = db.session.get(User, uid).notification_email_token
        assert stored == _sha(raw) and stored != raw

    # The raw token from the email verifies; the stored hash does not.
    assert client.post("/api/auth/notification-email/verify", json={"token": stored},
                       headers=auth_headers(uid)).status_code == 401
    assert client.post("/api/auth/notification-email/verify", json={"token": raw},
                       headers=auth_headers(uid)).status_code == 200

    with app.app_context():
        db.session.remove()
        assert db.session.get(User, uid).notification_email_verified is True

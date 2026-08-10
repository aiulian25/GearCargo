"""Regression tests for M1: changing the account email must RESET email
verification (a "verified" flag asserts a specific address; carrying it to a new
address makes it meaningless and shows a false green state in the Profile UI).
MAIL_ENABLED is off in tests, so no verification email is sent — the token is
simply cleared.
"""

from app import db
from app.models import User


def test_changing_email_resets_verification(app, client, user, auth_headers):
    with app.app_context():
        u = db.session.get(User, user.id)
        u.email_verified = True
        u.email_verification_token = "stale-token"
        db.session.commit()
        uid = u.id

    resp = client.put(
        "/api/auth/me",
        json={"email": "newaddr@example.com", "current_password": "StrongPass123!"},
        headers=auth_headers(uid),
    )
    assert resp.status_code == 200, resp.get_json()
    # The endpoint's own response already reflects the reset.
    assert resp.get_json()["user"]["email"] == "newaddr@example.com"
    assert resp.get_json()["user"]["email_verified"] is False

    with app.app_context():
        db.session.remove()  # fresh read from disk
        u = User.query.filter_by(email="newaddr@example.com").first()
        assert u is not None
        assert u.email_verified is False
        assert u.email_verification_token is None  # stale token cleared


def test_same_email_keeps_verification(app, client, user, auth_headers):
    """A no-op email 'change' (same address) must NOT reset verification."""
    with app.app_context():
        u = db.session.get(User, user.id)
        u.email_verified = True
        db.session.commit()
        uid, same_email = u.id, u.email

    resp = client.put(
        "/api/auth/me",
        json={"email": same_email},  # unchanged → not a sensitive change
        headers=auth_headers(uid),
    )
    assert resp.status_code == 200, resp.get_json()

    with app.app_context():
        db.session.remove()
        assert User.query.get(uid).email_verified is True

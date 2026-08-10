"""Regression tests for H4: /auth/refresh must rotate AND revoke the old session.

Before the fix, refresh minted a new session but left the presented one valid
until the 48h wall, so a stolen refresh+access pair survived rotation and the
session tables accrued ~1 row/hour/user. Now the old jti is revoked (Redis key +
durable DB mirror) the moment the new session is issued.

Note on cookie precedence: /auth/refresh reads the refresh_token COOKIE before
the JSON body, so the replay uses a FRESH client (no cookies) and passes the old
token in the body — otherwise the client's newly-set cookie would mask it.
"""

from app import db
from app.models import User


def _make_user(email="refresh@example.com"):
    u = User(username=email.split("@")[0], email=email, is_active=True)
    u.set_password("StrongPass123!")
    db.session.add(u)
    db.session.commit()
    return u


def _issue_tokens(app, user):
    """Mint a real (access, refresh) pair + server-side session, like login."""
    from app.routes.auth import generate_tokens
    with app.test_request_context():
        access, refresh = generate_tokens(user)
    return access, refresh


def test_refresh_revokes_the_old_session(app):
    """After one refresh, replaying the OLD refresh token is rejected (401)."""
    with app.app_context():
        u = _make_user()
        _access, old_refresh = _issue_tokens(app, u)
        db.session.remove()

        # First refresh (fresh client → no cookie → uses the body token) → 200.
        c1 = app.test_client()
        r1 = c1.post("/api/auth/refresh", json={"refresh_token": old_refresh})
        assert r1.status_code == 200, r1.get_json()

        # Replay the OLD token from a cookie-less client → session revoked → 401.
        c2 = app.test_client()
        r2 = c2.post("/api/auth/refresh", json={"refresh_token": old_refresh})
        assert r2.status_code == 401, r2.get_json()
        assert r2.get_json().get("code") == "SESSION_EXPIRED"


def test_refresh_new_session_still_works(app):
    """The freshly-issued session (new cookie) is valid for the next refresh."""
    with app.app_context():
        u = _make_user("refresh2@example.com")
        _access, old_refresh = _issue_tokens(app, u)
        db.session.remove()

        client = app.test_client()
        # Rotate once — client now holds the NEW refresh_token cookie.
        r1 = client.post("/api/auth/refresh", json={"refresh_token": old_refresh})
        assert r1.status_code == 200, r1.get_json()

        # Same client, no body → uses the new cookie → still valid (rotates again).
        r2 = client.post("/api/auth/refresh")
        assert r2.status_code == 200, r2.get_json()

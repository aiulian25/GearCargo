"""Regression tests for M11: a blank username in the profile update must be
rejected, not silently written.

Previously `"username": ""` skipped the validated branch (falsy) yet was still
applied by the generic `profile_fields` loop, clearing the identity — and a
second empty write violated the `unique=True` constraint → 500. `username` is
now removed from that loop and the dedicated block rejects blank/whitespace with
a 400.

A username change is a "sensitive change", so these requests carry
`current_password` to pass that gate and reach the username validation.
"""

from app import db
from app.models import User

PASSWORD = "StrongPass123!"
ME_URL = "/api/auth/me"


def _username(app, uid):
    with app.app_context():
        db.session.remove()
        return db.session.get(User, uid).username


def test_blank_username_rejected(app, client, user, auth_headers):
    with app.app_context():
        uid = user.id

    resp = client.put(
        ME_URL,
        json={"username": "", "current_password": PASSWORD},
        headers=auth_headers(uid),
    )
    assert resp.status_code == 400, resp.get_json()
    assert resp.get_json()["error"] == "Username cannot be empty"
    assert _username(app, uid) == "testuser"  # unchanged


def test_whitespace_username_rejected(app, client, user, auth_headers):
    with app.app_context():
        uid = user.id

    resp = client.put(
        ME_URL,
        json={"username": "   ", "current_password": PASSWORD},
        headers=auth_headers(uid),
    )
    assert resp.status_code == 400, resp.get_json()
    assert resp.get_json()["error"] == "Username cannot be empty"
    assert _username(app, uid) == "testuser"


def test_valid_username_change_succeeds(app, client, user, auth_headers):
    with app.app_context():
        uid = user.id

    resp = client.put(
        ME_URL,
        json={"username": "newhandle", "current_password": PASSWORD},
        headers=auth_headers(uid),
    )
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["user"]["username"] == "newhandle"
    assert _username(app, uid) == "newhandle"


def test_unchanged_username_is_noop(app, client, user, auth_headers):
    """Re-submitting the same username must not be rejected or cleared (no
    sensitive change → no password needed)."""
    with app.app_context():
        uid = user.id

    resp = client.put(
        ME_URL,
        json={"username": "testuser"},
        headers=auth_headers(uid),
    )
    assert resp.status_code == 200, resp.get_json()
    assert _username(app, uid) == "testuser"


def test_duplicate_username_still_rejected(app, client, user, auth_headers):
    """The existing uniqueness guard is intact (400, not a 500)."""
    with app.app_context():
        other = User(username="taken", email="taken@example.com", is_active=True)
        other.set_password(PASSWORD)
        db.session.add(other)
        db.session.commit()
        uid = user.id

    resp = client.put(
        ME_URL,
        json={"username": "taken", "current_password": PASSWORD},
        headers=auth_headers(uid),
    )
    assert resp.status_code == 400, resp.get_json()
    assert resp.get_json()["error"] == "Username is already in use"
    assert _username(app, uid) == "testuser"

"""RT2: token validation on the PUBLIC calendar feed.

`/api/calendar/feed/<token>` is unauthenticated and serves a user's reminders as
ICS, so every branch that decides "is this token acceptable" matters. This file
covers the VALIDATION surface — claim type, signature, expiry, unknown user,
malformed input. Revocation/rotation behaviour lives in
`test_calendar_feed_revocation.py` (R8).

The `type: calendar_feed` check is the important one: without it, any ordinary
access JWT (which every logged-in client holds) would also unlock the feed.
"""

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app import db
from app.models import User

FEED_TOKEN_URL = "/api/calendar/feed-token"


def _user(email="cal@example.com"):
    u = User(username=email.split("@")[0], email=email, is_active=True)
    u.set_password("StrongPass123!")
    db.session.add(u)
    db.session.commit()
    return u.id


def _issue(client, uid, auth_headers):
    resp = client.post(FEED_TOKEN_URL, headers=auth_headers(uid))
    assert resp.status_code == 200, resp.data[:150]
    return resp.get_json()["token"]


def _encode(app, payload):
    return jwt.encode(payload, app.config["JWT_SECRET_KEY"], algorithm="HS256")


def test_valid_feed_token_serves_ics(app, client, auth_headers):
    with app.app_context():
        uid = _user()
    token = _issue(client, uid, auth_headers)

    resp = client.get(f"/api/calendar/feed/{token}")
    assert resp.status_code == 200
    assert resp.mimetype == "text/calendar"
    assert b"BEGIN:VCALENDAR" in resp.data and b"END:VCALENDAR" in resp.data


def _retype(app, token, claim_type):
    """Re-issue a REAL feed token with only the `type` claim changed.

    Built from a genuine token so every other claim (notably R8's `fs`
    fingerprint) stays valid — otherwise the fingerprint check would reject it
    first and this would silently stop testing the `type` guard at all.
    """
    payload = jwt.decode(token, app.config["JWT_SECRET_KEY"], algorithms=["HS256"])
    if claim_type is None:
        payload.pop("type", None)
    else:
        payload["type"] = claim_type
    return _encode(app, payload)


def test_access_jwt_cannot_open_the_feed(app, client, auth_headers):
    """An ordinary access token is signed with the SAME key — only the
    `type: calendar_feed` claim keeps it from unlocking the feed."""
    with app.app_context():
        uid = _user("cal2@example.com")
    real = _issue(client, uid, auth_headers)

    with app.app_context():
        access_like = _retype(app, real, "access")

    assert client.get(f"/api/calendar/feed/{access_like}").status_code == 401


@pytest.mark.parametrize("claim_type", ["access", "refresh", "calendar_feed_x", "", None])
def test_wrong_or_missing_type_claim_rejected(app, client, auth_headers, claim_type):
    with app.app_context():
        uid = _user(f"cal-{claim_type or 'none'}@example.com")
    real = _issue(client, uid, auth_headers)

    with app.app_context():
        token = _retype(app, real, claim_type)

    assert client.get(f"/api/calendar/feed/{token}").status_code == 401


def test_tampered_signature_rejected(app, client, auth_headers):
    with app.app_context():
        uid = _user("cal3@example.com")
    token = _issue(client, uid, auth_headers)

    header, payload, signature = token.split(".")
    flipped = "A" if signature[0] != "A" else "B"
    tampered = f"{header}.{payload}.{flipped}{signature[1:]}"

    assert client.get(f"/api/calendar/feed/{tampered}").status_code == 401


def test_token_signed_with_a_foreign_key_rejected(app, client):
    with app.app_context():
        uid = _user("cal4@example.com")
        forged = jwt.encode(
            {
                "user_id": uid,
                "type": "calendar_feed",
                "exp": datetime.now(timezone.utc) + timedelta(days=90),
            },
            "not-the-servers-secret", algorithm="HS256",
        )

    assert client.get(f"/api/calendar/feed/{forged}").status_code == 401


def test_expired_feed_token_rejected(app, client):
    with app.app_context():
        uid = _user("cal5@example.com")
        expired = _encode(app, {
            "user_id": uid,
            "type": "calendar_feed",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
        })

    assert client.get(f"/api/calendar/feed/{expired}").status_code == 401


def test_unknown_user_returns_404(app, client):
    with app.app_context():
        ghost = _encode(app, {
            "user_id": 999999,
            "type": "calendar_feed",
            "exp": datetime.now(timezone.utc) + timedelta(days=90),
        })

    assert client.get(f"/api/calendar/feed/{ghost}").status_code == 404


def test_malformed_token_rejected(app, client):
    for junk in ("not-a-jwt", "a.b.c", "..", "x" * 200):
        assert client.get(f"/api/calendar/feed/{junk}").status_code in (401, 404), junk

"""R8: ICS feed links must be revocable.

A feed URL was a bare 90-day JWT with no jti and no server-side state, so a
leaked link stayed live until it expired — issuing a new one did not kill the
old one. Every token now carries a fingerprint of the user's
`calendar_feed_secret`; rotating that secret revokes all outstanding links.
"""

import jwt

from app import db
from app.models import User

FEED_TOKEN_URL = "/api/calendar/feed-token"


def _user(email="feed@example.com"):
    u = User(username=email.split("@")[0], email=email, is_active=True)
    u.set_password("StrongPass123!")
    db.session.add(u)
    db.session.commit()
    return u.id


def _issue(client, uid, auth_headers):
    resp = client.post(FEED_TOKEN_URL, headers=auth_headers(uid))
    assert resp.status_code == 200, resp.data[:150]
    return resp.get_json()["token"]


def test_issued_feed_token_serves_the_ics(app, client, auth_headers):
    with app.app_context():
        uid = _user()
    token = _issue(client, uid, auth_headers)

    resp = client.get(f"/api/calendar/feed/{token}")
    assert resp.status_code == 200
    assert b"BEGIN:VCALENDAR" in resp.data


def test_revoking_kills_the_outstanding_link(app, client, auth_headers):
    """The kill switch: a link that already leaked stops working."""
    with app.app_context():
        uid = _user("feed2@example.com")
    token = _issue(client, uid, auth_headers)
    assert client.get(f"/api/calendar/feed/{token}").status_code == 200

    revoke = client.delete(FEED_TOKEN_URL, headers=auth_headers(uid))
    assert revoke.status_code == 200, revoke.data[:150]
    assert revoke.get_json()["message_key"] == "calendar.linkRevoked"

    assert client.get(f"/api/calendar/feed/{token}").status_code == 401


def test_new_link_works_after_revocation(app, client, auth_headers):
    with app.app_context():
        uid = _user("feed3@example.com")
    old = _issue(client, uid, auth_headers)
    client.delete(FEED_TOKEN_URL, headers=auth_headers(uid))

    new = _issue(client, uid, auth_headers)
    assert new != old
    assert client.get(f"/api/calendar/feed/{new}").status_code == 200
    assert client.get(f"/api/calendar/feed/{old}").status_code == 401


def test_issuing_a_second_link_does_not_revoke_the_first(app, client, auth_headers):
    """Generate is additive — only an explicit revoke is destructive, so a user
    who copies the link twice doesn't break their calendar subscription."""
    with app.app_context():
        uid = _user("feed4@example.com")
    first = _issue(client, uid, auth_headers)
    second = _issue(client, uid, auth_headers)

    assert client.get(f"/api/calendar/feed/{first}").status_code == 200
    assert client.get(f"/api/calendar/feed/{second}").status_code == 200


def test_legacy_token_without_fingerprint_is_rejected(app, client, auth_headers):
    """Fail closed: a token minted before R8 carries no 'fs' claim, so it can't
    be revoked — it must not be honoured."""
    from datetime import datetime, timedelta, timezone

    with app.app_context():
        uid = _user("feed5@example.com")
        legacy = jwt.encode(
            {
                "user_id": uid,
                "type": "calendar_feed",
                "exp": datetime.now(timezone.utc) + timedelta(days=90),
            },
            app.config["JWT_SECRET_KEY"], algorithm="HS256",
        )

    assert client.get(f"/api/calendar/feed/{legacy}").status_code == 401


def test_another_users_secret_cannot_authorise_a_feed(app, client, auth_headers):
    """A fingerprint is only valid for the user it belongs to."""
    with app.app_context():
        victim = _user("feed6@example.com")
        attacker = _user("feed7@example.com")

    victim_token = _issue(client, victim, auth_headers)
    attacker_token = _issue(client, attacker, auth_headers)

    # Attacker's own fingerprint pointed at the victim's user_id must fail.
    with app.app_context():
        payload = jwt.decode(attacker_token, app.config["JWT_SECRET_KEY"], algorithms=["HS256"])
        payload["user_id"] = victim
        forged = jwt.encode(payload, app.config["JWT_SECRET_KEY"], algorithm="HS256")

    assert client.get(f"/api/calendar/feed/{forged}").status_code == 401
    assert client.get(f"/api/calendar/feed/{victim_token}").status_code == 200


def test_revoke_requires_authentication(app, client):
    assert client.delete(FEED_TOKEN_URL).status_code == 401

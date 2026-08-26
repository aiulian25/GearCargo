"""RT1: the PUBLIC shared-report surface.

`/api/reports/shared/<token>` and `/shared/<token>/pdf` are unauthenticated and
serve one user's financial aggregates to anyone holding the link, yet had no
tests. These pin the whole lifecycle — issue, view, revoke, expire — plus the
guarantees that make the link safe to hand out: only a SHA-256 hash is stored,
the raw token is shown exactly once, and a revoked/expired/orphaned link stops
resolving.
"""

from datetime import timedelta

from app import db
from app.models import User
from app.models.report_share import ReportShare
from app.models.vehicle import Vehicle
from app.utils.timeutils import utc_naive_now

SHARES_URL = "/api/reports/shares"
PASSWORD = "StrongPass123!"


def _owner(email="share@example.com"):
    u = User(username=email.split("@")[0], email=email, is_active=True, currency="GBP")
    u.set_password(PASSWORD)
    db.session.add(u)
    db.session.commit()
    db.session.add(Vehicle(user_id=u.id, name="Shared Car", make="VW", model="Golf"))
    db.session.commit()
    return u.id


def _create_share(client, uid, auth_headers, **payload):
    body = {"period": "current_month", **payload}
    resp = client.post(SHARES_URL, json=body, headers=auth_headers(uid))
    assert resp.status_code == 201, resp.data[:200]
    return resp.get_json()


# --- happy path ---------------------------------------------------------------

def test_share_link_serves_the_report_without_auth(app, client, auth_headers):
    with app.app_context():
        uid = _owner()
    share = _create_share(client, uid, auth_headers, label="Q3")

    # No Authorization header at all — this is the point of a share link.
    resp = client.get(f"/api/reports/shared/{share['token']}")
    assert resp.status_code == 200, resp.data[:200]
    body = resp.get_json()
    assert body["label"] == "Q3"
    for key in ("period_label", "entry_counts", "totals", "currency"):
        assert key in body


def test_raw_token_is_never_persisted(app, client, auth_headers):
    """Only the SHA-256 hash is stored, so a DB leak yields no working link."""
    with app.app_context():
        uid = _owner("share2@example.com")
    share = _create_share(client, uid, auth_headers)
    raw = share["token"]

    with app.app_context():
        db.session.remove()
        row = ReportShare.query.filter_by(token_hash=ReportShare.hash_token(raw)).first()
        assert row is not None
        assert row.token_hash != raw
        assert len(row.token_hash) == 64
        # The stored hash must not itself work as a token.
    assert client.get(f"/api/reports/shared/{row.token_hash}").status_code == 404


def test_listing_shares_never_returns_raw_tokens(app, client, auth_headers):
    with app.app_context():
        uid = _owner("share3@example.com")
    raw = _create_share(client, uid, auth_headers)["token"]

    listed = client.get(SHARES_URL, headers=auth_headers(uid)).get_json()["shares"]
    assert listed and all(raw not in str(s.values()) for s in listed)


# --- revocation & expiry ------------------------------------------------------

def test_revoked_link_returns_410(app, client, auth_headers):
    with app.app_context():
        uid = _owner("share4@example.com")
    share = _create_share(client, uid, auth_headers)
    assert client.get(f"/api/reports/shared/{share['token']}").status_code == 200

    assert client.delete(f"{SHARES_URL}/{share['id']}", headers=auth_headers(uid)).status_code == 200

    resp = client.get(f"/api/reports/shared/{share['token']}")
    assert resp.status_code == 410, resp.data[:200]
    assert resp.get_json()["status"] == "revoked"


def test_expired_link_returns_410(app, client, auth_headers):
    with app.app_context():
        uid = _owner("share5@example.com")
    share = _create_share(client, uid, auth_headers)

    with app.app_context():
        row = db.session.get(ReportShare, share["id"])
        row.expires_at = utc_naive_now() - timedelta(minutes=1)
        db.session.commit()

    resp = client.get(f"/api/reports/shared/{share['token']}")
    assert resp.status_code == 410, resp.data[:200]
    assert resp.get_json()["status"] == "expired"


def test_pdf_endpoint_honours_revocation_too(app, client, auth_headers):
    """The PDF route is a second public entry point — it must not outlive a revoke."""
    with app.app_context():
        uid = _owner("share6@example.com")
    share = _create_share(client, uid, auth_headers)
    client.delete(f"{SHARES_URL}/{share['id']}", headers=auth_headers(uid))

    assert client.get(f"/api/reports/shared/{share['token']}/pdf").status_code == 410


# --- rejection paths ----------------------------------------------------------

def test_garbage_and_short_tokens_return_404(app, client):
    assert client.get("/api/reports/shared/not-a-real-token-but-long-enough").status_code == 404
    assert client.get("/api/reports/shared/short").status_code == 404


def test_deactivated_owner_disables_the_link(app, client, auth_headers):
    """Disabling an account must take its public links down with it."""
    with app.app_context():
        uid = _owner("share7@example.com")
    share = _create_share(client, uid, auth_headers)
    assert client.get(f"/api/reports/shared/{share['token']}").status_code == 200

    with app.app_context():
        db.session.get(User, uid).is_active = False
        db.session.commit()

    resp = client.get(f"/api/reports/shared/{share['token']}")
    assert resp.status_code == 404, resp.data[:200]


def test_another_user_cannot_revoke_your_share(app, client, auth_headers):
    with app.app_context():
        owner = _owner("share8@example.com")
        attacker = _owner("share9@example.com")
    share = _create_share(client, owner, auth_headers)

    assert client.delete(f"{SHARES_URL}/{share['id']}",
                         headers=auth_headers(attacker)).status_code == 404
    # Still live for the real owner.
    assert client.get(f"/api/reports/shared/{share['token']}").status_code == 200


def test_creating_a_share_requires_authentication(app, client):
    assert client.post(SHARES_URL, json={"period": "current_month"}).status_code == 401

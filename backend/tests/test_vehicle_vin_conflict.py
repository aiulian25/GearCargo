"""R1: duplicate / cleared VIN must not 500.

`Vehicle.vin` is UNIQUE, but create and update committed bare — a duplicate VIN
(including another user's, since the constraint is global) surfaced as an
unhandled 500, which also made the crash a cross-tenant "does this VIN exist?"
oracle. Update additionally skipped create's `'' -> None` coercion, so two
vehicles whose VIN was *cleared* via PUT both stored '' and collided.
"""

from app import db
from app.models import User
from app.models.vehicle import Vehicle

VIN = "WVWZZZ1JZXW000001"


def _user(email):
    u = User(username=email.split("@")[0], email=email, is_active=True)
    u.set_password("StrongPass123!")
    db.session.add(u)
    db.session.commit()
    return u.id


def _vehicle(client, uid, auth_headers, **payload):
    return client.post("/api/vehicles", json={"name": "Car", **payload},
                       headers=auth_headers(uid))


def test_duplicate_vin_same_user_returns_409(app, client, auth_headers):
    with app.app_context():
        uid = _user("vin1@example.com")

    assert _vehicle(client, uid, auth_headers, vin=VIN).status_code == 201
    resp = _vehicle(client, uid, auth_headers, vin=VIN)

    assert resp.status_code == 409, resp.data[:200]          # was 500
    assert resp.get_json()["message_key"] == "vehicles.vinAlreadyExists"


def test_same_vin_allowed_for_a_different_user(app, client, auth_headers):
    """R1 (Step 3): uniqueness is PER USER. A car sold between two users of the
    same instance must be recordable by both — and one user must not be able to
    detect a VIN in another's garage."""
    with app.app_context():
        owner = _user("vin2@example.com")
        other = _user("vin3@example.com")

    assert _vehicle(client, owner, auth_headers, vin=VIN).status_code == 201
    resp = _vehicle(client, other, auth_headers, vin=VIN)
    assert resp.status_code == 201, resp.data[:200]      # was 409 (global unique)


def test_update_to_duplicate_vin_returns_409(app, client, auth_headers):
    with app.app_context():
        uid = _user("vin4@example.com")

    _vehicle(client, uid, auth_headers, vin=VIN)
    second = _vehicle(client, uid, auth_headers, name="Second").get_json()["vehicle"]["id"]

    resp = client.put(f"/api/vehicles/{second}", json={"vin": VIN}, headers=auth_headers(uid))
    assert resp.status_code == 409, resp.data[:200]
    assert resp.get_json()["message_key"] == "vehicles.vinAlreadyExists"


def test_clearing_vin_stores_null_not_empty_string(app, client, auth_headers):
    """Two cleared VINs must both become NULL (distinct under UNIQUE), not ''."""
    with app.app_context():
        uid = _user("vin5@example.com")

    a = _vehicle(client, uid, auth_headers, name="A", vin=VIN).get_json()["vehicle"]["id"]
    b = _vehicle(client, uid, auth_headers, name="B", vin="WVWZZZ1JZXW000002").get_json()["vehicle"]["id"]

    assert client.put(f"/api/vehicles/{a}", json={"vin": ""}, headers=auth_headers(uid)).status_code == 200
    # Second clear collided on '' before the fix.
    assert client.put(f"/api/vehicles/{b}", json={"vin": ""}, headers=auth_headers(uid)).status_code == 200

    with app.app_context():
        db.session.remove()
        assert db.session.get(Vehicle, a).vin is None
        assert db.session.get(Vehicle, b).vin is None


def test_vin_update_still_works(app, client, auth_headers):
    """Happy path unchanged: setting a fresh VIN persists."""
    with app.app_context():
        uid = _user("vin6@example.com")

    vid = _vehicle(client, uid, auth_headers).get_json()["vehicle"]["id"]
    assert client.put(f"/api/vehicles/{vid}", json={"vin": VIN},
                      headers=auth_headers(uid)).status_code == 200

    with app.app_context():
        db.session.remove()
        assert db.session.get(Vehicle, vid).vin == VIN

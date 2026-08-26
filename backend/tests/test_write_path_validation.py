"""R2: identity/vehicle write paths must reject bad input with 4xx, not 500.

`username` (80), `first_name`/`last_name` (50) and `email` (120) are
length-limited columns and `current_mileage` is an int, but the values went in
unvalidated: on Postgres that is a DataError/TypeError -> 500. SQLite accepts
over-long strings happily, which is exactly why the suite never caught it — so
these tests assert the STATUS CODE, which is engine-independent.
"""

from app import db
from app.models import User
from app.models.vehicle import Vehicle

PASSWORD = "StrongPass123!"


def _register(client, **payload):
    body = {"email": "new@example.com", "password": PASSWORD}
    body.update(payload)
    return client.post("/api/auth/register", json=body)


def _user(email="w@example.com"):
    u = User(username=email.split("@")[0], email=email, is_active=True)
    u.set_password(PASSWORD)
    db.session.add(u)
    db.session.commit()
    return u.id


# --- register -----------------------------------------------------------------

def test_register_rejects_malformed_email(app, client):
    resp = _register(client, email="not-an-email")
    assert resp.status_code == 400, resp.data[:150]
    assert resp.get_json()["message_key"] == "validation.invalidEmail"


def test_register_rejects_overlong_username(app, client):
    resp = _register(client, username="u" * 81)
    assert resp.status_code == 400, resp.data[:150]
    body = resp.get_json()
    assert body["message_key"] == "validation.maxLength"
    assert body["max_length"] == 80 and body["field"] == "username"


def test_register_rejects_overlong_name(app, client):
    resp = _register(client, first_name="f" * 51)
    assert resp.status_code == 400, resp.data[:150]
    assert resp.get_json()["field"] == "first_name"


def test_register_duplicate_username_returns_409(app, client):
    """The pre-check only covers email, so a taken *username* hit the DB
    constraint and 500'd."""
    with app.app_context():
        _user("taken@example.com")          # username -> 'taken'

    resp = _register(client, email="other@example.com", username="taken")
    assert resp.status_code == 409, resp.data[:150]
    assert resp.get_json()["message_key"] == "auth.usernameOrEmailTaken"


# --- update_profile -----------------------------------------------------------

def test_update_profile_rejects_malformed_email(app, client, auth_headers):
    with app.app_context():
        uid = _user("p1@example.com")

    resp = client.put("/api/auth/me",
                      json={"email": "bogus", "current_password": PASSWORD},
                      headers=auth_headers(uid))
    assert resp.status_code == 400, resp.data[:150]
    assert resp.get_json()["message_key"] == "validation.invalidEmail"


def test_update_profile_rejects_overlong_name(app, client, auth_headers):
    with app.app_context():
        uid = _user("p2@example.com")

    resp = client.put("/api/auth/me",
                      json={"name": "n" * 60, "current_password": PASSWORD},
                      headers=auth_headers(uid))
    assert resp.status_code == 400, resp.data[:150]
    assert resp.get_json()["message_key"] == "validation.maxLength"


def test_update_profile_still_accepts_valid_values(app, client, auth_headers):
    with app.app_context():
        uid = _user("p3@example.com")

    resp = client.put("/api/auth/me",
                      json={"name": "Jane Doe", "current_password": PASSWORD},
                      headers=auth_headers(uid))
    assert resp.status_code == 200, resp.get_json()


# --- vehicles -----------------------------------------------------------------

def test_update_vehicle_rejects_non_numeric_mileage(app, client, auth_headers):
    with app.app_context():
        uid = _user("v1@example.com")
        v = Vehicle(user_id=uid, name="Car")
        db.session.add(v)
        db.session.commit()
        vid = v.id

    resp = client.put(f"/api/vehicles/{vid}", json={"current_mileage": "abc"},
                      headers=auth_headers(uid))
    assert resp.status_code == 400, resp.data[:150]
    assert resp.get_json()["message_key"] == "validation.invalidNumber"


def test_update_vehicle_accepts_numeric_string_mileage(app, client, auth_headers):
    """A numeric string is coerced rather than rejected — forms send strings."""
    with app.app_context():
        uid = _user("v2@example.com")
        v = Vehicle(user_id=uid, name="Car")
        db.session.add(v)
        db.session.commit()
        vid = v.id

    resp = client.put(f"/api/vehicles/{vid}", json={"current_mileage": "5000"},
                      headers=auth_headers(uid))
    assert resp.status_code == 200, resp.data[:150]
    with app.app_context():
        db.session.remove()
        assert db.session.get(Vehicle, vid).current_mileage == 5000


def test_create_vehicle_rejects_bad_purchase_date(app, client, auth_headers):
    with app.app_context():
        uid = _user("v3@example.com")

    resp = client.post("/api/vehicles", json={"name": "Car", "purchase_date": "31/12/2026"},
                       headers=auth_headers(uid))
    assert resp.status_code == 400, resp.data[:150]
    assert resp.get_json()["message_key"] == "validation.invalidDate"


def test_update_vehicle_rejects_bad_purchase_date(app, client, auth_headers):
    with app.app_context():
        uid = _user("v4@example.com")
        v = Vehicle(user_id=uid, name="Car")
        db.session.add(v)
        db.session.commit()
        vid = v.id

    resp = client.put(f"/api/vehicles/{vid}", json={"purchase_date": "not-a-date"},
                      headers=auth_headers(uid))
    assert resp.status_code == 400, resp.data[:150]
    assert resp.get_json()["message_key"] == "validation.invalidDate"

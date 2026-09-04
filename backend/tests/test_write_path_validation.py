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


# --- R4-31/32/33: the last unguarded write paths ------------------------------
#
# Same class as everything above: values from a form or an admin panel reaching
# int()/fromisoformat()/a length-limited column with no coercion, so junk is a
# 500 rather than a 400 the UI can render.

import pytest

from app.models.attachment import Attachment


def _admin(email="wadmin@example.com"):
    user = User(username=email.split("@")[0], email=email, is_active=True,
                is_admin=True)
    user.set_password(PASSWORD)
    db.session.add(user)
    db.session.commit()
    return user.id


# --- reports (R4-31) ---

@pytest.mark.parametrize("payload", [
    {"period": "custom", "year": "2026", "month": "not-a-month"},
    {"period": "custom", "year": "not-a-year", "month": 6},
    {"period": "custom", "year": 2026, "month": {}},
])
def test_report_rejects_a_non_numeric_year_or_month(app, client, auth_headers, payload):
    with app.app_context():
        user_id = _user("rep1@example.com")
        db.session.add(Vehicle(user_id=user_id, name="Car"))
        db.session.commit()

    response = client.post("/api/reports/generate", json=payload,
                           headers=auth_headers(user_id))

    assert response.status_code == 400, response.data[:200]   # was: TypeError 500
    assert response.get_json()["message_key"] == "validation.invalidNumber"


def test_report_still_rejects_a_month_outside_the_year(app, client, auth_headers):
    with app.app_context():
        user_id = _user("rep2@example.com")
        db.session.add(Vehicle(user_id=user_id, name="Car"))
        db.session.commit()

    response = client.post("/api/reports/generate",
                           json={"period": "custom", "year": 2026, "month": 13},
                           headers=auth_headers(user_id))

    assert response.status_code == 400
    assert "Month" in response.get_json()["error"]


def test_report_never_includes_another_users_vehicle(app, client, auth_headers):
    """The inline resolution is gone; _resolve_report_vehicles enforces ownership."""
    with app.app_context():
        user_id = _user("rep3@example.com")
        db.session.add(Vehicle(user_id=user_id, name="Mine"))
        stranger_id = _user("rep4@example.com")
        stranger_vehicle = Vehicle(user_id=stranger_id, name="Theirs")
        db.session.add(stranger_vehicle)
        db.session.commit()
        stranger_vehicle_id = stranger_vehicle.id

    response = client.post("/api/reports/generate",
                           json={"vehicle_ids": [stranger_vehicle_id]},
                           headers=auth_headers(user_id))

    assert response.status_code == 404          # none of them are the caller's
    assert b"Theirs" not in response.data


# --- admin (R4-32) ---

@pytest.mark.parametrize("limit", ["abc", {}, "3.5.1"])
def test_admin_create_user_rejects_a_non_numeric_vehicle_limit(app, client, auth_headers, limit):
    with app.app_context():
        admin_id = _admin("wadmin1@example.com")

    response = client.post("/api/admin/users",
                           json={"email": "made@example.com", "password": PASSWORD,
                                 "vehicle_limit": limit},
                           headers=auth_headers(admin_id, is_admin=True))

    assert response.status_code == 400, response.data[:200]   # was: ValueError 500
    assert response.get_json()["message_key"] == "validation.invalidNumber"


def test_admin_update_user_rejects_a_non_numeric_vehicle_limit(app, client, auth_headers):
    with app.app_context():
        admin_id = _admin("wadmin2@example.com")
        target_id = _user("target@example.com")

    response = client.put(f"/api/admin/users/{target_id}",
                          json={"vehicle_limit": "abc"},
                          headers=auth_headers(admin_id, is_admin=True))

    assert response.status_code == 400, response.data[:200]
    assert response.get_json()["message_key"] == "validation.invalidNumber"


def test_admin_block_ip_rejects_a_non_numeric_expiry(app, client, auth_headers):
    with app.app_context():
        admin_id = _admin("wadmin3@example.com")

    response = client.post("/api/admin/blocked/ip",
                           json={"ip_address": "203.0.113.9", "expires_hours": "soon"},
                           headers=auth_headers(admin_id, is_admin=True))

    assert response.status_code == 400, response.data[:200]   # was: TypeError 500
    assert response.get_json()["message_key"] == "validation.invalidNumber"


def test_admin_block_ip_still_works_with_a_numeric_expiry(app, client, auth_headers):
    with app.app_context():
        admin_id = _admin("wadmin4@example.com")

    response = client.post("/api/admin/blocked/ip",
                           json={"ip_address": "203.0.113.10", "expires_hours": "24"},
                           headers=auth_headers(admin_id, is_admin=True))

    assert response.status_code in (200, 201), response.data[:200]


# --- attachments (R4-33) ---

def _attachment(user_id):
    attachment = Attachment(user_id=user_id, filename="doc.pdf",
                            filepath="/tmp/doc.pdf", file_type="application/pdf",
                            file_size=10, category="document")
    db.session.add(attachment)
    db.session.commit()
    return attachment.id


def test_attachment_rejects_a_malformed_expiry(app, client, auth_headers):
    with app.app_context():
        user_id = _user("att1@example.com")
        attachment_id = _attachment(user_id)

    response = client.put(f"/api/attachments/{attachment_id}",
                          json={"expires_at": "31/12/2026"},
                          headers=auth_headers(user_id))

    assert response.status_code == 400, response.data[:200]   # was: ValueError 500
    assert response.get_json()["message_key"] == "validation.invalidDate"


def test_attachment_still_accepts_and_clears_a_valid_expiry(app, client, auth_headers):
    with app.app_context():
        user_id = _user("att2@example.com")
        attachment_id = _attachment(user_id)

    assert client.put(f"/api/attachments/{attachment_id}",
                      json={"expires_at": "2026-12-31"},
                      headers=auth_headers(user_id)).status_code == 200
    with app.app_context():
        assert db.session.get(Attachment, attachment_id).expires_at is not None

    assert client.put(f"/api/attachments/{attachment_id}",
                      json={"expires_at": None},
                      headers=auth_headers(user_id)).status_code == 200
    with app.app_context():
        assert db.session.get(Attachment, attachment_id).expires_at is None


@pytest.mark.parametrize("category", ["../../etc/passwd", "x" * 80, "not-a-category"])
def test_attachment_rejects_an_unknown_category(app, client, auth_headers, category):
    with app.app_context():
        user_id = _user(f"att-{abs(hash(category)) % 9999}@example.com")
        attachment_id = _attachment(user_id)

    response = client.put(f"/api/attachments/{attachment_id}",
                          json={"category": category},
                          headers=auth_headers(user_id))

    assert response.status_code == 400, response.data[:200]
    with app.app_context():
        assert db.session.get(Attachment, attachment_id).category == "document"


@pytest.mark.parametrize("category", [
    "receipt", "invoice", "insurance", "insurance_document", "registration",
    "maintenance", "warranty", "photo", "document", "manual", "other",
])
def test_every_category_the_frontend_sends_is_accepted(app, client, auth_headers, category):
    """The allow-list must cover both selects AND the insurance_document value
    the upload route uses to route insurance attachments."""
    with app.app_context():
        user_id = _user(f"cat-{category}@example.com")
        attachment_id = _attachment(user_id)

    response = client.put(f"/api/attachments/{attachment_id}",
                          json={"category": category},
                          headers=auth_headers(user_id))

    assert response.status_code == 200, response.data[:200]
    with app.app_context():
        assert db.session.get(Attachment, attachment_id).category == category

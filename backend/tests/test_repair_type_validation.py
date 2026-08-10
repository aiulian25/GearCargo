"""Regression tests for L10: repair-type validation must apply on UPDATE, not
just create.

PUT previously accepted arbitrary `repair_types` that POST rejects, corrupting
by_type stats and the health endpoint's REPAIR_TYPE_TO_COMPONENTS matching.
`update_repair_entry` now filters against the module-level VALID_REPAIR_TYPES and
returns 400 when a selection is sent but nothing valid remains.
"""

from datetime import date

from app import db
from app.models import User
from app.models.vehicle import Vehicle
from app.models.repair import RepairEntry

PASSWORD = "StrongPass123!"


def _seed():
    u = User(username="rep", email="rep@example.com", is_active=True)
    u.set_password(PASSWORD)
    db.session.add(u)
    db.session.commit()
    v = Vehicle(user_id=u.id, name="Rep Car")
    db.session.add(v)
    db.session.commit()
    e = RepairEntry(
        user_id=u.id, vehicle_id=v.id, date=date.today(), amount=100,
        repair_type="brakes", repair_types=["brakes"], severity="low",
    )
    db.session.add(e)
    db.session.commit()
    return u.id, e.id


def _types(app, eid):
    with app.app_context():
        db.session.remove()
        e = db.session.get(RepairEntry, eid)
        return e.repair_types, e.repair_type


def test_update_all_invalid_types_rejected(app, client, auth_headers):
    with app.app_context():
        uid, eid = _seed()

    resp = client.put(f"/api/repairs/{eid}", json={"repair_types": ["bogus"]},
                      headers=auth_headers(uid))
    assert resp.status_code == 400, resp.get_json()
    assert _types(app, eid) == (["brakes"], "brakes")  # unchanged


def test_update_filters_invalid_keeps_valid(app, client, auth_headers):
    with app.app_context():
        uid, eid = _seed()

    resp = client.put(f"/api/repairs/{eid}", json={"repair_types": ["suspension", "bogus"]},
                      headers=auth_headers(uid))
    assert resp.status_code == 200, resp.get_json()
    types, primary = _types(app, eid)
    assert types == ["suspension"]        # 'bogus' dropped
    assert primary == "suspension"


def test_update_multiple_valid_types_saved(app, client, auth_headers):
    with app.app_context():
        uid, eid = _seed()

    resp = client.put(f"/api/repairs/{eid}", json={"repair_types": ["brakes", "engine"]},
                      headers=auth_headers(uid))
    assert resp.status_code == 200, resp.get_json()
    assert _types(app, eid) == (["brakes", "engine"], "brakes")


def test_update_legacy_repair_type_invalid_rejected(app, client, auth_headers):
    """The legacy single `repair_type` field is validated too."""
    with app.app_context():
        uid, eid = _seed()

    resp = client.put(f"/api/repairs/{eid}", json={"repair_type": "bogus"},
                      headers=auth_headers(uid))
    assert resp.status_code == 400, resp.get_json()
    assert _types(app, eid) == (["brakes"], "brakes")


def test_update_without_types_leaves_them_unchanged(app, client, auth_headers):
    """Editing only other fields must not touch (or reject on) repair types."""
    with app.app_context():
        uid, eid = _seed()

    resp = client.put(f"/api/repairs/{eid}", json={"amount": 250, "notes": "x"},
                      headers=auth_headers(uid))
    assert resp.status_code == 200, resp.get_json()
    assert _types(app, eid) == (["brakes"], "brakes")

"""Regression test for L9: /reports/preview now dedups through the shared
_resolve_report_vehicles + _report_summary helpers (same numbers as the public
shared view) and merely adds an `id` to each vehicle.

Locks the fields the Settings.jsx preview actually reads (period_label,
vehicle_count, entry_counts, totals, currency) plus the added vehicle id.
"""

from app import db
from app.models import User
from app.models.vehicle import Vehicle


def _user_vehicle():
    u = User(username="rep", email="rep@example.com", is_active=True, currency="GBP")
    u.set_password("StrongPass123!")
    db.session.add(u)
    db.session.commit()
    v = Vehicle(user_id=u.id, name="Rep Car", make="VW", model="Golf")
    db.session.add(v)
    db.session.commit()
    return u.id, v.id


def test_preview_returns_consumed_shape_with_vehicle_id(app, client, auth_headers):
    with app.app_context():
        uid, vid = _user_vehicle()

    resp = client.post(
        "/api/reports/preview",
        json={"vehicle_ids": "all", "period": "current_month"},
        headers=auth_headers(uid),
    )
    assert resp.status_code == 200, resp.get_json()
    d = resp.get_json()
    # Fields the preview UI consumes
    for key in ("period_label", "vehicle_count", "entry_counts", "totals", "currency"):
        assert key in d, key
    assert d["vehicle_count"] == 1
    assert d["currency"] == "GBP"
    assert d["entry_counts"]["total"] == 0
    assert d["totals"]["grand_total"] == 0
    # L9: authenticated preview exposes the vehicle id (public view omits it)
    assert d["vehicles"][0]["id"] == vid


def test_preview_no_vehicles_returns_404(app, client, auth_headers):
    """A selection resolving to no owned vehicles → 404 (unchanged)."""
    with app.app_context():
        uid, _ = _user_vehicle()

    resp = client.post(
        "/api/reports/preview",
        json={"vehicle_ids": [999999], "period": "current_month"},
        headers=auth_headers(uid),
    )
    assert resp.status_code == 404, resp.get_json()

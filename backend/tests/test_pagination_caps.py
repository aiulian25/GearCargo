"""R3: list endpoints must clamp `per_page` (cap 100, floor 1).

`per_page` went straight into .paginate() uncapped, so ?per_page=10000000
serialised a user's whole table in one request — a memory/latency DoS on the
1 GB single-container deployment. A negative value reached paginate() too.
"""

from datetime import date, timedelta

from app import db
from app.models import User
from app.models.fuel import FuelEntry
from app.models.vehicle import Vehicle

# Every list endpoint clamped in this pass (all default page 1).
LIST_URLS = [
    "/api/fuel", "/api/services", "/api/repairs", "/api/taxes",
    "/api/parking", "/api/consumables", "/api/reminders",
    "/api/insurance", "/api/todos", "/api/attachments",
    "/api/backup/history",
]


def _user_with_fuel(n):
    u = User(username="pag", email="pag@example.com", is_active=True)
    u.set_password("StrongPass123!")
    db.session.add(u)
    db.session.commit()
    v = Vehicle(user_id=u.id, name="Pager")
    db.session.add(v)
    db.session.commit()
    db.session.add_all([
        FuelEntry(user_id=u.id, vehicle_id=v.id, date=date(2026, 1, 1) + timedelta(days=i),
                  amount=10, total_price=10, liters=5)
        for i in range(n)
    ])
    db.session.commit()
    return u.id


def test_huge_per_page_is_capped_at_100(app, client, auth_headers):
    """101 rows + ?per_page=999999 → 100 returned (was: all 101)."""
    with app.app_context():
        uid = _user_with_fuel(101)

    body = client.get("/api/fuel?per_page=999999", headers=auth_headers(uid)).get_json()
    assert len(body["entries"]) == 100
    assert body["pages"] == 2          # 101 rows / 100 per page — not 1


def test_default_per_page_unchanged(app, client, auth_headers):
    """The clamp must not shrink the existing default (fuel: 20)."""
    with app.app_context():
        uid = _user_with_fuel(101)

    body = client.get("/api/fuel", headers=auth_headers(uid)).get_json()
    assert len(body["entries"]) == 20


def test_all_list_endpoints_survive_hostile_per_page(app, client, auth_headers):
    """Negative / zero / garbage must not 500 on any clamped endpoint."""
    with app.app_context():
        uid = _user_with_fuel(1)
    headers = auth_headers(uid)

    for url in LIST_URLS:
        for value in ("-5", "0", "abc"):
            resp = client.get(f"{url}?per_page={value}", headers=headers)
            assert resp.status_code == 200, (url, value, resp.status_code, resp.data[:120])

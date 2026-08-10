"""Equivalence tests for M9: the /stats endpoints are being moved from
`query.all()` + Python loops to DB aggregation. These lock the EXACT response
shape and values on seeded data, so the refactor cannot change behaviour.

Each test asserts hand-computed expected values that match the CURRENT
implementation; they must pass both before and after the refactor. Edge cases
are deliberately exercised: null type → 'other'/'custom'/'medium', JSON
`repair_types` multi-type expansion, per-year tax grouping, insurance
active/expiring (date-based properties), reminder overdue, and attachment
image/pdf/document classification.
"""

from datetime import date, timedelta

import pytest

from app import db
from app.models import User
from app.models.vehicle import Vehicle
from app.models.fuel import FuelEntry
from app.models.service import ServiceEntry
from app.models.repair import RepairEntry
from app.models.tax import TaxEntry
from app.models.parking import ParkingEntry
from app.models.insurance import InsurancePolicy
from app.models.reminder import Reminder
from app.models.attachment import Attachment

TODAY = date.today()


def _mk(currency="GBP"):
    u = User(username="statsu", email="stats@example.com", is_active=True, currency=currency)
    u.set_password("StrongPass123!")
    db.session.add(u)
    db.session.commit()
    v = Vehicle(user_id=u.id, name="Stats Car")
    db.session.add(v)
    db.session.commit()
    return u.id, v.id


def test_fuel_stats(app, client, auth_headers):
    with app.app_context():
        uid, vid = _mk(currency="GBP")
        db.session.add_all([
            FuelEntry(user_id=uid, vehicle_id=vid, currency="GBP", total_price=50,
                      liters=40, fuel_efficiency=8.0, price_per_liter=1.25, date=TODAY),
            FuelEntry(user_id=uid, vehicle_id=vid, currency="GBP", total_price=30,
                      liters=20, fuel_efficiency=None, price_per_liter=None, date=TODAY),
        ])
        db.session.commit()

    r = client.get("/api/fuel/stats", headers=auth_headers(uid))
    assert r.status_code == 200
    d = r.get_json()
    assert d["total_cost"] == pytest.approx(80.0)
    assert d["total_liters"] == pytest.approx(60.0)
    assert d["entry_count"] == 2
    assert d["avg_efficiency"] == pytest.approx(8.0)      # only the truthy one
    assert d["avg_price_per_liter"] == pytest.approx(1.25)
    assert d["display_currency"] == "GBP"
    assert d["converted"] is True
    assert d["fx_applied"] is False


def test_service_stats(app, client, auth_headers):
    with app.app_context():
        uid, vid = _mk()
        db.session.add_all([
            ServiceEntry(user_id=uid, vehicle_id=vid, service_type="oil_change",
                         amount=100, labor_cost=40, parts_cost=60, date=TODAY),
            ServiceEntry(user_id=uid, vehicle_id=vid, service_type="oil_change",
                         amount=50, labor_cost=20, parts_cost=30, date=TODAY),
            ServiceEntry(user_id=uid, vehicle_id=vid, service_type=None,
                         amount=25, labor_cost=0, parts_cost=0, date=TODAY),
        ])
        db.session.commit()

    d = client.get("/api/services/stats", headers=auth_headers(uid)).get_json()
    assert d["total_cost"] == pytest.approx(175.0)
    assert d["total_labor_cost"] == pytest.approx(60.0)
    assert d["total_parts_cost"] == pytest.approx(90.0)
    assert d["entry_count"] == 3
    assert d["by_type"] == {
        "oil_change": {"count": 2, "cost": 150.0},
        "other": {"count": 1, "cost": 25.0},
    }


def test_repair_stats(app, client, auth_headers):
    with app.app_context():
        uid, vid = _mk()
        db.session.add_all([
            RepairEntry(user_id=uid, vehicle_id=vid, repair_types=["brakes", "suspension"],
                        amount=200, severity="high", under_warranty=False, date=TODAY),
            RepairEntry(user_id=uid, vehicle_id=vid, repair_types=["brakes"],
                        amount=100, severity="low", under_warranty=True, date=TODAY),
            RepairEntry(user_id=uid, vehicle_id=vid, repair_type="engine", repair_types=None,
                        amount=50, severity="unknownsev", under_warranty=False, date=TODAY),
            RepairEntry(user_id=uid, vehicle_id=vid, repair_type=None, repair_types=None,
                        amount=10, severity=None, under_warranty=False, date=TODAY),
        ])
        db.session.commit()

    d = client.get("/api/repairs/stats", headers=auth_headers(uid)).get_json()
    assert d["total_cost"] == pytest.approx(360.0)
    assert d["entry_count"] == 4
    assert d["warranty_savings"] == pytest.approx(100.0)
    assert d["insurance_claims"] == pytest.approx(0.0)
    # unknown severity is dropped; None → 'medium'
    assert d["by_severity"] == {"low": 1, "medium": 1, "high": 1, "critical": 0}
    assert d["by_type"] == {
        "brakes": {"count": 2, "cost": 300.0},
        "suspension": {"count": 1, "cost": 200.0},
        "engine": {"count": 1, "cost": 50.0},
        "other": {"count": 1, "cost": 10.0},
    }


def test_tax_stats(app, client, auth_headers):
    with app.app_context():
        uid, vid = _mk()
        db.session.add_all([
            TaxEntry(user_id=uid, vehicle_id=vid, tax_type="road_tax", amount=150, date=date(2023, 5, 1)),
            TaxEntry(user_id=uid, vehicle_id=vid, tax_type="road_tax", amount=160, date=date(2024, 5, 1)),
            TaxEntry(user_id=uid, vehicle_id=vid, tax_type=None, amount=40, date=date(2024, 1, 1)),
        ])
        db.session.commit()

    d = client.get("/api/taxes/stats", headers=auth_headers(uid)).get_json()
    assert d["total_cost"] == pytest.approx(350.0)
    assert d["entry_count"] == 3
    assert d["by_type"] == {
        "road_tax": {"count": 2, "cost": 310.0},
        "other": {"count": 1, "cost": 40.0},
    }
    # JSON object keys are strings
    assert d["yearly_breakdown"] == {"2023": 150.0, "2024": 200.0}


def test_parking_stats(app, client, auth_headers):
    with app.app_context():
        uid, vid = _mk()
        db.session.add_all([
            ParkingEntry(user_id=uid, vehicle_id=vid, parking_type="street", amount=5,
                         duration_minutes=60, location="Downtown", date=TODAY),
            ParkingEntry(user_id=uid, vehicle_id=vid, parking_type="street", amount=3,
                         duration_minutes=30, location="Downtown", date=TODAY),
            ParkingEntry(user_id=uid, vehicle_id=vid, parking_type="garage", amount=10,
                         duration_minutes=120, location="Mall", date=TODAY),
            ParkingEntry(user_id=uid, vehicle_id=vid, parking_type=None, amount=2,
                         duration_minutes=None, location=None, date=TODAY),
        ])
        db.session.commit()

    d = client.get("/api/parking/stats", headers=auth_headers(uid)).get_json()
    assert d["total_cost"] == pytest.approx(20.0)
    assert d["total_duration_minutes"] == 210
    assert d["entry_count"] == 4
    assert d["by_type"] == {
        "street": {"count": 2, "cost": 8.0, "duration": 90},
        "garage": {"count": 1, "cost": 10.0, "duration": 120},
        "other": {"count": 1, "cost": 2.0, "duration": 0},
    }
    assert d["top_locations"] == {
        "Downtown": {"count": 2, "cost": 8.0},
        "Mall": {"count": 1, "cost": 10.0},
        "Unknown": {"count": 1, "cost": 2.0},
    }


def test_insurance_stats(app, client, auth_headers):
    with app.app_context():
        uid, vid = _mk()
        db.session.add_all([
            InsurancePolicy(user_id=uid, vehicle_id=vid, provider="Acme", policy_type="auto",
                            premium=1200, status="active",
                            start_date=TODAY - timedelta(days=100), end_date=TODAY + timedelta(days=100)),
            InsurancePolicy(user_id=uid, vehicle_id=vid, provider="Beta", policy_type="auto",
                            premium=600, status="active",
                            start_date=TODAY - timedelta(days=10), end_date=TODAY + timedelta(days=15)),
            InsurancePolicy(user_id=uid, vehicle_id=vid, provider="Acme", policy_type="home",
                            premium=300, status="active",
                            start_date=TODAY - timedelta(days=400), end_date=TODAY - timedelta(days=40)),
            InsurancePolicy(user_id=uid, vehicle_id=vid, provider="Acme", policy_type="auto",
                            premium=999, status="cancelled",
                            start_date=TODAY - timedelta(days=10), end_date=TODAY + timedelta(days=200)),
        ])
        db.session.commit()

    d = client.get("/api/insurance/stats", headers=auth_headers(uid)).get_json()
    assert d["total_policies"] == 4
    assert d["active_policies"] == 2
    assert d["total_active_premium"] == pytest.approx(1800.0)
    assert d["expiring_soon"] == 1
    assert d["by_type"] == {
        "auto": {"count": 3, "active": 2, "premium": 1800.0},
        "home": {"count": 1, "active": 0, "premium": 0},
    }
    assert d["by_provider"] == {
        "Acme": {"count": 3, "active": 1},
        "Beta": {"count": 1, "active": 1},
    }


def test_reminder_stats(app, client, auth_headers):
    with app.app_context():
        uid, vid = _mk()
        db.session.add_all([
            Reminder(user_id=uid, vehicle_id=vid, title="a", reminder_type="maintenance",
                     completed=True, dismissed=False, due_date=TODAY - timedelta(days=5)),
            Reminder(user_id=uid, vehicle_id=vid, title="b", reminder_type="maintenance",
                     completed=False, dismissed=False, due_date=TODAY + timedelta(days=5)),
            Reminder(user_id=uid, vehicle_id=vid, title="c", reminder_type="insurance",
                     completed=False, dismissed=False, due_date=TODAY - timedelta(days=3)),
            Reminder(user_id=uid, vehicle_id=vid, title="d", reminder_type=None,
                     completed=False, dismissed=True, due_date=TODAY - timedelta(days=10)),
        ])
        db.session.commit()

    d = client.get("/api/reminders/stats", headers=auth_headers(uid)).get_json()
    assert d["total"] == 4
    assert d["completed"] == 1
    assert d["pending"] == 2
    assert d["overdue"] == 1
    assert d["by_type"] == {
        "maintenance": {"total": 2, "pending": 1, "completed": 1},
        "insurance": {"total": 1, "pending": 1, "completed": 0},
        "custom": {"total": 1, "pending": 0, "completed": 0},
    }


def test_attachment_stats(app, client, auth_headers):
    with app.app_context():
        uid, vid = _mk()
        db.session.add_all([
            Attachment(user_id=uid, vehicle_id=vid, filename="a", filepath="/a",
                       file_type="image/png", file_size=1000, category="receipt"),
            Attachment(user_id=uid, vehicle_id=vid, filename="b", filepath="/b",
                       file_type="application/pdf", file_size=2000, category="receipt"),
            Attachment(user_id=uid, vehicle_id=vid, filename="c", filepath="/c",
                       file_type="application/document", file_size=500, category=None),
            Attachment(user_id=uid, vehicle_id=vid, filename="d", filepath="/d",
                       file_type="application/zip", file_size=300, category="misc"),
            Attachment(user_id=uid, vehicle_id=vid, filename="e", filepath="/e",
                       file_type=None, file_size=None, category=None),
        ])
        db.session.commit()

    d = client.get("/api/attachments/stats", headers=auth_headers(uid)).get_json()
    assert d["total_count"] == 5
    assert d["total_size"] == 3800
    assert d["total_size_human"] == "3.7 KB"
    assert d["by_category"] == {
        "receipt": {"count": 2, "size": 3000},
        "other": {"count": 2, "size": 500},
        "misc": {"count": 1, "size": 300},
    }
    assert d["by_type"] == {"images": 1, "pdfs": 1, "documents": 1, "other": 2}

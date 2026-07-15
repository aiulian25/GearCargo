"""Tests for F24 — cost of ownership in /cost-analytics.

The stored purchase_price has no currency column and is treated as already
being in the user's display currency (documented in the route), so rates are
pinned empty here — running costs are created in the display currency too.
"""

from datetime import date, timedelta

import pytest
from dateutil.relativedelta import relativedelta

from app import db
from app.models import User, Vehicle, FuelEntry

TODAY = date.today()


@pytest.fixture(autouse=True)
def _no_fx(monkeypatch):
    import app.routes.vehicles as vroutes
    monkeypatch.setattr(vroutes, 'get_rates_cached', lambda app: {})


def _mk_vehicle(user_id, **kwargs):
    v = Vehicle(user_id=user_id, name='Octavia', make='Skoda', model='Octavia', **kwargs)
    db.session.add(v)
    db.session.commit()
    db.session.refresh(v)
    return v


def test_ownership_totals_and_months(app, client, user, auth_headers):
    with app.app_context():
        u = db.session.get(User, user.id)
        u.currency = 'GBP'
        db.session.commit()
        v = _mk_vehicle(user.id,
                        purchase_price=10000,
                        purchase_date=TODAY - relativedelta(months=20))
        db.session.add(FuelEntry(user_id=user.id, vehicle_id=v.id,
                                 date=TODAY - timedelta(days=10), amount=500,
                                 total_price=500, currency='GBP',
                                 fuel_type='petrol'))
        db.session.commit()
        vid = v.id

    resp = client.get(f'/api/vehicles/{vid}/cost-analytics', headers=auth_headers(user.id))
    assert resp.status_code == 200
    own = resp.get_json()['ownership']

    assert own['purchase_price'] == 10000.0
    assert own['months_owned'] == 20
    assert own['total_with_purchase'] == 10500.0
    assert own['avg_monthly_ownership'] == round(10500.0 / 20, 2)
    # No odometer readings → no distance span → per-distance stays None.
    assert own['cost_per_distance_with_purchase'] is None


def test_ownership_per_distance_uses_odometer_span(app, client, user, auth_headers):
    with app.app_context():
        u = db.session.get(User, user.id)
        u.currency = 'GBP'
        db.session.commit()
        v = _mk_vehicle(user.id, purchase_price=9000)
        db.session.add(FuelEntry(user_id=user.id, vehicle_id=v.id,
                                 date=TODAY - timedelta(days=40), amount=400,
                                 total_price=400, currency='GBP',
                                 fuel_type='petrol', odometer=10000))
        db.session.add(FuelEntry(user_id=user.id, vehicle_id=v.id,
                                 date=TODAY - timedelta(days=5), amount=600,
                                 total_price=600, currency='GBP',
                                 fuel_type='petrol', odometer=12000))
        db.session.commit()
        vid = v.id

    own = client.get(f'/api/vehicles/{vid}/cost-analytics',
                     headers=auth_headers(user.id)).get_json()['ownership']
    # (9000 + 1000) / 2000 km span
    assert own['total_with_purchase'] == 10000.0
    assert own['cost_per_distance_with_purchase'] == 5.0
    # No purchase_date → months_owned / per-month stay None.
    assert own['months_owned'] is None
    assert own['avg_monthly_ownership'] is None


def test_ownership_is_null_without_purchase_price(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        db.session.add(FuelEntry(user_id=user.id, vehicle_id=v.id,
                                 date=TODAY - timedelta(days=3), amount=50,
                                 total_price=50, currency='GBP', fuel_type='petrol'))
        db.session.commit()
        vid = v.id

    body = client.get(f'/api/vehicles/{vid}/cost-analytics',
                      headers=auth_headers(user.id)).get_json()
    assert body['ownership'] is None

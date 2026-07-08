"""Tests for F1 — currency normalization (backend/app/services/currency.py +
the cost-analytics / summary endpoints).

Rates are patched to a fixed EUR-based dict so the tests are deterministic and
never touch the network.
"""

from datetime import date, timedelta

import pytest

from app import db
from app.models import User, Vehicle, FuelEntry, ServiceEntry
from app.services import currency as currency_svc


# EUR-based: "units of X per 1 EUR" (EUR itself is the base = 1.0, not a key).
FIXED_RATES = {'GBP': 0.86, 'USD': 1.08, 'RON': 5.0}


@pytest.fixture(autouse=True)
def _patch_rates(monkeypatch):
    """Force deterministic, offline rates for every test in this module."""
    monkeypatch.setattr(currency_svc, 'get_rates_cached', lambda app: dict(FIXED_RATES))
    # The route modules imported the symbol by name, so patch those bindings too.
    import app.routes.vehicles as vroutes
    monkeypatch.setattr(vroutes, 'get_rates_cached', lambda app: dict(FIXED_RATES))


def _mk_vehicle(user_id, name='Focus'):
    v = Vehicle(user_id=user_id, name=name, make='Ford', model='Focus')
    db.session.add(v)
    db.session.commit()
    db.session.refresh(v)
    return v


# --- Pure helper -----------------------------------------------------------

def test_to_display_same_currency_is_passthrough():
    amt, ok = currency_svc.to_display(100, 'GBP', 'GBP', FIXED_RATES)
    assert ok is True and amt == 100


def test_to_display_eur_to_gbp():
    amt, ok = currency_svc.to_display(100, 'EUR', 'GBP', FIXED_RATES)
    assert ok is True and round(amt, 2) == 86.00  # 100 EUR * 0.86


def test_to_display_usd_to_gbp_pivots_through_eur():
    amt, ok = currency_svc.to_display(100, 'USD', 'GBP', FIXED_RATES)
    # 100 USD -> EUR (/1.08) -> GBP (*0.86)
    assert ok is True and round(amt, 2) == round(100 / 1.08 * 0.86, 2)


def test_to_display_missing_rate_flags_unconverted():
    amt, ok = currency_svc.to_display(100, 'JPY', 'GBP', FIXED_RATES)
    assert ok is False and amt == 100  # returned unchanged, flagged


def test_sum_to_display_reports_fx_and_converted():
    total, converted, fx = currency_svc.sum_to_display(
        [('EUR', 100), ('USD', 100)], 'GBP', FIXED_RATES)
    assert converted is True and fx is True
    assert round(total, 2) == round(100 * 0.86 + 100 / 1.08 * 0.86, 2)


# --- Endpoint: cost-analytics ---------------------------------------------

def test_cost_analytics_converts_mixed_currencies_to_user_currency(app, client, user, auth_headers):
    """Acceptance: user.currency=GBP, EUR 100 + USD 100 -> single GBP total,
    display_currency='GBP', converted=True."""
    with app.app_context():
        u = db.session.get(User, user.id)
        u.currency = 'GBP'
        db.session.commit()
        v = _mk_vehicle(user.id)
        today = date.today()
        db.session.add(FuelEntry(user_id=user.id, vehicle_id=v.id,
                                 date=today - timedelta(days=3), amount=100,
                                 total_price=100, currency='EUR', fuel_type='petrol'))
        db.session.add(ServiceEntry(user_id=user.id, vehicle_id=v.id,
                                    date=today - timedelta(days=2), amount=100,
                                    currency='USD', title='Service'))
        db.session.commit()
        vid = v.id

    resp = client.get(f'/api/vehicles/{vid}/cost-analytics', headers=auth_headers(user.id))
    assert resp.status_code == 200
    data = resp.get_json()

    assert data['display_currency'] == 'GBP'
    assert data['currency'] == 'GBP'
    assert data['converted'] is True
    assert data['fx_applied'] is True
    expected = round(100 * 0.86 + 100 / 1.08 * 0.86, 2)
    assert data['total_cost'] == expected


def test_cost_analytics_flags_unconverted_when_rate_missing(app, client, user, auth_headers):
    with app.app_context():
        u = db.session.get(User, user.id)
        u.currency = 'GBP'
        db.session.commit()
        v = _mk_vehicle(user.id)
        today = date.today()
        # JPY has no rate in FIXED_RATES -> converted must be False.
        db.session.add(FuelEntry(user_id=user.id, vehicle_id=v.id,
                                 date=today - timedelta(days=1), amount=5000,
                                 total_price=5000, currency='JPY', fuel_type='petrol'))
        db.session.commit()
        vid = v.id

    resp = client.get(f'/api/vehicles/{vid}/cost-analytics', headers=auth_headers(user.id))
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['converted'] is False
    assert data['display_currency'] == 'GBP'


# --- Endpoint: fleet summary (also verifies the is_active->archived fix) ----

def test_summary_converts_and_ignores_archived(app, client, user, auth_headers):
    with app.app_context():
        u = db.session.get(User, user.id)
        u.currency = 'GBP'
        db.session.commit()
        v = _mk_vehicle(user.id)
        today = date.today()
        db.session.add(FuelEntry(user_id=user.id, vehicle_id=v.id,
                                 date=today - timedelta(days=1), amount=100,
                                 total_price=100, currency='EUR', fuel_type='petrol'))
        db.session.commit()
        vid = v.id

    resp = client.get('/api/vehicles/summary', headers=auth_headers(user.id))
    assert resp.status_code == 200  # would 500 before the is_active fix
    data = resp.get_json()
    assert data['display_currency'] == 'GBP'
    assert data['total_cost'] == round(100 * 0.86, 2)
    assert data['fx_applied'] is True

    # Archiving the only vehicle drops it from the summed total.
    with app.app_context():
        vv = db.session.get(Vehicle, vid)
        vv.archived = True
        db.session.commit()
    resp2 = client.get('/api/vehicles/summary', headers=auth_headers(user.id))
    assert resp2.status_code == 200
    assert resp2.get_json()['vehicle_count'] == 0

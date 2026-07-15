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
    import app.routes.fuel as froutes
    monkeypatch.setattr(vroutes, 'get_rates_cached', lambda app: dict(FIXED_RATES))
    monkeypatch.setattr(froutes, 'get_rates_cached', lambda app: dict(FIXED_RATES))


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


# --- Endpoint: per-vehicle stats + fuel stats (F28) --------------------------

def test_vehicle_stats_converts_mixed_fuel_currencies(app, client, user, auth_headers):
    """EUR 100 + GBP 50 fuel, display GBP -> fuel_costs = 100*0.86 + 50."""
    with app.app_context():
        u = db.session.get(User, user.id)
        u.currency = 'GBP'
        db.session.commit()
        v = _mk_vehicle(user.id)
        today = date.today()
        db.session.add(FuelEntry(user_id=user.id, vehicle_id=v.id,
                                 date=today - timedelta(days=3), amount=100,
                                 total_price=100, currency='EUR', fuel_type='petrol'))
        db.session.add(FuelEntry(user_id=user.id, vehicle_id=v.id,
                                 date=today - timedelta(days=1), amount=50,
                                 total_price=50, currency='GBP', fuel_type='petrol'))
        db.session.commit()
        vid = v.id

    resp = client.get(f'/api/vehicles/{vid}/stats', headers=auth_headers(user.id))
    assert resp.status_code == 200
    data = resp.get_json()

    assert data['display_currency'] == 'GBP'
    assert data['converted'] is True
    assert data['fx_applied'] is True
    expected = round(100 * 0.86 + 50, 2)
    assert round(data['fuel_costs'], 2) == expected
    assert round(data['total_costs'], 2) == expected  # only fuel entries exist


def test_vehicle_stats_matches_summary_conversion_basis(app, client, user, auth_headers):
    """Acceptance: stats.total_costs ≈ summary.total_cost for one vehicle."""
    with app.app_context():
        u = db.session.get(User, user.id)
        u.currency = 'GBP'
        db.session.commit()
        v = _mk_vehicle(user.id)
        today = date.today()
        db.session.add(FuelEntry(user_id=user.id, vehicle_id=v.id,
                                 date=today - timedelta(days=5), amount=700,
                                 total_price=700, currency='RON', fuel_type='diesel'))
        db.session.add(ServiceEntry(user_id=user.id, vehicle_id=v.id,
                                    date=today - timedelta(days=2), amount=50,
                                    currency='GBP', title='Service'))
        db.session.commit()
        vid = v.id

    stats = client.get(f'/api/vehicles/{vid}/stats',
                       headers=auth_headers(user.id)).get_json()
    summary = client.get('/api/vehicles/summary',
                         headers=auth_headers(user.id)).get_json()

    # 700 RON -> EUR (/5.0) -> GBP (*0.86) = 120.40, + 50 GBP
    expected = round(700 / 5.0 * 0.86 + 50, 2)
    assert round(stats['total_costs'], 2) == expected
    assert round(summary['total_cost'], 2) == expected


def test_vehicle_stats_converts_insurance_premiums(app, client, user, auth_headers):
    from app.models import InsurancePolicy
    with app.app_context():
        u = db.session.get(User, user.id)
        u.currency = 'GBP'
        db.session.commit()
        v = _mk_vehicle(user.id)
        today = date.today()
        db.session.add(InsurancePolicy(
            user_id=user.id, vehicle_id=v.id, provider='Acme', status='active',
            premium=108, currency='USD', payment_frequency='annual',
            start_date=today - timedelta(days=30),
            end_date=today + timedelta(days=335)))
        db.session.commit()
        vid = v.id

    data = client.get(f'/api/vehicles/{vid}/stats',
                      headers=auth_headers(user.id)).get_json()
    # 108 USD -> EUR (/1.08) -> GBP (*0.86) = 86.00 annualized
    assert round(data['insurance_annual_cost'], 2) == 86.00
    assert data['fx_applied'] is True


def test_fuel_stats_converts_cost_but_not_volume(app, client, user, auth_headers):
    with app.app_context():
        u = db.session.get(User, user.id)
        u.currency = 'GBP'
        db.session.commit()
        v = _mk_vehicle(user.id)
        today = date.today()
        db.session.add(FuelEntry(user_id=user.id, vehicle_id=v.id,
                                 date=today - timedelta(days=3), amount=100,
                                 total_price=100, liters=40,
                                 currency='EUR', fuel_type='petrol'))
        db.session.add(FuelEntry(user_id=user.id, vehicle_id=v.id,
                                 date=today - timedelta(days=1), amount=50,
                                 total_price=50, liters=20,
                                 currency='GBP', fuel_type='petrol'))
        db.session.commit()
        vid = v.id

    resp = client.get(f'/api/fuel/stats?vehicle_id={vid}', headers=auth_headers(user.id))
    assert resp.status_code == 200
    data = resp.get_json()
    assert round(data['total_cost'], 2) == round(100 * 0.86 + 50, 2)
    assert data['total_liters'] == 60.0          # unit-based, no FX
    assert data['display_currency'] == 'GBP'
    assert data['converted'] is True
    assert data['fx_applied'] is True


def test_fuel_stats_empty_keeps_stable_shape(client, user, auth_headers):
    resp = client.get('/api/fuel/stats?vehicle_id=999999', headers=auth_headers(user.id))
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['total_cost'] == 0
    assert data['converted'] is True and data['fx_applied'] is False

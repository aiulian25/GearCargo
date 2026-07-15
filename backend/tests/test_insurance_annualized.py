"""Tests for F12 — annualize insurance premiums in analytics (payment_frequency)."""

from datetime import date, timedelta

import pytest

from app import db
from app.models import User, Vehicle
from app.models.insurance import InsurancePolicy

TODAY = date.today()


@pytest.fixture(autouse=True)
def _no_fx(monkeypatch):
    """These tests exercise F12 frequency math, not F28 FX conversion — pin
    rates to empty (offline, deterministic); policies are created in GBP,
    the test user's display currency, so conversion is a no-op anyway."""
    import app.routes.vehicles as vroutes
    monkeypatch.setattr(vroutes, 'get_rates_cached', lambda app: {})


def _mk_vehicle(user_id, name='Focus'):
    v = Vehicle(user_id=user_id, name=name, make='Ford', model='Focus')
    db.session.add(v)
    db.session.commit()
    db.session.refresh(v)
    return v


def _mk_policy(user_id, vehicle_id, premium, frequency):
    p = InsurancePolicy(
        user_id=user_id, vehicle_id=vehicle_id, provider='Aviva',
        policy_number='POL', premium=premium, payment_frequency=frequency,
        currency='GBP', status='active', start_date=TODAY - timedelta(days=30),
        end_date=TODAY + timedelta(days=335))
    db.session.add(p)
    db.session.commit()
    return p


def test_annualized_premium_property(app):
    with app.app_context():
        u = User(email='a@ex.com', username='a', is_active=True)
        u.set_password('Str0ng!Passw0rd')
        db.session.add(u)
        db.session.commit()
        v = _mk_vehicle(u.id)

        assert _mk_policy(u.id, v.id, 100, 'monthly').annualized_premium == 1200.0
        assert _mk_policy(u.id, v.id, 300, 'quarterly').annualized_premium == 1200.0
        assert _mk_policy(u.id, v.id, 600, 'semi_annual').annualized_premium == 1200.0
        assert _mk_policy(u.id, v.id, 600, 'semi-annual').annualized_premium == 1200.0
        assert _mk_policy(u.id, v.id, 1200, 'annual').annualized_premium == 1200.0
        # Unknown/blank frequency → treated as annual.
        assert _mk_policy(u.id, v.id, 1200, None).annualized_premium == 1200.0


def test_monthly_and_annual_contribute_equal_annual_cost(app, client, user, auth_headers):
    """A €100/mo policy and a €1,200/yr policy contribute the same annual cost."""
    with app.app_context():
        v_month = _mk_vehicle(user.id, 'Monthly')
        v_year = _mk_vehicle(user.id, 'Annual')
        _mk_policy(user.id, v_month.id, 100, 'monthly')
        _mk_policy(user.id, v_year.id, 1200, 'annual')
        mid, yid = v_month.id, v_year.id

    m = client.get(f'/api/vehicles/{mid}/stats', headers=auth_headers(user.id)).get_json()
    y = client.get(f'/api/vehicles/{yid}/stats', headers=auth_headers(user.id)).get_json()
    assert m['insurance_annual_cost'] == 1200.0
    assert y['insurance_annual_cost'] == 1200.0
    assert m['insurance_annual_cost'] == y['insurance_annual_cost']


def test_to_dict_exposes_annualized_premium(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        _mk_policy(user.id, v.id, 100, 'monthly')

    resp = client.get('/api/insurance', headers=auth_headers(user.id))
    assert resp.status_code == 200
    policies = resp.get_json()['policies']
    assert policies[0]['annualized_premium'] == 1200.0
    assert policies[0]['payment_frequency'] == 'monthly'

"""Tests for F11 — 12-month forward cost forecast."""

from datetime import date

from dateutil.relativedelta import relativedelta

from app import db
from app.models import User, Vehicle, TaxEntry
from app.models.insurance import InsurancePolicy
from app.models.prediction import PredictionAlert

FIRST = date.today().replace(day=1)


def _mk_vehicle(user_id, name='Focus', budget=None):
    v = Vehicle(user_id=user_id, name=name, make='Ford', model='Focus',
                monthly_budget=budget)
    db.session.add(v)
    db.session.commit()
    db.session.refresh(v)
    return v


def _mk_recurring_tax(user_id, vehicle_id, amount, currency='GBP'):
    t = TaxEntry(user_id=user_id, vehicle_id=vehicle_id, date=FIRST, amount=amount,
                 currency=currency, tax_type='road_tax', recurring=True,
                 recurrence_type='monthly', next_due_date=FIRST)
    db.session.add(t)
    db.session.commit()
    return t


def test_requires_auth(client):
    assert client.get('/api/vehicles/1/forecast').status_code == 401


def test_twelve_buckets_in_user_currency(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        vid = v.id
    body = client.get(f'/api/vehicles/{vid}/forecast', headers=auth_headers(user.id)).get_json()
    assert len(body['buckets']) == 12
    assert body['months'] == 12
    assert body['currency'] == (user.currency or 'GBP')
    # First bucket is the current month.
    assert body['buckets'][0]['month'] == FIRST.strftime('%Y-%m')


def test_monthly_recurring_tax_appears_every_month(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        _mk_recurring_tax(user.id, v.id, 50, currency=user.currency or 'GBP')
        vid = v.id
    body = client.get(f'/api/vehicles/{vid}/forecast', headers=auth_headers(user.id)).get_json()
    for b in body['buckets']:
        assert b['breakdown']['tax'] == 50.0
        assert b['projected'] == 50.0


def test_prediction_lands_in_its_month(app, client, user, auth_headers):
    target = (FIRST + relativedelta(months=2))
    with app.app_context():
        v = _mk_vehicle(user.id)
        db.session.add(PredictionAlert(
            vehicle_id=v.id, user_id=user.id, alert_type='oil_change',
            estimated_cost=200, predicted_date=target, severity='info',
            dismissed=False, actioned=False))
        db.session.commit()
        vid = v.id
    body = client.get(f'/api/vehicles/{vid}/forecast', headers=auth_headers(user.id)).get_json()
    key = target.strftime('%Y-%m')
    match = [b for b in body['buckets'] if b['month'] == key]
    assert match and match[0]['breakdown']['prediction'] == 200.0


def test_annual_insurance_spread_to_monthly(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        db.session.add(InsurancePolicy(
            user_id=user.id, vehicle_id=v.id, provider='Aviva', premium=1200,
            payment_frequency='annual', currency=user.currency or 'GBP', status='active',
            start_date=FIRST - relativedelta(months=1),
            end_date=FIRST + relativedelta(months=18)))
        db.session.commit()
        vid = v.id
    body = client.get(f'/api/vehicles/{vid}/forecast', headers=auth_headers(user.id)).get_json()
    # €1,200/yr → €100/month in every active month.
    for b in body['buckets']:
        assert b['breakdown']['insurance'] == 100.0


def test_over_budget_flagged(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id, budget=10)   # tiny budget
        _mk_recurring_tax(user.id, v.id, 50, currency=user.currency or 'GBP')
        vid = v.id
    body = client.get(f'/api/vehicles/{vid}/forecast', headers=auth_headers(user.id)).get_json()
    assert body['monthly_budget'] == 10.0
    assert all(b['over_budget'] for b in body['buckets'])


def test_ownership_isolation(app, client, user, auth_headers):
    with app.app_context():
        other = User(email='o11@example.com', username='o11', is_active=True)
        other.set_password('Str0ng!Passw0rd')
        db.session.add(other)
        db.session.commit()
        ov = _mk_vehicle(other.id, 'Theirs')
        vid = ov.id
    # Requesting another user's vehicle forecast is a 404.
    assert client.get(f'/api/vehicles/{vid}/forecast',
                      headers=auth_headers(user.id)).status_code == 404


def test_fleet_forecast_sums_vehicles(app, client, user, auth_headers):
    with app.app_context():
        v1 = _mk_vehicle(user.id, 'A')
        v2 = _mk_vehicle(user.id, 'B')
        _mk_recurring_tax(user.id, v1.id, 30, currency=user.currency or 'GBP')
        _mk_recurring_tax(user.id, v2.id, 20, currency=user.currency or 'GBP')
    body = client.get('/api/forecast', headers=auth_headers(user.id)).get_json()
    assert len(body['buckets']) == 12
    # Both vehicles' monthly taxes summed into each month.
    assert body['buckets'][0]['breakdown']['tax'] == 50.0

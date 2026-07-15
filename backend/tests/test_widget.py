"""Tests for F38 — Gethomepage widget v2 (due items, fines owed, fuel price).

Covers the full API-key flow (generate → call with X-API-Key) since no widget
tests existed before.
"""

from datetime import date, timedelta

import pytest

from app import db
from app.models import Vehicle, ParkingEntry
from app.models.insurance import InsurancePolicy
import app.services.fuel_price_service as fps

TODAY = date.today()


@pytest.fixture(autouse=True)
def _fixed_prices(monkeypatch):
    """Deterministic, offline fuel prices."""
    monkeypatch.setattr(fps, 'get_prices', lambda country, app, force=False: {
        'diesel': 1.52, 'petrol': 1.44, 'lpg': 0.80, 'premium': None,
        'currency': '€', 'currency_code': 'EUR',
        'last_update': TODAY.isoformat(), 'baseline': False, 'stale': False,
    })


def _api_key(client, user, auth_headers):
    resp = client.post('/api/widget/api-key', headers=auth_headers(user.id))
    assert resp.status_code in (200, 201), resp.get_data(as_text=True)
    key = resp.get_json()['raw_key']   # returned exactly once (S07)
    assert key
    return key


def test_widget_requires_api_key(client):
    assert client.get('/api/widget/v1/homepage').status_code == 401
    assert client.get('/api/widget/v1/homepage',
                      headers={'X-API-Key': 'wrong-key'}).status_code == 401


def test_widget_v2_fields(app, client, user, auth_headers):
    with app.app_context():
        v = Vehicle(user_id=user.id, name='Golf', make='VW', model='Golf')
        db.session.add(v)
        db.session.commit()
        # Due item: insurance ending in 6 days (lands in the F4 feed).
        db.session.add(InsurancePolicy(
            user_id=user.id, vehicle_id=v.id, provider='Acme', status='active',
            premium=420, start_date=TODAY - timedelta(days=359),
            end_date=TODAY + timedelta(days=6)))
        # Outstanding fine: 60 pending.
        db.session.add(ParkingEntry(
            user_id=user.id, vehicle_id=v.id, amount=60, date=TODAY,
            parking_type='fine', fine_reason='Bus lane', fine_status='pending'))
        db.session.commit()
        u = db.session.get(type(user), user.id)
        u.currency = 'EUR'
        db.session.commit()

    key = _api_key(client, user, auth_headers)
    resp = client.get('/api/widget/v1/homepage', headers={'X-API-Key': key})
    assert resp.status_code == 200
    body = resp.get_json()

    # Original fields still present (backward-compatible mappings).
    for field in ('vehicles', 'service_records', 'reminders', 'next_reminder', 'subtitle'):
        assert field in body
    assert body['vehicles'] == 1

    # F38 fields.
    assert body['due_soon'] >= 1
    assert 'Golf' in body['next_due'] and '(6d)' in body['next_due']
    assert body['fines_owed'] == '60.00 EUR'
    assert body['fuel_price'] == 'diesel 1.52 €/L'


def test_widget_degrades_gracefully(app, client, user, auth_headers, monkeypatch):
    """Price service down + no data → 200 with safe defaults, never a 500."""
    monkeypatch.setattr(fps, 'get_prices',
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError('down')))

    key = _api_key(client, user, auth_headers)
    resp = client.get('/api/widget/v1/homepage', headers={'X-API-Key': key})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['due_soon'] == 0
    assert body['next_due'] == 'None'
    assert body['fines_owed'] == '0.00 GBP'
    assert body['fuel_price'] == 'N/A'

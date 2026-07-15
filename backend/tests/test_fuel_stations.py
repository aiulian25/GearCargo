"""Tests for F26 — per-station fuel price insights."""

from datetime import date, timedelta

import pytest

from app import db
from app.models import User, Vehicle, FuelEntry
import app.services.fuel_price_service as fps

TODAY = date.today()


@pytest.fixture(autouse=True)
def _fixed_national_price(monkeypatch):
    """Deterministic, offline national price (diesel 1.50)."""
    monkeypatch.setattr(fps, 'get_prices', lambda country, app, force=False: {
        'diesel': 1.50, 'petrol': 1.40, 'lpg': 0.80, 'premium': None,
        'currency_code': 'GBP', 'source': 'test',
        'last_update': TODAY.isoformat(), 'baseline': False, 'stale': False,
    })


def _mk_vehicle(user_id, fuel_type='diesel'):
    v = Vehicle(user_id=user_id, name='Passat', make='VW', model='Passat',
                fuel_type=fuel_type)
    db.session.add(v)
    db.session.commit()
    db.session.refresh(v)
    return v


def _mk_fill(user_id, vehicle_id, days_ago, station, price):
    db.session.add(FuelEntry(
        user_id=user_id, vehicle_id=vehicle_id, amount=price * 40,
        date=TODAY - timedelta(days=days_ago), liters=40,
        price_per_liter=price, total_price=price * 40,
        station=station, fuel_type='diesel'))


def test_stations_grouped_ordered_and_compared(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        _mk_fill(user.id, v.id, 30, 'Shell High St', 1.60)
        _mk_fill(user.id, v.id, 10, 'Shell High St', 1.50)   # avg 1.55
        _mk_fill(user.id, v.id, 5, 'Costco', 1.35)
        db.session.commit()
        vid = v.id

    resp = client.get(f'/api/fuel/stations?vehicle_id={vid}', headers=auth_headers(user.id))
    assert resp.status_code == 200
    body = resp.get_json()

    assert body['national_price'] == 1.50
    assert body['currency_code'] == 'GBP'
    names = [s['name'] for s in body['stations']]
    assert names == ['Shell High St', 'Costco']            # ordered by fills desc

    shell = body['stations'][0]
    assert shell['fills'] == 2
    assert shell['avg_price'] == 1.55
    assert shell['last_price'] == 1.50                     # most recent fill
    assert shell['delta_vs_national_pct'] == 3.3           # (1.55-1.50)/1.50

    costco = body['stations'][1]
    assert costco['delta_vs_national_pct'] == -10.0


def test_stations_isolated_per_user(app, client, user, auth_headers):
    with app.app_context():
        other = User(email='other4@example.com', username='other4', is_active=True)
        other.set_password('Str0ng!Passw0rd')
        db.session.add(other)
        db.session.commit()
        ov = _mk_vehicle(other.id)
        _mk_fill(other.id, ov.id, 3, 'Their Secret Station', 1.20)

        v = _mk_vehicle(user.id)
        _mk_fill(user.id, v.id, 2, 'My Station', 1.45)
        db.session.commit()

    body = client.get('/api/fuel/stations', headers=auth_headers(user.id)).get_json()
    names = [s['name'] for s in body['stations']]
    assert names == ['My Station']
    assert 'Their Secret Station' not in names


def test_station_less_fills_are_ignored_and_auth_required(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        _mk_fill(user.id, v.id, 4, None, 1.40)             # no station → excluded
        db.session.add(FuelEntry(                          # no price → excluded
            user_id=user.id, vehicle_id=v.id, amount=60, liters=40,
            date=TODAY - timedelta(days=2), station='Shell', fuel_type='diesel'))
        db.session.commit()
        vid = v.id

    assert client.get('/api/fuel/stations').status_code == 401
    body = client.get(f'/api/fuel/stations?vehicle_id={vid}',
                      headers=auth_headers(user.id)).get_json()
    assert body['stations'] == []


def test_station_address_in_entry_json(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        db.session.add(FuelEntry(
            user_id=user.id, vehicle_id=v.id, amount=60, liters=40,
            date=TODAY, price_per_liter=1.5, total_price=60,
            station='Shell', station_address='1 High Street', fuel_type='diesel'))
        db.session.commit()
        vid = v.id

    entries = client.get(f'/api/fuel?vehicle_id={vid}',
                         headers=auth_headers(user.id)).get_json()['entries']
    assert entries[0]['station_address'] == '1 High Street'

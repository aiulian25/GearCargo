"""Tests for GET /api/vehicles/recent-transactions — the fleet-wide feed."""

from datetime import date, timedelta

from app import db
from app.models import User, Vehicle, FuelEntry, ServiceEntry, InsurancePolicy


def _mk_vehicle(user_id, name):
    v = Vehicle(user_id=user_id, name=name, make='Ford', model='Focus')
    db.session.add(v)
    db.session.commit()
    db.session.refresh(v)
    return v


def test_requires_auth(client):
    assert client.get('/api/vehicles/recent-transactions').status_code == 401


def test_merges_types_newest_first_with_vehicle_name(app, client, user, auth_headers):
    with app.app_context():
        v1 = _mk_vehicle(user.id, 'Ford Focus')
        v2 = _mk_vehicle(user.id, 'VW Golf')
        today = date.today()

        # Oldest → newest so we can assert ordering.
        db.session.add(ServiceEntry(user_id=user.id, vehicle_id=v2.id,
                                    date=today - timedelta(days=10), amount=120, title='MOT'))
        db.session.add(FuelEntry(user_id=user.id, vehicle_id=v1.id,
                                 date=today - timedelta(days=5), amount=64.20,
                                 total_price=64.20, fuel_type='petrol'))
        db.session.add(InsurancePolicy(user_id=user.id, vehicle_id=v1.id,
                                       provider='Aviva', policy_number='V-88219',
                                       premium=363.68, start_date=today - timedelta(days=1),
                                       end_date=today + timedelta(days=364)))
        db.session.commit()

    resp = client.get('/api/vehicles/recent-transactions', headers=auth_headers(user.id))
    assert resp.status_code == 200
    txs = resp.get_json()['transactions']

    assert len(txs) == 3
    # Newest first: insurance (day -1), fuel (day -5), service (day -10)
    assert [t['type'] for t in txs] == ['insurance', 'fuel', 'service']
    # Each carries its vehicle name and a cost.
    assert txs[0]['vehicle_name'] == 'Ford Focus' and txs[0]['cost'] == 363.68
    assert txs[1]['vehicle_name'] == 'Ford Focus'
    assert txs[2]['vehicle_name'] == 'VW Golf'
    assert all('id' in t and 'vehicle_id' in t for t in txs)


def test_limit_caps_results(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id, 'Ford Focus')
        today = date.today()
        for i in range(8):
            db.session.add(FuelEntry(user_id=user.id, vehicle_id=v.id,
                                     date=today - timedelta(days=i), amount=50 + i,
                                     total_price=50 + i, fuel_type='petrol'))
        db.session.commit()

    resp = client.get('/api/vehicles/recent-transactions?limit=5', headers=auth_headers(user.id))
    assert resp.status_code == 200
    assert len(resp.get_json()['transactions']) == 5


def test_excludes_future_dated_entries(app, client, user, auth_headers):
    # A future-dated scheduled entry (e.g. next year's MOT) must NOT appear in
    # the "recent" feed; a past entry on the same vehicle should.
    with app.app_context():
        v = _mk_vehicle(user.id, 'Ford Focus')
        today = date.today()
        db.session.add(ServiceEntry(user_id=user.id, vehicle_id=v.id,
                                    date=today + timedelta(days=200), amount=0, title='scheduled MOT'))
        db.session.add(FuelEntry(user_id=user.id, vehicle_id=v.id,
                                 date=today - timedelta(days=2), amount=60,
                                 total_price=60, fuel_type='petrol'))
        db.session.commit()

    resp = client.get('/api/vehicles/recent-transactions', headers=auth_headers(user.id))
    txs = resp.get_json()['transactions']
    assert len(txs) == 1
    assert txs[0]['type'] == 'fuel'
    assert all('MOT' not in (t.get('title') or '') for t in txs)


def test_isolation_never_leaks_other_users_entries(app, client, user, auth_headers):
    with app.app_context():
        # The authorized user's own entry.
        v_mine = _mk_vehicle(user.id, 'Mine')
        db.session.add(FuelEntry(user_id=user.id, vehicle_id=v_mine.id,
                                 date=date.today(), amount=10, total_price=10, fuel_type='petrol'))

        # A second user with their own vehicle + entry.
        other = User(username='other', email='other@example.com', is_active=True)
        other.set_password('StrongPass123!')
        db.session.add(other)
        db.session.commit()
        db.session.refresh(other)
        v_theirs = _mk_vehicle(other.id, 'Theirs')
        db.session.add(ServiceEntry(user_id=other.id, vehicle_id=v_theirs.id,
                                    date=date.today(), amount=999, title='secret'))
        db.session.commit()

    resp = client.get('/api/vehicles/recent-transactions', headers=auth_headers(user.id))
    txs = resp.get_json()['transactions']
    assert len(txs) == 1
    assert txs[0]['vehicle_name'] == 'Mine'
    assert all(t['vehicle_name'] != 'Theirs' for t in txs)

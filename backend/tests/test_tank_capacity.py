"""Tests for F22 — vehicles.tank_capacity persists and round-trips.

Before the fix the Add/Edit forms collected tank_capacity but no column
existed: create ignored it and update wrote a transient attribute — the
field always re-opened empty.
"""

from app import db
from app.models import Vehicle


def test_create_persists_tank_capacity(app, client, user, auth_headers):
    resp = client.post('/api/vehicles', json={
        'name': 'Passat', 'make': 'VW', 'model': 'Passat',
        'tank_capacity': 52.5,
    }, headers=auth_headers(user.id))
    assert resp.status_code == 201
    vid = resp.get_json()['vehicle']['id']
    assert resp.get_json()['vehicle']['tank_capacity'] == 52.5

    got = client.get(f'/api/vehicles/{vid}', headers=auth_headers(user.id)).get_json()
    assert got['tank_capacity'] == 52.5


def test_update_persists_and_clears_tank_capacity(app, client, user, auth_headers):
    resp = client.post('/api/vehicles', json={'name': 'Clio'},
                       headers=auth_headers(user.id))
    vid = resp.get_json()['vehicle']['id']
    assert resp.get_json()['vehicle']['tank_capacity'] is None

    resp = client.put(f'/api/vehicles/{vid}', json={'tank_capacity': 42},
                      headers=auth_headers(user.id))
    assert resp.status_code == 200
    assert resp.get_json()['vehicle']['tank_capacity'] == 42.0
    with app.app_context():
        assert float(db.session.get(Vehicle, vid).tank_capacity) == 42.0

    # Clearing works (EditVehicle sends null for an emptied field).
    resp = client.put(f'/api/vehicles/{vid}', json={'tank_capacity': None},
                      headers=auth_headers(user.id))
    assert resp.get_json()['vehicle']['tank_capacity'] is None

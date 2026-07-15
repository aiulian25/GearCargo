"""Tests for F23 — the vehicle spec sheet round-trips through the API.

Before the fix: dimensions sent by the Add form were silently discarded on
create; vehicle_length_cm was unsettable through the app; drivetrain and
purchase_date/purchase_price were write-once-then-invisible (absent from
to_dict).
"""

from datetime import date

from app import db
from app.models import Vehicle


def test_create_persists_dimensions_and_specs(app, client, user, auth_headers):
    resp = client.post('/api/vehicles', json={
        'name': 'Camper', 'make': 'VW', 'model': 'California',
        'drivetrain': 'awd',
        'vehicle_height_cm': 199,
        'vehicle_width_cm': 190,
        'vehicle_length_cm': 490,
        'vehicle_weight_kg': 2500,
        'purchase_date': '2024-05-01',
        'purchase_price': 45000,
    }, headers=auth_headers(user.id))
    assert resp.status_code == 201
    vid = resp.get_json()['vehicle']['id']

    got = client.get(f'/api/vehicles/{vid}', headers=auth_headers(user.id)).get_json()
    assert got['vehicle_height_cm'] == 199
    assert got['vehicle_width_cm'] == 190
    assert got['vehicle_length_cm'] == 490
    assert got['vehicle_weight_kg'] == 2500
    assert got['drivetrain'] == 'awd'
    assert got['purchase_date'] == '2024-05-01'
    assert got['purchase_price'] == 45000.0


def test_update_persists_length_and_purchase_fields(app, client, user, auth_headers):
    resp = client.post('/api/vehicles', json={
        'name': 'Golf', 'make': 'VW', 'model': 'Golf',
    }, headers=auth_headers(user.id))
    vid = resp.get_json()['vehicle']['id']

    resp = client.put(f'/api/vehicles/{vid}', json={
        'vehicle_length_cm': 428,
        'purchase_date': '2023-11-15',
        'purchase_price': 18750.50,
        'drivetrain': 'fwd',
    }, headers=auth_headers(user.id))
    assert resp.status_code == 200
    body = resp.get_json()['vehicle']
    assert body['vehicle_length_cm'] == 428
    assert body['purchase_date'] == '2023-11-15'
    assert body['purchase_price'] == 18750.50
    assert body['drivetrain'] == 'fwd'

    with app.app_context():
        v = db.session.get(Vehicle, vid)
        assert v.vehicle_length_cm == 428
        assert v.purchase_date == date(2023, 11, 15)
        assert float(v.purchase_price) == 18750.50


def test_update_can_clear_purchase_date(app, client, user, auth_headers):
    resp = client.post('/api/vehicles', json={
        'name': 'Ibiza', 'purchase_date': '2022-01-01',
    }, headers=auth_headers(user.id))
    vid = resp.get_json()['vehicle']['id']

    resp = client.put(f'/api/vehicles/{vid}', json={'purchase_date': None},
                      headers=auth_headers(user.id))
    assert resp.status_code == 200
    assert resp.get_json()['vehicle']['purchase_date'] is None

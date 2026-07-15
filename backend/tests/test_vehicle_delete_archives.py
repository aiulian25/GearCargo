"""Tests for F21 — soft vehicle delete archives instead of silently no-oping.

Before the fix, DELETE /api/vehicles/<id> (without ?hard=true) set a phantom
`is_active` attribute, persisted nothing, and returned "Vehicle deleted" while
the vehicle stayed fully visible.
"""

from datetime import date, timedelta

from app import db
from app.models import Vehicle, InsurancePolicy, TaxEntry

TODAY = date.today()


def _create_vehicle(client, user, auth_headers, name='Corsa'):
    resp = client.post('/api/vehicles', json={
        'name': name, 'make': 'Opel', 'model': 'Corsa',
    }, headers=auth_headers(user.id))
    assert resp.status_code == 201
    return resp.get_json()['vehicle']['id']


def _listed_ids(client, user, auth_headers, path='/api/vehicles'):
    return [v['id'] for v in
            client.get(path, headers=auth_headers(user.id)).get_json()['vehicles']]


def test_soft_delete_archives_and_hides_vehicle(app, client, user, auth_headers):
    vid = _create_vehicle(client, user, auth_headers)

    resp = client.delete(f'/api/vehicles/{vid}', headers=auth_headers(user.id))
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['archived'] is True
    assert body['vehicle']['id'] == vid

    # Gone from the garage, present under Archived — and restorable.
    assert vid not in _listed_ids(client, user, auth_headers)
    assert vid in _listed_ids(client, user, auth_headers, '/api/vehicles/archived')

    with app.app_context():
        v = db.session.get(Vehicle, vid)
        assert v is not None and v.archived is True and v.archived_at is not None


def test_soft_delete_cancels_insurance_and_recurring_taxes(app, client, user, auth_headers):
    vid = _create_vehicle(client, user, auth_headers, 'Astra')
    with app.app_context():
        db.session.add(InsurancePolicy(
            user_id=user.id, vehicle_id=vid, provider='Acme', status='active',
            premium=420, start_date=TODAY - timedelta(days=30),
            end_date=TODAY + timedelta(days=335)))
        db.session.add(TaxEntry(
            user_id=user.id, vehicle_id=vid, amount=15, date=TODAY,
            tax_type='road_tax', recurring=True, recurrence_type='monthly',
            next_due_date=TODAY + timedelta(days=20)))
        db.session.commit()

    assert client.delete(f'/api/vehicles/{vid}',
                         headers=auth_headers(user.id)).status_code == 200

    with app.app_context():
        policy = InsurancePolicy.query.filter_by(vehicle_id=vid).first()
        assert policy.status == 'cancelled' and policy.auto_renew is False
        tax = TaxEntry.query.filter_by(vehicle_id=vid).first()
        assert tax.recurring is False and tax.next_due_date is None


def test_hard_delete_removes_entirely(app, client, user, auth_headers):
    vid = _create_vehicle(client, user, auth_headers, 'Scrapped')

    resp = client.delete(f'/api/vehicles/{vid}?hard=true', headers=auth_headers(user.id))
    assert resp.status_code == 200
    assert resp.get_json()['message'] == 'Vehicle deleted'

    assert vid not in _listed_ids(client, user, auth_headers)
    assert vid not in _listed_ids(client, user, auth_headers, '/api/vehicles/archived')
    with app.app_context():
        assert db.session.get(Vehicle, vid) is None


def test_update_persists_drivetrain_and_ignores_phantom_fields(app, client, user, auth_headers):
    vid = _create_vehicle(client, user, auth_headers, 'Quattro')

    resp = client.put(f'/api/vehicles/{vid}', json={
        'drivetrain': 'awd',
        'body_type': 'x',            # phantom — ignored without error
        'is_active': False,          # phantom — must not fake-archive anything
    }, headers=auth_headers(user.id))
    assert resp.status_code == 200

    with app.app_context():
        v = db.session.get(Vehicle, vid)
        assert v.drivetrain == 'awd'
        assert v.archived is False
    assert vid in _listed_ids(client, user, auth_headers)


def test_delete_requires_ownership(app, client, user, auth_headers):
    from app.models import User
    with app.app_context():
        other = User(email='other3@example.com', username='other3', is_active=True)
        other.set_password('Str0ng!Passw0rd')
        db.session.add(other)
        db.session.commit()
        v = Vehicle(user_id=other.id, name='Theirs', make='X', model='Y')
        db.session.add(v)
        db.session.commit()
        vid = v.id

    assert client.delete(f'/api/vehicles/{vid}',
                         headers=auth_headers(user.id)).status_code == 404
    with app.app_context():
        assert db.session.get(Vehicle, vid).archived is False

"""Tests for F14 — surface paid and unpaid parking fines."""

from datetime import date

from app import db
from app.models import User, Vehicle, ParkingEntry


def _mk_user(email='fines@example.com', username='finesuser'):
    u = User(email=email, username=username, is_active=True)
    u.set_password('Str0ng!Passw0rd')
    db.session.add(u)
    db.session.commit()
    return u


def _mk_vehicle(user_id, name='Focus'):
    v = Vehicle(user_id=user_id, name=name, make='Ford', model='Focus')
    db.session.add(v)
    db.session.commit()
    db.session.refresh(v)
    return v


def _mk_fine(user_id, vehicle_id, amount, status, reason='No ticket'):
    f = ParkingEntry(user_id=user_id, vehicle_id=vehicle_id, date=date.today(),
                     amount=amount, parking_type='fine',
                     fine_status=status, fine_reason=reason)
    db.session.add(f)
    db.session.commit()
    return f


def test_requires_auth(client):
    assert client.get('/api/parking/fines').status_code == 401


def test_default_returns_outstanding_with_total(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        _mk_fine(user.id, v.id, 60, 'pending')
        _mk_fine(user.id, v.id, 40, 'contested')
        _mk_fine(user.id, v.id, 25, 'paid')          # excluded

    body = client.get('/api/parking/fines', headers=auth_headers(user.id)).get_json()
    statuses = sorted(f['fine_status'] for f in body['fines'])
    assert statuses == ['contested', 'pending']
    assert body['count'] == 2
    assert body['total_owed'] == 100.0               # 60 + 40, paid excluded


def test_status_pending_filter(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        _mk_fine(user.id, v.id, 60, 'pending')
        _mk_fine(user.id, v.id, 40, 'contested')

    body = client.get('/api/parking/fines?status=pending',
                      headers=auth_headers(user.id)).get_json()
    assert body['count'] == 1
    assert body['fines'][0]['fine_status'] == 'pending'
    assert body['total_owed'] == 60.0


def test_status_paid_filter(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        _mk_fine(user.id, v.id, 25, 'paid')

    body = client.get('/api/parking/fines?status=paid',
                      headers=auth_headers(user.id)).get_json()
    assert body['count'] == 1
    assert body['fines'][0]['fine_status'] == 'paid'
    assert body['total_owed'] == 0.0                 # paid isn't "owed"


def test_unset_status_treated_as_pending(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        _mk_fine(user.id, v.id, 30, None)            # legacy fine, no status

    body = client.get('/api/parking/fines', headers=auth_headers(user.id)).get_json()
    assert body['count'] == 1
    assert body['fines'][0]['fine_status'] == 'pending'
    assert body['fines'][0]['vehicle_name'] == 'Focus'
    assert body['total_owed'] == 30.0


def test_cross_user_isolation(app, client, user, auth_headers):
    with app.app_context():
        other = _mk_user('other14@example.com', 'other14')
        ov = _mk_vehicle(other.id, 'Theirs')
        _mk_fine(other.id, ov.id, 99, 'pending')

    body = client.get('/api/parking/fines', headers=auth_headers(user.id)).get_json()
    assert body['count'] == 0
    assert body['total_owed'] == 0.0


def test_create_fine_defaults_to_pending(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        vid = v.id

    resp = client.post('/api/parking', json={
        'vehicle_id': vid, 'parking_type': 'fine', 'cost': 50,
        'fine_reason': 'Expired meter',
    }, headers=auth_headers(user.id))
    assert resp.status_code == 201
    assert resp.get_json()['entry']['fine_status'] == 'pending'


def test_fine_appears_in_due_surface(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        _mk_fine(user.id, v.id, 60, 'pending', reason='Loading zone')

    body = client.get('/api/due', headers=auth_headers(user.id)).get_json()
    fines = [it for it in body['items'] if it['kind'] == 'fine']
    assert len(fines) == 1
    assert fines[0]['severity'] == 'warning'
    assert fines[0]['title'] == 'Loading zone'

"""Tests for F2 — warranty ledger endpoint + expiry push job."""

from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from app import db
from app.models import User, Vehicle, ServiceEntry, RepairEntry, ConsumableEntry


def _mk_vehicle(user_id, name='Focus', mileage=10000):
    v = Vehicle(user_id=user_id, name=name, make='Ford', model='Focus',
                current_mileage=mileage, distance_unit='km')
    db.session.add(v)
    db.session.commit()
    db.session.refresh(v)
    return v


def test_requires_auth(client):
    assert client.get('/api/vehicles/1/warranties').status_code == 401


def test_ledger_lists_in_force_and_excludes_expired(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        today = date.today()
        # In force: explicit expiry 10 days out.
        db.session.add(ServiceEntry(user_id=user.id, vehicle_id=v.id, date=today,
                                    title='Cambelt', amount=400,
                                    warranty_expires=today + timedelta(days=10)))
        # Expired: expiry in the past → excluded.
        db.session.add(ServiceEntry(user_id=user.id, vehicle_id=v.id, date=today,
                                    title='Old service', amount=100,
                                    warranty_expires=today - timedelta(days=5)))
        # Repair with 24-month warranty from today → in force, days_left ~ 730.
        db.session.add(RepairEntry(user_id=user.id, vehicle_id=v.id, date=today,
                                   title='Alternator', amount=300, warranty_months=24))
        db.session.commit()
        vid = v.id

    resp = client.get(f'/api/vehicles/{vid}/warranties', headers=auth_headers(user.id))
    assert resp.status_code == 200
    data = resp.get_json()

    labels = {i['label']: i for i in data['items']}
    assert 'Cambelt' in labels and 'Alternator' in labels
    assert 'Old service' not in labels          # expired excluded
    assert data['count'] == 2
    assert labels['Cambelt']['days_left'] == 10
    # Soonest-first ordering + nearest summary.
    assert data['items'][0]['label'] == 'Cambelt'
    assert data['nearest_days_left'] == 10


def test_km_limit_excludes_when_mileage_exhausted(app, client, user, auth_headers):
    with app.app_context():
        # Warranty: 12 months AND 20,000 km from odo 10,000; car now at 35,000 →
        # km exhausted (whichever-first) → excluded even though time remains.
        v = _mk_vehicle(user.id, mileage=35000)
        today = date.today()
        db.session.add(ServiceEntry(user_id=user.id, vehicle_id=v.id, date=today,
                                    title='Clutch', amount=800, odometer=10000,
                                    warranty_months=12, warranty_km=20000))
        db.session.commit()
        vid = v.id

    items = client.get(f'/api/vehicles/{vid}/warranties',
                       headers=auth_headers(user.id)).get_json()['items']
    assert items == []


def test_km_left_reported_when_in_force(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id, mileage=15000)
        today = date.today()
        db.session.add(ServiceEntry(user_id=user.id, vehicle_id=v.id, date=today,
                                    title='Gearbox', amount=800, odometer=10000,
                                    warranty_months=36, warranty_km=20000))
        db.session.commit()
        vid = v.id

    item = client.get(f'/api/vehicles/{vid}/warranties',
                      headers=auth_headers(user.id)).get_json()['items'][0]
    assert item['km_left'] == 15000     # 20000 - (15000 - 10000)


def test_ledger_scoped_to_owner(app, client, user, auth_headers):
    with app.app_context():
        other = User(email='o@example.com', username='other2', is_active=True)
        other.set_password('Str0ng!Passw0rd')
        db.session.add(other)
        db.session.commit()
        v = _mk_vehicle(other.id, 'Other')
        db.session.add(ServiceEntry(user_id=other.id, vehicle_id=v.id, date=date.today(),
                                    title='X', amount=1, warranty_months=12))
        db.session.commit()
        vid = v.id

    # Requesting user does not own that vehicle → 404 (no cross-user leakage).
    resp = client.get(f'/api/vehicles/{vid}/warranties', headers=auth_headers(user.id))
    assert resp.status_code == 404


def test_check_warranty_expiry_pushes_once(app, monkeypatch):
    from app.services import check_warranty_expiry
    import app.routes.push as push_mod
    calls = []
    monkeypatch.setattr(push_mod, 'send_push_to_user',
                        lambda *a, **k: calls.append((a, k)) or 1)

    with app.app_context():
        u = User(email='w@example.com', username='warr', is_active=True)
        u.set_password('Str0ng!Passw0rd')
        db.session.add(u)
        db.session.commit()
        v = _mk_vehicle(u.id)
        today = date.today()
        # Expires in 12 days → within the 30-day horizon.
        s = ServiceEntry(user_id=u.id, vehicle_id=v.id, date=today, title='Brakes',
                         amount=200, warranty_expires=today + timedelta(days=12))
        db.session.add(s)
        db.session.commit()
        sid = s.id

    check_warranty_expiry(app)
    assert len(calls) == 1
    with app.app_context():
        assert db.session.get(ServiceEntry, sid).warranty_notified is True

    check_warranty_expiry(app)
    assert len(calls) == 1     # sentinel prevents a second push


def test_check_warranty_expiry_ignores_far_off(app, monkeypatch):
    from app.services import check_warranty_expiry
    import app.routes.push as push_mod
    calls = []
    monkeypatch.setattr(push_mod, 'send_push_to_user', lambda *a, **k: calls.append(1) or 1)

    with app.app_context():
        u = User(email='w2@example.com', username='warr2', is_active=True)
        u.set_password('Str0ng!Passw0rd')
        db.session.add(u)
        db.session.commit()
        v = _mk_vehicle(u.id)
        # 24 months away → outside the 30-day window.
        db.session.add(RepairEntry(user_id=u.id, vehicle_id=v.id, date=date.today(),
                                   title='Engine', amount=999, warranty_months=24))
        db.session.commit()

    check_warranty_expiry(app)
    assert calls == []


# --- Route-level capture: the forms must be able to feed the ledger -----------

def test_service_create_captures_warranty_fields(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        vid = v.id

    resp = client.post('/api/services', json={
        'vehicle_id': vid, 'service_types': ['brake_service'], 'total_cost': 250,
        'warranty_months': 24, 'warranty_km': 40000,
    }, headers=auth_headers(user.id))
    assert resp.status_code == 201
    sid = resp.get_json()['entry']['id']

    with app.app_context():
        s = db.session.get(ServiceEntry, sid)
        assert s.warranty_months == 24
        assert s.warranty_km == 40000

    # …and it shows up in the ledger.
    data = client.get(f'/api/vehicles/{vid}/warranties',
                      headers=auth_headers(user.id)).get_json()
    assert data['count'] == 1


def test_service_update_sets_and_clears_warranty(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        s = ServiceEntry(user_id=user.id, vehicle_id=v.id, date=date.today(),
                         title='Clutch', amount=600, service_type='other')
        db.session.add(s)
        db.session.commit()
        sid, vid = s.id, v.id

    expires = (date.today() + timedelta(days=90)).isoformat()
    resp = client.put(f'/api/services/{sid}', json={
        'warranty_months': 12, 'warranty_expires': expires,
    }, headers=auth_headers(user.id))
    assert resp.status_code == 200
    with app.app_context():
        s = db.session.get(ServiceEntry, sid)
        assert s.warranty_months == 12
        assert s.warranty_expires == date.today() + timedelta(days=90)

    # Clearing with empty string / null removes the warranty.
    resp = client.put(f'/api/services/{sid}', json={
        'warranty_months': '', 'warranty_expires': None,
    }, headers=auth_headers(user.id))
    assert resp.status_code == 200
    with app.app_context():
        s = db.session.get(ServiceEntry, sid)
        assert s.warranty_months is None
        assert s.warranty_expires is None


def test_repair_create_and_update_capture_warranty_fields(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        vid = v.id

    resp = client.post('/api/repairs', json={
        'vehicle_id': vid, 'repair_types': ['brakes'], 'total_cost': 300,
        'warranty_months': 12, 'warranty_km': 20000, 'warranty_covered': True,
    }, headers=auth_headers(user.id))
    assert resp.status_code == 201
    rid = resp.get_json()['entry']['id']

    with app.app_context():
        r = db.session.get(RepairEntry, rid)
        assert r.warranty_months == 12
        assert r.warranty_km == 20000
        assert r.under_warranty is True

    # PUT maps warranty_covered onto the real under_warranty column.
    resp = client.put(f'/api/repairs/{rid}', json={
        'warranty_covered': False, 'warranty_months': 6,
    }, headers=auth_headers(user.id))
    assert resp.status_code == 200
    with app.app_context():
        r = db.session.get(RepairEntry, rid)
        assert r.under_warranty is False
        assert r.warranty_months == 6

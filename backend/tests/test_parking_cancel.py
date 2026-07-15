"""Tests for F34 — POST /api/parking/<id>/cancel stops a recurring series."""

from datetime import date, timedelta

from app import db
from app.models import User, Vehicle, ParkingEntry
from app.services import process_recurring_parking_entries

TODAY = date.today()


def _mk_vehicle(user_id):
    v = Vehicle(user_id=user_id, name='Yaris', make='Toyota', model='Yaris')
    db.session.add(v)
    db.session.commit()
    db.session.refresh(v)
    return v


def _mk_recurring_permit(user_id, vehicle_id, next_due):
    p = ParkingEntry(
        user_id=user_id, vehicle_id=vehicle_id, amount=45,
        date=TODAY - timedelta(days=30), parking_type='monthly',
        title='Monthly permit', location='Downtown',
        recurring=True, recurrence_type='monthly', next_due_date=next_due)
    db.session.add(p)
    db.session.commit()
    db.session.refresh(p)
    return p


def test_cancel_stops_series_and_generator_is_noop(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        # Next occurrence already in the past — the generator WOULD clone it.
        p = _mk_recurring_permit(user.id, v.id, next_due=TODAY - timedelta(days=1))
        pid, vid = p.id, v.id

    resp = client.post(f'/api/parking/{pid}/cancel', headers=auth_headers(user.id))
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['message'] == 'Recurring parking cancelled'
    assert body['entry']['recurring'] is False
    assert body['entry']['next_due_date'] is None

    with app.app_context():
        p = db.session.get(ParkingEntry, pid)
        assert p.recurring is False and p.next_due_date is None
        before = ParkingEntry.query.filter_by(vehicle_id=vid).count()

        process_recurring_parking_entries(app)

        after = ParkingEntry.query.filter_by(vehicle_id=vid).count()
        assert after == before          # nothing new generated for the series


def test_cancel_rejects_non_recurring_and_enforces_ownership(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        plain = ParkingEntry(user_id=user.id, vehicle_id=v.id, amount=5,
                             date=TODAY, parking_type='street')
        db.session.add(plain)

        other = User(email='other5@example.com', username='other5', is_active=True)
        other.set_password('Str0ng!Passw0rd')
        db.session.add(other)
        db.session.commit()
        ov = _mk_vehicle(other.id)
        theirs = _mk_recurring_permit(other.id, ov.id, next_due=TODAY + timedelta(days=5))
        plain_id, theirs_id = plain.id, theirs.id

    # Not recurring → 400.
    assert client.post(f'/api/parking/{plain_id}/cancel',
                       headers=auth_headers(user.id)).status_code == 400
    # Someone else's series → 404, and it stays recurring.
    assert client.post(f'/api/parking/{theirs_id}/cancel',
                       headers=auth_headers(user.id)).status_code == 404
    with app.app_context():
        assert db.session.get(ParkingEntry, theirs_id).recurring is True
    # Auth required.
    assert client.post(f'/api/parking/{theirs_id}/cancel').status_code == 401

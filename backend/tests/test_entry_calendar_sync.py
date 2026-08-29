"""Step 7 — calendar sync must fire on update, delete and cancel, not just create.

`sync_entry_to_calendar` has always implemented all three actions ('delete' calls
CalendarService.delete_event; 'update' upserts on the same UID), but the tax and
parking routes only called it from create. A deleted tax therefore stayed on the
user's calendar forever, and an edited amount or date went stale — exactly the
drift calendar sync exists to prevent.

The real CalDAV call is monkeypatched: these tests assert the ROUTES dispatch
correctly, not that caldav works.
"""

from datetime import date, timedelta

import pytest

from app import db
from app.models import Vehicle, TaxEntry, ParkingEntry
import app.services.calendar_service as calendar_service

TODAY = date.today()
TAXES_URL = '/api/taxes'
PARKING_URL = '/api/parking'


@pytest.fixture
def synced(monkeypatch):
    """Record (entry_type, entry_id, action) instead of talking to CalDAV."""
    calls = []

    def _record(user, entry_type, entry, action='create'):
        # entry.id must still be readable — on delete this proves the sync runs
        # BEFORE db.session.delete().
        calls.append((entry_type, entry.id, action))
        return True, 'recorded'

    monkeypatch.setattr(calendar_service, 'sync_entry_to_calendar', _record)
    return calls


def _vehicle(user_id, name='Qashqai'):
    vehicle = Vehicle(user_id=user_id, name=name, make='Nissan', model='Qashqai')
    db.session.add(vehicle)
    db.session.commit()
    db.session.refresh(vehicle)
    return vehicle


def _enable_calendar(user_id):
    from app.models import User
    user_row = db.session.get(User, user_id)
    user_row.calendar_enabled = True
    db.session.commit()


def _tax(user_id, vehicle_id, **kwargs):
    fields = dict(user_id=user_id, vehicle_id=vehicle_id, date=TODAY, amount=15,
                  currency='EUR', tax_type='road_tax', title='road_tax',
                  due_date=TODAY + timedelta(days=30))
    fields.update(kwargs)
    entry = TaxEntry(**fields)
    db.session.add(entry)
    db.session.commit()
    db.session.refresh(entry)
    return entry


def _parking(user_id, vehicle_id, **kwargs):
    fields = dict(user_id=user_id, vehicle_id=vehicle_id, date=TODAY, amount=40,
                  currency='EUR', parking_type='permit', title='City Permit')
    fields.update(kwargs)
    entry = ParkingEntry(**fields)
    db.session.add(entry)
    db.session.commit()
    db.session.refresh(entry)
    return entry


# --- taxes ---------------------------------------------------------------------

def test_updating_a_tax_syncs_the_calendar(app, client, user, auth_headers, synced):
    with app.app_context():
        _enable_calendar(user.id)
        vehicle = _vehicle(user.id)
        entry = _tax(user.id, vehicle.id)
        entry_id = entry.id

    resp = client.put(f'{TAXES_URL}/{entry_id}', json={'amount': 25},
                      headers=auth_headers(user.id))

    assert resp.status_code == 200, resp.data[:200]
    assert ('tax', entry_id, 'update') in synced


def test_deleting_a_tax_syncs_a_delete(app, client, user, auth_headers, synced):
    """The reported symptom: a deleted tax stayed on the calendar."""
    with app.app_context():
        _enable_calendar(user.id)
        vehicle = _vehicle(user.id)
        entry = _tax(user.id, vehicle.id)
        entry_id = entry.id

    resp = client.delete(f'{TAXES_URL}/{entry_id}', headers=auth_headers(user.id))

    assert resp.status_code == 200
    assert ('tax', entry_id, 'delete') in synced
    with app.app_context():
        db.session.remove()
        assert db.session.get(TaxEntry, entry_id) is None


def test_cancelling_a_recurring_tax_syncs(app, client, user, auth_headers, synced):
    with app.app_context():
        _enable_calendar(user.id)
        vehicle = _vehicle(user.id)
        entry = _tax(user.id, vehicle.id, recurring=True, recurrence_type='annual',
                     next_due_date=TODAY + timedelta(days=40))
        entry_id = entry.id

    resp = client.post(f'{TAXES_URL}/{entry_id}/cancel', headers=auth_headers(user.id))

    assert resp.status_code == 200, resp.data[:200]
    assert ('tax', entry_id, 'update') in synced


def test_creating_a_tax_still_syncs(app, client, user, auth_headers, synced):
    """Regression guard: the pre-existing create sync survived the refactor."""
    with app.app_context():
        _enable_calendar(user.id)
        vehicle = _vehicle(user.id)
        vehicle_id = vehicle.id

    resp = client.post(TAXES_URL, json={
        'vehicle_id': vehicle_id, 'tax_type': 'road_tax', 'amount': 10,
    }, headers=auth_headers(user.id))

    assert resp.status_code == 201
    assert [action for _t, _i, action in synced] == ['create']


# --- parking -------------------------------------------------------------------

def test_updating_parking_syncs(app, client, user, auth_headers, synced):
    with app.app_context():
        _enable_calendar(user.id)
        vehicle = _vehicle(user.id, name='Golf')
        entry = _parking(user.id, vehicle.id)
        entry_id = entry.id

    resp = client.put(f'{PARKING_URL}/{entry_id}', json={'amount': 55},
                      headers=auth_headers(user.id))

    assert resp.status_code == 200, resp.data[:200]
    assert ('parking', entry_id, 'update') in synced


def test_deleting_parking_syncs_a_delete(app, client, user, auth_headers, synced):
    with app.app_context():
        _enable_calendar(user.id)
        vehicle = _vehicle(user.id, name='Golf')
        entry = _parking(user.id, vehicle.id)
        entry_id = entry.id

    resp = client.delete(f'{PARKING_URL}/{entry_id}', headers=auth_headers(user.id))

    assert resp.status_code == 200
    assert ('parking', entry_id, 'delete') in synced


def test_cancelling_recurring_parking_syncs(app, client, user, auth_headers, synced):
    with app.app_context():
        _enable_calendar(user.id)
        vehicle = _vehicle(user.id, name='Golf')
        entry = _parking(user.id, vehicle.id, recurring=True,
                         recurrence_type='monthly',
                         next_due_date=TODAY + timedelta(days=20))
        entry_id = entry.id

    resp = client.post(f'{PARKING_URL}/{entry_id}/cancel',
                       headers=auth_headers(user.id))

    assert resp.status_code == 200, resp.data[:200]
    assert ('parking', entry_id, 'update') in synced


# --- the guards ----------------------------------------------------------------

def test_no_sync_when_calendar_disabled(app, client, user, auth_headers, synced):
    """calendar_enabled is off by default — nothing should be dispatched."""
    with app.app_context():
        vehicle = _vehicle(user.id)
        entry = _tax(user.id, vehicle.id)
        entry_id = entry.id

    client.put(f'{TAXES_URL}/{entry_id}', json={'amount': 25},
               headers=auth_headers(user.id))
    client.delete(f'{TAXES_URL}/{entry_id}', headers=auth_headers(user.id))

    assert synced == []


def test_calendar_failure_does_not_break_the_write(app, client, user, auth_headers,
                                                   monkeypatch):
    """A CalDAV outage must not turn a successful save into a failed request."""
    def _explode(*args, **kwargs):
        raise RuntimeError('CalDAV unreachable')

    monkeypatch.setattr(calendar_service, 'sync_entry_to_calendar', _explode)

    with app.app_context():
        _enable_calendar(user.id)
        vehicle = _vehicle(user.id)
        entry = _tax(user.id, vehicle.id)
        entry_id = entry.id

    resp = client.put(f'{TAXES_URL}/{entry_id}', json={'amount': 99},
                      headers=auth_headers(user.id))
    assert resp.status_code == 200, 'a calendar outage broke the edit'

    delete_resp = client.delete(f'{TAXES_URL}/{entry_id}',
                                headers=auth_headers(user.id))
    assert delete_resp.status_code == 200
    with app.app_context():
        db.session.remove()
        assert db.session.get(TaxEntry, entry_id) is None, 'the row survived'


def test_failed_delete_sync_still_removes_the_row(app, client, user, auth_headers):
    """Documents the accepted trade-off: the DB is the source of truth."""
    from app.models import User
    with app.app_context():
        _enable_calendar(user.id)
        vehicle = _vehicle(user.id, name='Golf')
        entry = _parking(user.id, vehicle.id)
        entry_id = entry.id
        assert db.session.get(User, user.id).calendar_enabled is True

    resp = client.delete(f'{PARKING_URL}/{entry_id}', headers=auth_headers(user.id))
    assert resp.status_code == 200
    with app.app_context():
        db.session.remove()
        assert db.session.get(ParkingEntry, entry_id) is None

"""Step 4 — PUT /parking/<id> recurrence transitions + the quarterly create fix.

Mirrors test_tax_recurrence_transitions.py. Parking additionally reschedules
when `permit_expires` moves (renewing a permit shifts the whole series) and,
until now, could not have its `next_due_date` edited at all: the alias map had
no key for it even though `date_columns` listed it.

The create path also fell through an inline branch chain to "annual" for the
'quarterly' option the form offers (AddVehicleParking.jsx), so a quarterly
permit's first renewal landed nine months late.
"""

from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from app import db
from app.models import Vehicle, ParkingEntry

TODAY = date.today()
PARKING_URL = '/api/parking'


def _vehicle(user_id, name='Golf'):
    vehicle = Vehicle(user_id=user_id, name=name, make='VW', model='Golf')
    db.session.add(vehicle)
    db.session.commit()
    db.session.refresh(vehicle)
    return vehicle


def _permit(user_id, vehicle_id, **kwargs):
    fields = dict(
        user_id=user_id, vehicle_id=vehicle_id,
        date=TODAY - relativedelta(months=1), amount=40, currency='EUR',
        parking_type='permit', title='City Permit', location='City Centre',
        recurring=False, recurrence_type=None, next_due_date=None,
        permit_expires=None,
    )
    fields.update(kwargs)
    entry = ParkingEntry(**fields)
    db.session.add(entry)
    db.session.commit()
    db.session.refresh(entry)
    return entry


def _reload(app, entry_id):
    with app.app_context():
        db.session.remove()
        return db.session.get(ParkingEntry, entry_id)


# --- create: quarterly -----------------------------------------------------------

def test_quarterly_permit_schedules_three_months_out(app, client, user, auth_headers):
    """The form offers 'quarterly'; create used to fall through to annual."""
    expires = TODAY + relativedelta(months=1)
    with app.app_context():
        vehicle = _vehicle(user.id)
        vehicle_id = vehicle.id

    resp = client.post(PARKING_URL, json={
        'vehicle_id': vehicle_id, 'parking_type': 'permit',
        'location': 'City Centre', 'amount': 40,
        'recurring': True, 'recurrence_type': 'quarterly',
        'permit_expires': expires.isoformat(),
    }, headers=auth_headers(user.id))

    assert resp.status_code == 201, resp.data[:200]
    entry = resp.get_json()['entry']
    assert entry['next_due_date'] == (expires + relativedelta(months=3)).isoformat()


def test_semi_annual_permit_is_supported(app, client, user, auth_headers):
    """_recurrence_step covers semi_annual; the old chain did not."""
    expires = TODAY + relativedelta(months=1)
    with app.app_context():
        vehicle = _vehicle(user.id)
        vehicle_id = vehicle.id

    resp = client.post(PARKING_URL, json={
        'vehicle_id': vehicle_id, 'parking_type': 'permit', 'amount': 40,
        'recurring': True, 'recurrence_type': 'semi_annual',
        'permit_expires': expires.isoformat(),
    }, headers=auth_headers(user.id))

    assert resp.get_json()['entry']['next_due_date'] == \
        (expires + relativedelta(months=6)).isoformat()


def test_monthly_permit_unchanged(app, client, user, auth_headers):
    """Regression guard: the frequencies the old chain got right still work."""
    expires = TODAY + relativedelta(months=1)
    with app.app_context():
        vehicle = _vehicle(user.id)
        vehicle_id = vehicle.id

    resp = client.post(PARKING_URL, json={
        'vehicle_id': vehicle_id, 'parking_type': 'permit', 'amount': 40,
        'recurring': True, 'recurrence_type': 'monthly',
        'permit_expires': expires.isoformat(),
    }, headers=auth_headers(user.id))

    assert resp.get_json()['entry']['next_due_date'] == \
        (expires + relativedelta(months=1)).isoformat()


# --- update: next_due_date is editable at all ------------------------------------

def test_next_due_date_can_be_edited(app, client, user, auth_headers):
    """"Update date" — previously impossible: no alias mapped it."""
    chosen = TODAY + relativedelta(months=4)
    with app.app_context():
        vehicle = _vehicle(user.id)
        entry = _permit(user.id, vehicle.id, recurring=True,
                        recurrence_type='monthly',
                        next_due_date=TODAY + relativedelta(months=1))
        entry_id = entry.id

    resp = client.put(f'{PARKING_URL}/{entry_id}',
                      json={'next_due_date': chosen.isoformat()},
                      headers=auth_headers(user.id))
    assert resp.status_code == 200, resp.data[:200]
    assert resp.get_json()['entry']['next_due_date'] == chosen.isoformat()
    assert _reload(app, entry_id).next_due_date == chosen


# --- update: transitions ---------------------------------------------------------

def test_turning_recurring_off_clears_next_due_date(app, client, user, auth_headers):
    with app.app_context():
        vehicle = _vehicle(user.id)
        entry = _permit(user.id, vehicle.id, recurring=True,
                        recurrence_type='monthly',
                        next_due_date=TODAY + relativedelta(months=1))
        entry_id = entry.id

    client.put(f'{PARKING_URL}/{entry_id}', json={'recurring': False},
               headers=auth_headers(user.id))

    assert _reload(app, entry_id).next_due_date is None


def test_turning_recurring_on_schedules_a_future_date(app, client, user, auth_headers):
    with app.app_context():
        vehicle = _vehicle(user.id)
        entry = _permit(user.id, vehicle.id, date=TODAY - relativedelta(years=2))
        entry_id = entry.id

    client.put(f'{PARKING_URL}/{entry_id}',
               json={'recurring': True, 'recurrence_type': 'monthly'},
               headers=auth_headers(user.id))

    entry = _reload(app, entry_id)
    assert entry.next_due_date is not None
    assert entry.next_due_date > TODAY


def test_changing_frequency_reschedules(app, client, user, auth_headers):
    far_off = TODAY + relativedelta(months=11)
    with app.app_context():
        vehicle = _vehicle(user.id)
        entry = _permit(user.id, vehicle.id, recurring=True,
                        recurrence_type='annual', next_due_date=far_off,
                        permit_expires=TODAY)
        entry_id = entry.id

    client.put(f'{PARKING_URL}/{entry_id}', json={'recurrence_type': 'monthly'},
               headers=auth_headers(user.id))

    entry = _reload(app, entry_id)
    assert entry.next_due_date != far_off
    assert TODAY < entry.next_due_date <= TODAY + relativedelta(months=1)


def test_moving_permit_expiry_reschedules_the_series(app, client, user, auth_headers):
    """Renewing a permit shifts when the next renewal is due."""
    new_expiry = TODAY + relativedelta(months=6)
    with app.app_context():
        vehicle = _vehicle(user.id)
        entry = _permit(user.id, vehicle.id, recurring=True,
                        recurrence_type='monthly', permit_expires=TODAY,
                        next_due_date=TODAY + relativedelta(days=1))
        entry_id = entry.id

    client.put(f'{PARKING_URL}/{entry_id}',
               json={'permit_expires': new_expiry.isoformat()},
               headers=auth_headers(user.id))

    entry = _reload(app, entry_id)
    assert entry.permit_expires == new_expiry
    assert entry.next_due_date == new_expiry + relativedelta(months=1)


def test_string_false_is_not_truthy(app, client, user, auth_headers):
    with app.app_context():
        vehicle = _vehicle(user.id)
        entry = _permit(user.id, vehicle.id, recurring=True,
                        recurrence_type='monthly',
                        next_due_date=TODAY + relativedelta(months=1))
        entry_id = entry.id

    client.put(f'{PARKING_URL}/{entry_id}', json={'recurring': ''},
               headers=auth_headers(user.id))

    entry = _reload(app, entry_id)
    assert entry.recurring is False
    assert entry.next_due_date is None


# --- invariants ------------------------------------------------------------------

def test_editing_other_fields_leaves_the_schedule_alone(app, client, user, auth_headers):
    scheduled = TODAY + relativedelta(months=7)
    with app.app_context():
        vehicle = _vehicle(user.id)
        entry = _permit(user.id, vehicle.id, recurring=True,
                        recurrence_type='annual', permit_expires=TODAY,
                        next_due_date=scheduled)
        entry_id = entry.id

    resp = client.put(
        f'{PARKING_URL}/{entry_id}',
        json={'notes': 'renewed at the kiosk', 'amount': 45.5,
              'recurring': True, 'recurrence_type': 'annual',
              'permit_expires': TODAY.isoformat()},
        headers=auth_headers(user.id),
    )
    assert resp.status_code == 200, resp.data[:200]

    entry = _reload(app, entry_id)
    assert entry.next_due_date == scheduled, 'an unrelated edit moved the series'
    assert float(entry.amount) == 45.5


def test_explicit_next_due_date_wins_over_recompute(app, client, user, auth_headers):
    chosen = TODAY + relativedelta(months=9)
    with app.app_context():
        vehicle = _vehicle(user.id)
        entry = _permit(user.id, vehicle.id)
        entry_id = entry.id

    client.put(f'{PARKING_URL}/{entry_id}',
               json={'recurring': True, 'recurrence_type': 'monthly',
                     'next_due_date': chosen.isoformat()},
               headers=auth_headers(user.id))

    assert _reload(app, entry_id).next_due_date == chosen


def test_fine_edit_does_not_gain_a_schedule(app, client, user, auth_headers):
    """A fine is never a recurring permit (create enforces it); edits too."""
    with app.app_context():
        vehicle = _vehicle(user.id)
        entry = _permit(user.id, vehicle.id, parking_type='fine',
                        fine_status='pending', title='Parking fine')
        entry_id = entry.id

    client.put(f'{PARKING_URL}/{entry_id}', json={'fine_status': 'paid'},
               headers=auth_headers(user.id))

    entry = _reload(app, entry_id)
    assert entry.fine_status == 'paid'
    assert entry.next_due_date is None
    assert entry.recurring is False


def test_cross_user_update_still_forbidden(app, client, user, auth_headers):
    from app.models import User
    with app.app_context():
        vehicle = _vehicle(user.id)
        entry = _permit(user.id, vehicle.id, recurring=True,
                        recurrence_type='monthly')
        entry_id = entry.id

        intruder = User(username='pk-intruder', email='pk-intruder@example.com',
                        is_active=True)
        intruder.set_password('StrongPass123!')
        db.session.add(intruder)
        db.session.commit()
        intruder_id = intruder.id

    resp = client.put(f'{PARKING_URL}/{entry_id}', json={'recurring': False},
                      headers=auth_headers(intruder_id))
    assert resp.status_code == 404
    assert _reload(app, entry_id).recurring is True

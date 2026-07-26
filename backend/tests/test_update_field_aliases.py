"""Tests for F18 — PUT field-name rot fix.

The Add/Edit forms submit legacy field names (entry_date, mileage, cost,
shop_name, next_service_date, is_recurring, recurrence_pattern, notes,
repeat_interval, …). Historically the update routes setattr'd those names
verbatim, creating transient attributes that were silently discarded on
commit — edits returned 200 but changed nothing. These tests prove every
alias now lands on the real column and round-trips through GET.
"""

from datetime import date, timedelta

from app import db
from app.models import Vehicle, ServiceEntry, RepairEntry, Reminder, TaxEntry, ParkingEntry

TODAY = date.today()


def _mk_vehicle(user_id, mileage=50000):
    v = Vehicle(user_id=user_id, name='Leaf', make='Nissan', model='Leaf',
                current_mileage=mileage, distance_unit='km')
    db.session.add(v)
    db.session.commit()
    db.session.refresh(v)
    return v


def test_service_edit_persists_date_odometer_and_next_due(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        vid = v.id

    created = client.post('/api/services', json={
        'vehicle_id': vid, 'service_types': ['oil_change'],
        'date': TODAY.isoformat(), 'mileage': 50000, 'total_cost': 80,
    }, headers=auth_headers(user.id))
    assert created.status_code == 201
    sid = created.get_json()['entry']['id']

    new_date = (TODAY - timedelta(days=3)).isoformat()
    next_due = (TODAY + timedelta(days=180)).isoformat()
    resp = client.put(f'/api/services/{sid}', json={
        'date': new_date,
        'mileage': 52000,
        'next_due_date': next_due,
        'next_service_mileage': 62000,
        'shop_name': 'Nissan Main Dealer',
        'provider_location': '1 Electric Ave',
        'notes': 'edited',
    }, headers=auth_headers(user.id))
    assert resp.status_code == 200

    # Round-trip through GET — the edit must be visible, not just 200'd.
    got = client.get(f'/api/services/{sid}', headers=auth_headers(user.id)).get_json()
    assert got['date'] == new_date
    assert got['odometer'] == 52000
    assert got['next_due_date'] == next_due
    assert got['next_due_mileage'] == 62000
    assert got['garage_name'] == 'Nissan Main Dealer'
    assert got['notes'] == 'edited'

    with app.app_context():
        s = db.session.get(ServiceEntry, sid)
        assert s.date.isoformat() == new_date
        assert s.odometer == 52000
        # Mileage bump mirrored from create: 52000 > 50000.
        assert db.session.get(Vehicle, vid).current_mileage == 52000
        # No transient legacy attributes left behind.
        assert not hasattr(type(s), 'entry_date')


def test_service_edit_never_lowers_vehicle_mileage(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id, mileage=90000)
        vid = v.id
    created = client.post('/api/services', json={
        'vehicle_id': vid, 'service_types': ['inspection'], 'total_cost': 50,
    }, headers=auth_headers(user.id))
    sid = created.get_json()['entry']['id']

    client.put(f'/api/services/{sid}', json={'mileage': 40000},
               headers=auth_headers(user.id))
    with app.app_context():
        assert db.session.get(Vehicle, vid).current_mileage == 90000


def test_repair_edit_persists_date_odometer_and_cost(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        vid = v.id

    created = client.post('/api/repairs', json={
        'vehicle_id': vid, 'repair_types': ['brakes'],
        'date': TODAY.isoformat(), 'mileage': 50000, 'total_cost': 200,
    }, headers=auth_headers(user.id))
    assert created.status_code == 201
    rid = created.get_json()['entry']['id']

    new_date = (TODAY - timedelta(days=7)).isoformat()
    resp = client.put(f'/api/repairs/{rid}', json={
        'entry_date': new_date,          # legacy alias for date
        'mileage': 53000,
        'cost': 350,                     # legacy alias for amount
        'shop_name': 'BrakeFix',
        'severity': 'high',
    }, headers=auth_headers(user.id))
    assert resp.status_code == 200

    got = client.get(f'/api/repairs/{rid}', headers=auth_headers(user.id)).get_json()
    assert got['date'] == new_date
    assert got['odometer'] == 53000
    assert got['amount'] == 350
    assert got['provider'] == 'BrakeFix'
    assert got['garage_name'] == 'BrakeFix'
    assert got['severity'] == 'high'

    with app.app_context():
        r = db.session.get(RepairEntry, rid)
        assert float(r.amount) == 350
        assert db.session.get(Vehicle, vid).current_mileage == 53000


# --- F56: workshop record — work order #, labor hours, root cause ------------

def test_service_roundtrips_work_order_and_labor_hours(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        vid = v.id

    created = client.post('/api/services', json={
        'vehicle_id': vid, 'service_types': ['oil_change'],
        'date': TODAY.isoformat(), 'total_cost': 80,
        'work_order_number': 'WO-2026-118', 'labor_hours': 2.5,
    }, headers=auth_headers(user.id))
    assert created.status_code == 201
    entry = created.get_json()['entry']
    # Present on create response (proves both the constructor and to_dict).
    assert entry['work_order_number'] == 'WO-2026-118'
    assert entry['labor_hours'] == 2.5
    sid = entry['id']

    resp = client.put(f'/api/services/{sid}', json={
        'work_order_number': 'WO-2026-999', 'labor_hours': 3,
    }, headers=auth_headers(user.id))
    assert resp.status_code == 200

    got = client.get(f'/api/services/{sid}', headers=auth_headers(user.id)).get_json()
    assert got['work_order_number'] == 'WO-2026-999'
    assert got['labor_hours'] == 3.0


def test_repair_roundtrips_root_cause_and_labor_hours(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        vid = v.id

    created = client.post('/api/repairs', json={
        'vehicle_id': vid, 'repair_types': ['brakes'],
        'date': TODAY.isoformat(), 'total_cost': 200,
        'root_cause': 'Seized caliper piston', 'labor_hours': 1.5,
    }, headers=auth_headers(user.id))
    assert created.status_code == 201
    entry = created.get_json()['entry']
    assert entry['root_cause'] == 'Seized caliper piston'
    assert entry['labor_hours'] == 1.5
    rid = entry['id']

    resp = client.put(f'/api/repairs/{rid}', json={
        'root_cause': 'Corroded brake line', 'labor_hours': 2,
    }, headers=auth_headers(user.id))
    assert resp.status_code == 200

    got = client.get(f'/api/repairs/{rid}', headers=auth_headers(user.id)).get_json()
    assert got['root_cause'] == 'Corroded brake line'
    assert got['labor_hours'] == 2.0


def test_reminder_edit_persists_recurrence_and_notify_flags(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        vid = v.id

    created = client.post('/api/reminders', json={
        'vehicle_id': vid, 'title': 'MOT',
        'due_date': (TODAY + timedelta(days=30)).isoformat(),
    }, headers=auth_headers(user.id))
    assert created.status_code == 201
    rid = created.get_json()['reminder']['id']

    # Legacy alias names (the pre-F18 update list) must now persist.
    resp = client.put(f'/api/reminders/{rid}', json={
        'is_recurring': True,
        'recurrence_pattern': 'monthly',
        'recurrence_interval': 2,
        'notify_via_push': False,
        'notify_via_email': False,
        'sync_to_calendar': True,
        'notes': 'check tyres too',
    }, headers=auth_headers(user.id))
    assert resp.status_code == 200
    got = resp.get_json()['reminder']
    assert got['recurring'] is True
    assert got['frequency'] == 'monthly'
    assert got['frequency_value'] == 2
    assert got['notify_push'] is False
    assert got['notify_email'] is False
    assert got['calendar_sync'] is True
    assert got['description'] == 'check tyres too'

    # Canonical names work too (and win when both are sent).
    resp = client.put(f'/api/reminders/{rid}', json={
        'recurrence_pattern': 'monthly', 'frequency': 'yearly',
        'notify_push': True,
    }, headers=auth_headers(user.id))
    got = resp.get_json()['reminder']
    assert got['frequency'] == 'yearly'
    assert got['notify_push'] is True

    with app.app_context():
        rem = db.session.get(Reminder, rid)
        assert rem.recurring is True and rem.frequency == 'yearly'
        # 'status' / 'recurrence_unit' were never columns — nothing leaked.
        assert not hasattr(type(rem), 'status')


def test_reminder_repeat_interval_maps_to_recurrence(app, client, user, auth_headers):
    """The actual UI 'Repeats' select round-trips create → edit → GET."""
    with app.app_context():
        v = _mk_vehicle(user.id)
        vid = v.id

    created = client.post('/api/reminders', json={
        'vehicle_id': vid, 'title': 'Insurance',
        'due_date': (TODAY + timedelta(days=60)).isoformat(),
        'repeat_interval': '6_months',
    }, headers=auth_headers(user.id))
    got = created.get_json()['reminder']
    assert got['recurring'] is True
    assert got['frequency'] == 'monthly'
    assert got['frequency_value'] == 6
    assert got['repeat_interval'] == '6_months'
    rid = got['id']

    # Edit to yearly.
    got = client.put(f'/api/reminders/{rid}', json={'repeat_interval': '1_year'},
                     headers=auth_headers(user.id)).get_json()['reminder']
    assert got['frequency'] == 'yearly' and got['frequency_value'] == 1
    assert got['repeat_interval'] == '1_year'

    # Clear to "does not repeat".
    got = client.put(f'/api/reminders/{rid}', json={'repeat_interval': ''},
                     headers=auth_headers(user.id)).get_json()['reminder']
    assert got['recurring'] is False
    assert got['frequency'] is None
    assert got['repeat_interval'] == ''

    # Unknown tokens are ignored, not stored.
    got = client.put(f'/api/reminders/{rid}', json={'repeat_interval': 'weekly_ish'},
                     headers=auth_headers(user.id)).get_json()['reminder']
    assert got['recurring'] is False


# --- F41: taxes + parking (the two types F18 didn't cover) --------------------

def test_tax_edit_persists_date_amount_and_due_date(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        vid = v.id

    created = client.post('/api/taxes', json={
        'vehicle_id': vid, 'tax_type': 'road_tax',
        'date': TODAY.isoformat(), 'amount': 100, 'status': 'paid',
    }, headers=auth_headers(user.id))
    assert created.status_code == 201
    tid = created.get_json()['entry']['id']

    new_date = (TODAY - timedelta(days=4)).isoformat()
    valid_until = (TODAY + timedelta(days=365)).isoformat()
    resp = client.put(f'/api/taxes/{tid}', json={
        'cost': 200,                 # legacy alias for amount
        'valid_until': valid_until,  # legacy alias for due_date
        'entry_date': new_date,      # legacy alias for date
        'reference_number': 'RT-2027',
        'status': 'pending',
    }, headers=auth_headers(user.id))
    assert resp.status_code == 200

    got = client.get(f'/api/taxes/{tid}', headers=auth_headers(user.id)).get_json()
    assert got['amount'] == 200
    assert got['date'] == new_date
    assert got['due_date'] == valid_until
    assert got['reference_number'] == 'RT-2027'
    assert got['status'] == 'pending'

    with app.app_context():
        tx = db.session.get(TaxEntry, tid)
        assert float(tx.amount) == 200
        assert tx.date.isoformat() == new_date
        assert tx.due_date.isoformat() == valid_until
        # No phantom legacy attributes leaked onto the column set.
        assert not hasattr(type(tx), 'valid_from')
        assert not hasattr(type(tx), 'payment_method')


def test_parking_edit_persists_date_amount_location(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        vid = v.id

    created = client.post('/api/parking', json={
        'vehicle_id': vid, 'parking_type': 'street',
        'date': TODAY.isoformat(), 'amount': 5, 'location': 'High St',
    }, headers=auth_headers(user.id))
    assert created.status_code == 201
    pid = created.get_json()['entry']['id']

    new_date = (TODAY - timedelta(days=2)).isoformat()
    permit_exp = (TODAY + timedelta(days=30)).isoformat()
    resp = client.put(f'/api/parking/{pid}', json={
        'cost': 12,                          # legacy alias for amount
        'location_name': 'Multi-storey B2',  # legacy alias for location
        'entry_date': new_date,              # legacy alias for date
        'parking_type': 'permit',
        'permit_valid_until': permit_exp,    # legacy alias for permit_expires
        'start_time': '09:30',
    }, headers=auth_headers(user.id))
    assert resp.status_code == 200

    got = client.get(f'/api/parking/{pid}', headers=auth_headers(user.id)).get_json()
    assert got['amount'] == 12
    assert got['location'] == 'Multi-storey B2'
    assert got['date'] == new_date
    assert got['parking_type'] == 'permit'
    assert got['permit_expires'] == permit_exp
    assert got['start_datetime'] and got['start_datetime'][11:16] == '09:30'

    with app.app_context():
        pk = db.session.get(ParkingEntry, pid)
        assert float(pk.amount) == 12
        assert pk.location == 'Multi-storey B2'
        assert pk.permit_expires.isoformat() == permit_exp
        assert not hasattr(type(pk), 'location_name')
        assert not hasattr(type(pk), 'permit_valid_until')

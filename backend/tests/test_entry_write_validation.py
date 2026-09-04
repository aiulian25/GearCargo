"""Step 5 — malformed dates/amounts must 400, not 500.

R2 guarded the vehicle and identity write paths. The tax and parking routes
parse fifteen date fields plus an amount between them and guarded none of them,
so `datetime.fromisoformat('garbage')` escaped the handler as a 500 — the same
bug class F41 fixed for times only.

Every response is asserted to carry the localized `message_key` the frontend
renders (`validation.invalidDate` / `validation.invalidNumber`, already present
in en/ro/es), and the entry is asserted UNCHANGED — a rejected write must not
half-apply.
"""

import pytest

from app import db
from app.models import Vehicle, TaxEntry, ParkingEntry
from app.utils.entryparse import (
    InvalidFieldError, parse_amount, parse_iso_date,
)
from datetime import date

TODAY = date.today()
TAXES_URL = '/api/taxes'
PARKING_URL = '/api/parking'

# '' is deliberately absent: an empty value means "no change" for the NOT NULL
# `date` column and "clear it" for the nullable ones — not "malformed".
BAD_DATES = ['garbage', '2026-13-45', '32/01/2026', 'null', '2026-02-30']
# Falsy containers are absent too: create's `total_cost or cost or amount or 0`
# chain treats them as "not provided", which is pre-existing intent.
BAD_AMOUNTS = ['abc', 'ten euros']


def _vehicle(user_id, name='Qashqai'):
    vehicle = Vehicle(user_id=user_id, name=name, make='Nissan', model='Qashqai')
    db.session.add(vehicle)
    db.session.commit()
    db.session.refresh(vehicle)
    return vehicle


# --- the helper itself ---------------------------------------------------------

@pytest.mark.parametrize('raw', ['garbage', '2026-13-45', None, '', 42.5, []])
def test_parse_iso_date_raises_typed_error(raw):
    with pytest.raises(InvalidFieldError) as excinfo:
        parse_iso_date(raw)
    assert excinfo.value.message_key == 'validation.invalidDate'


@pytest.mark.parametrize('raw', ['abc', None, {}, 'ten'])
def test_parse_amount_raises_typed_error(raw):
    with pytest.raises(InvalidFieldError) as excinfo:
        parse_amount(raw)
    assert excinfo.value.message_key == 'validation.invalidNumber'


def test_parse_helpers_accept_valid_input():
    assert parse_iso_date('2026-03-04') == date(2026, 3, 4)
    assert parse_iso_date('2026-03-04T10:30:00Z') == date(2026, 3, 4)
    assert parse_amount('12.50') == 12.5
    assert parse_amount(7) == 7.0


# --- taxes: create -------------------------------------------------------------

@pytest.mark.parametrize('field', ['date', 'entry_date', 'valid_until',
                                   'due_date', 'next_due_date'])
def test_create_tax_rejects_bad_date(app, client, user, auth_headers, field):
    with app.app_context():
        vehicle = _vehicle(user.id)
        vehicle_id = vehicle.id
        before = TaxEntry.query.count()

    resp = client.post(TAXES_URL, json={
        'vehicle_id': vehicle_id, 'tax_type': 'road_tax', 'amount': 10,
        field: 'garbage',
    }, headers=auth_headers(user.id))

    assert resp.status_code == 400, resp.data[:200]
    assert resp.get_json()['message_key'] == 'validation.invalidDate'
    with app.app_context():
        assert TaxEntry.query.count() == before, 'a rejected create still inserted'


@pytest.mark.parametrize('bad', BAD_AMOUNTS)
def test_create_tax_rejects_bad_amount(app, client, user, auth_headers, bad):
    with app.app_context():
        vehicle = _vehicle(user.id)
        vehicle_id = vehicle.id

    resp = client.post(TAXES_URL, json={
        'vehicle_id': vehicle_id, 'tax_type': 'road_tax', 'amount': bad,
    }, headers=auth_headers(user.id))

    assert resp.status_code == 400, resp.data[:200]
    assert resp.get_json()['message_key'] == 'validation.invalidNumber'


def test_create_tax_still_works_with_valid_input(app, client, user, auth_headers):
    with app.app_context():
        vehicle = _vehicle(user.id)
        vehicle_id = vehicle.id

    resp = client.post(TAXES_URL, json={
        'vehicle_id': vehicle_id, 'tax_type': 'road_tax', 'amount': '15.50',
        'date': TODAY.isoformat(), 'valid_until': TODAY.isoformat(),
    }, headers=auth_headers(user.id))

    assert resp.status_code == 201, resp.data[:200]
    assert resp.get_json()['entry']['amount'] == 15.5


# --- taxes: update -------------------------------------------------------------

@pytest.mark.parametrize('bad', BAD_DATES)
def test_update_tax_rejects_bad_date_and_changes_nothing(app, client, user,
                                                         auth_headers, bad):
    with app.app_context():
        vehicle = _vehicle(user.id)
        entry = TaxEntry(user_id=user.id, vehicle_id=vehicle.id, date=TODAY,
                         amount=15, tax_type='road_tax', title='Road Tax',
                         notes='original')
        db.session.add(entry)
        db.session.commit()
        entry_id = entry.id

    resp = client.put(f'{TAXES_URL}/{entry_id}',
                      json={'date': bad, 'notes': 'should not persist'},
                      headers=auth_headers(user.id))

    assert resp.status_code == 400, resp.data[:200]
    assert resp.get_json()['message_key'] == 'validation.invalidDate'

    with app.app_context():
        db.session.remove()
        unchanged = db.session.get(TaxEntry, entry_id)
        assert unchanged.date == TODAY
        assert unchanged.notes == 'original', 'a rejected update half-applied'


def test_update_tax_rejects_bad_amount(app, client, user, auth_headers):
    with app.app_context():
        vehicle = _vehicle(user.id)
        entry = TaxEntry(user_id=user.id, vehicle_id=vehicle.id, date=TODAY,
                         amount=15, tax_type='road_tax', title='Road Tax')
        db.session.add(entry)
        db.session.commit()
        entry_id = entry.id

    resp = client.put(f'{TAXES_URL}/{entry_id}', json={'amount': 'abc'},
                      headers=auth_headers(user.id))

    assert resp.status_code == 400
    assert resp.get_json()['message_key'] == 'validation.invalidNumber'
    with app.app_context():
        db.session.remove()
        assert float(db.session.get(TaxEntry, entry_id).amount) == 15.0


# --- parking: create -----------------------------------------------------------

@pytest.mark.parametrize('field', ['date', 'entry_date', 'permit_valid_until',
                                   'permit_expires', 'next_due_date'])
def test_create_parking_rejects_bad_date(app, client, user, auth_headers, field):
    with app.app_context():
        vehicle = _vehicle(user.id, name='Golf')
        vehicle_id = vehicle.id
        before = ParkingEntry.query.count()

    resp = client.post(PARKING_URL, json={
        'vehicle_id': vehicle_id, 'parking_type': 'permit', 'amount': 10,
        field: 'garbage',
    }, headers=auth_headers(user.id))

    assert resp.status_code == 400, resp.data[:200]
    assert resp.get_json()['message_key'] == 'validation.invalidDate'
    with app.app_context():
        assert ParkingEntry.query.count() == before


def test_create_parking_rejects_bad_amount(app, client, user, auth_headers):
    with app.app_context():
        vehicle = _vehicle(user.id, name='Golf')
        vehicle_id = vehicle.id

    resp = client.post(PARKING_URL, json={
        'vehicle_id': vehicle_id, 'parking_type': 'hourly', 'amount': 'abc',
    }, headers=auth_headers(user.id))

    assert resp.status_code == 400
    assert resp.get_json()['message_key'] == 'validation.invalidNumber'


def test_create_parking_still_works_with_valid_input(app, client, user, auth_headers):
    with app.app_context():
        vehicle = _vehicle(user.id, name='Golf')
        vehicle_id = vehicle.id

    resp = client.post(PARKING_URL, json={
        'vehicle_id': vehicle_id, 'parking_type': 'hourly', 'amount': '4.25',
        'date': TODAY.isoformat(), 'start_time': '08:30', 'end_time': '10:00',
    }, headers=auth_headers(user.id))

    assert resp.status_code == 201, resp.data[:200]
    entry = resp.get_json()['entry']
    assert entry['amount'] == 4.25
    assert entry['start_datetime'] is not None


# --- parking: update -----------------------------------------------------------

@pytest.mark.parametrize('field', ['date', 'permit_expires', 'next_due_date'])
def test_update_parking_rejects_bad_date_and_changes_nothing(app, client, user,
                                                             auth_headers, field):
    with app.app_context():
        vehicle = _vehicle(user.id, name='Golf')
        entry = ParkingEntry(user_id=user.id, vehicle_id=vehicle.id, date=TODAY,
                             amount=40, parking_type='permit', notes='original')
        db.session.add(entry)
        db.session.commit()
        entry_id = entry.id

    resp = client.put(f'{PARKING_URL}/{entry_id}',
                      json={field: 'garbage', 'notes': 'should not persist'},
                      headers=auth_headers(user.id))

    assert resp.status_code == 400, resp.data[:200]
    assert resp.get_json()['message_key'] == 'validation.invalidDate'

    with app.app_context():
        db.session.remove()
        unchanged = db.session.get(ParkingEntry, entry_id)
        assert unchanged.date == TODAY
        assert unchanged.notes == 'original'


def test_update_parking_rejects_bad_amount(app, client, user, auth_headers):
    with app.app_context():
        vehicle = _vehicle(user.id, name='Golf')
        entry = ParkingEntry(user_id=user.id, vehicle_id=vehicle.id, date=TODAY,
                             amount=40, parking_type='permit')
        db.session.add(entry)
        db.session.commit()
        entry_id = entry.id

    resp = client.put(f'{PARKING_URL}/{entry_id}', json={'amount': 'abc'},
                      headers=auth_headers(user.id))

    assert resp.status_code == 400
    assert resp.get_json()['message_key'] == 'validation.invalidNumber'
    with app.app_context():
        db.session.remove()
        assert float(db.session.get(ParkingEntry, entry_id).amount) == 40.0


def test_clearing_a_nullable_date_is_still_allowed(app, client, user, auth_headers):
    """An empty value clears a nullable date — it is not 'malformed'."""
    with app.app_context():
        vehicle = _vehicle(user.id, name='Golf')
        entry = ParkingEntry(user_id=user.id, vehicle_id=vehicle.id, date=TODAY,
                             amount=40, parking_type='permit',
                             permit_expires=TODAY)
        db.session.add(entry)
        db.session.commit()
        entry_id = entry.id

    resp = client.put(f'{PARKING_URL}/{entry_id}', json={'permit_expires': None},
                      headers=auth_headers(user.id))

    assert resp.status_code == 200, resp.data[:200]
    with app.app_context():
        db.session.remove()
        assert db.session.get(ParkingEntry, entry_id).permit_expires is None


# ── Step 12: parse_optional_int — the shared coercion for nullable int columns ──
# Every odometer / mileage / warranty_months / quantity field on the entry write
# paths is a nullable INTEGER that routes currently assign straight from JSON.
# This is the one place that turns "whatever the client sent" into either an int
# the DB can store or a typed 400.

from app.utils.entryparse import INVALID_NUMBER_KEY, invalid_field_response, parse_optional_int


@pytest.mark.parametrize('raw, expected', [
    ('5000', 5000),          # HTML number inputs submit strings
    (5000, 5000),
    (5000.0, 5000),
    ('12000.7', 12000),      # truncated, never rounded up past a real reading
    (0, 0),                  # a real value, NOT "empty"
    ('0', 0),
    (-50, -50),              # negative is the caller's business, not the parser's
    (None, None),
    ('', None),
])
def test_parse_optional_int_accepts_the_shapes_clients_send(raw, expected):
    assert parse_optional_int(raw) == expected


@pytest.mark.parametrize('raw', [
    'abc', '12k', '5,000',   # free text and thousands separators
    {}, [], object(),
    True, False,             # a bool is not a reading; int(True) == 1 would be a lie
    'nan', 'inf', '-inf', '1e400',   # float() accepts these; int() then blows up
    '99999999999',           # valid int, but past PostgreSQL INTEGER
    99999999999,
    -99999999999,
])
def test_parse_optional_int_rejects_everything_else(raw):
    with pytest.raises(InvalidFieldError) as excinfo:
        parse_optional_int(raw)
    assert excinfo.value.message_key == INVALID_NUMBER_KEY


def test_parse_optional_int_keeps_the_int32_boundaries():
    """The limits themselves are valid — the guard must not be off by one."""
    assert parse_optional_int(2147483647) == 2147483647
    assert parse_optional_int(-2147483648) == -2147483648
    with pytest.raises(InvalidFieldError):
        parse_optional_int(2147483648)


def test_parse_optional_int_error_is_the_standard_400_payload():
    """Callers hand the exception straight to invalid_field_response, so the
    shape must match what every other guarded route returns."""
    try:
        parse_optional_int('abc', 'Mileage must be a number')
    except InvalidFieldError as exc:
        payload, status = invalid_field_response(exc)

    assert status == 400
    assert payload == {'error': 'Mileage must be a number',
                       'message_key': 'validation.invalidNumber'}

"""Regression tests for R4-10 / R4-11 on the service routes.

`create_service_entry` called `datetime.fromisoformat` on six client-supplied
dates with no guard, ran `float()` over `labor_cost`/`parts_cost`, and assigned
`amount`, `odometer`, `labor_hours` and `next_due_mileage` straight onto
Numeric / Integer columns. Any malformed value reached the driver as a 500.

The mileage bump then compared a raw string to `vehicle.current_mileage`
(`TypeError`), and compared against `None` when the vehicle had no mileage yet.

`update_service_entry` shared every gap and mutated the entry as its alias loop
ran, so a refused write half-applied. Each update rejection asserts the stored
entry is COMPLETELY unchanged.
"""

from datetime import date

import pytest

from app import db
from app.models import ServiceEntry, User, Vehicle


def _seed(app, current_mileage=1000):
    with app.app_context():
        user = User(username='svc', email='svc@example.com', is_active=True,
                    currency='GBP')
        user.set_password('StrongPass123!')
        db.session.add(user)
        db.session.commit()
        vehicle = Vehicle(user_id=user.id, name='Golf', current_mileage=current_mileage)
        db.session.add(vehicle)
        db.session.commit()
        return user.id, vehicle.id


def _valid_payload(vehicle_id, **overrides):
    payload = {
        'vehicle_id': vehicle_id,
        'service_types': ['oil_change'],
        'date': '2026-03-01',
        'total_cost': 120.50,
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize('field, bad_value, expected_key', [
    ('date', 'bad', 'validation.invalidDate'),
    ('date', '2026-13-40', 'validation.invalidDate'),
    ('entry_date', 12345, 'validation.invalidDate'),          # was: AttributeError
    ('next_service_date', 'bad', 'validation.invalidDate'),
    ('warranty_until', 'bad', 'validation.invalidDate'),
    ('mileage', 'abc', 'validation.invalidNumber'),
    ('odometer', {}, 'validation.invalidNumber'),
    ('total_cost', 'abc', 'validation.invalidNumber'),
    ('labor_cost', 'abc', 'validation.invalidNumber'),
    ('parts_cost', 'abc', 'validation.invalidNumber'),
    ('labor_hours', 'abc', 'validation.invalidNumber'),
    ('next_service_mileage', 'abc', 'validation.invalidNumber'),
    ('warranty_months', 'abc', 'validation.invalidNumber'),
    ('currency', 'EURO', 'validation.invalidCurrency'),      # the column is String(3)
])
def test_create_rejects_malformed_input(app, client, auth_headers, field, bad_value, expected_key):
    user_id, vehicle_id = _seed(app)
    payload = _valid_payload(vehicle_id, **{field: bad_value})
    if field in ('labor_cost', 'parts_cost'):
        payload.pop('total_cost')            # force the labor+parts sum branch
    if field == 'entry_date':
        payload.pop('date')                  # 'date' takes precedence over its alias

    response = client.post('/api/services', headers=auth_headers(user_id), json=payload)

    assert response.status_code == 400, response.get_json()   # was: 500
    assert response.get_json()['message_key'] == expected_key
    with app.app_context():
        assert ServiceEntry.query.count() == 0
        assert db.session.get(Vehicle, vehicle_id).current_mileage == 1000


def test_create_coerces_the_numeric_strings_a_form_submits(app, client, auth_headers):
    user_id, vehicle_id = _seed(app)

    response = client.post('/api/services', headers=auth_headers(user_id),
                           json=_valid_payload(vehicle_id, mileage='15000',
                                               next_service_mileage='30000',
                                               warranty_months='24',
                                               date='2026-03-01T09:30:00Z'))

    assert response.status_code == 201, response.get_json()
    with app.app_context():
        entry = ServiceEntry.query.one()
        assert entry.odometer == 15000
        assert entry.date == date(2026, 3, 1)                 # 'Z' suffix accepted
        assert entry.next_due_mileage == 30000
        assert entry.warranty_months == 24
        assert entry.currency == 'GBP'                        # the user's currency
        assert db.session.get(Vehicle, vehicle_id).current_mileage == 15000


def test_create_sums_labor_and_parts_when_no_total_is_given(app, client, auth_headers):
    user_id, vehicle_id = _seed(app)
    payload = _valid_payload(vehicle_id, labor_cost='80.25', parts_cost='40.25')
    payload.pop('total_cost')

    response = client.post('/api/services', headers=auth_headers(user_id), json=payload)

    assert response.status_code == 201, response.get_json()
    with app.app_context():
        entry = ServiceEntry.query.one()
        assert float(entry.amount) == 120.50
        assert float(entry.labor_cost) == 80.25


def test_create_bumps_a_vehicle_that_has_no_mileage_yet(app, client, auth_headers):
    user_id, vehicle_id = _seed(app)
    with app.app_context():
        # The column default is 0, so NULL has to be forced past the ORM — legacy
        # rows predating that default still hold it.
        db.session.execute(
            db.text('UPDATE vehicles SET current_mileage = NULL WHERE id = :id'),
            {'id': vehicle_id})
        db.session.commit()

    response = client.post('/api/services', headers=auth_headers(user_id),
                           json=_valid_payload(vehicle_id, mileage=15000))

    assert response.status_code == 201, response.get_json()   # was: TypeError 500
    with app.app_context():
        assert db.session.get(Vehicle, vehicle_id).current_mileage == 15000


def test_create_never_lowers_the_vehicle_mileage(app, client, auth_headers):
    user_id, vehicle_id = _seed(app, current_mileage=20000)

    response = client.post('/api/services', headers=auth_headers(user_id),
                           json=_valid_payload(vehicle_id, mileage='15000'))

    assert response.status_code == 201, response.get_json()
    with app.app_context():
        assert db.session.get(Vehicle, vehicle_id).current_mileage == 20000


def _existing_entry(app, user_id, vehicle_id):
    with app.app_context():
        entry = ServiceEntry(
            user_id=user_id, vehicle_id=vehicle_id, date=date(2026, 3, 1),
            odometer=10000, amount=120.50, currency='GBP', title='oil_change',
            service_type='oil_change', service_types=['oil_change'],
            labor_cost=80.25, parts_cost=40.25, next_due_mileage=30000,
            warranty_months=24, description='Original',
        )
        db.session.add(entry)
        db.session.commit()
        return entry.id


@pytest.mark.parametrize('field, bad_value, expected_key', [
    ('date', 'bad', 'validation.invalidDate'),
    ('next_service_date', '2026-13-40', 'validation.invalidDate'),
    ('warranty_expires', 'bad', 'validation.invalidDate'),
    ('mileage', 'abc', 'validation.invalidNumber'),
    ('labor_cost', 'abc', 'validation.invalidNumber'),
    ('next_service_mileage', 'abc', 'validation.invalidNumber'),
    ('warranty_km', 'abc', 'validation.invalidNumber'),
    ('total_cost', 'abc', 'validation.invalidNumber'),
    ('currency', 'EURO', 'validation.invalidCurrency'),
])
def test_update_rejects_malformed_input_without_partial_writes(
        app, client, auth_headers, field, bad_value, expected_key):
    user_id, vehicle_id = _seed(app)
    entry_id = _existing_entry(app, user_id, vehicle_id)

    response = client.put(f'/api/services/{entry_id}', headers=auth_headers(user_id),
                          json={'description': 'Renamed', field: bad_value})

    assert response.status_code == 400, response.get_json()   # was: 500
    assert response.get_json()['message_key'] == expected_key
    with app.app_context():
        entry = db.session.get(ServiceEntry, entry_id)
        assert entry.description == 'Original'                # the valid edit too
        assert entry.date == date(2026, 3, 1)
        assert entry.odometer == 10000
        assert float(entry.labor_cost) == 80.25
        assert entry.next_due_mileage == 30000
        assert entry.warranty_months == 24


def test_update_stores_numeric_strings_and_bumps_the_vehicle(app, client, auth_headers):
    user_id, vehicle_id = _seed(app)
    entry_id = _existing_entry(app, user_id, vehicle_id)

    response = client.put(f'/api/services/{entry_id}', headers=auth_headers(user_id),
                          json={'mileage': '15000', 'next_service_mileage': '45000',
                                'warranty_km': '20000', 'date': '2026-04-02'})

    assert response.status_code == 200, response.get_json()
    with app.app_context():
        entry = db.session.get(ServiceEntry, entry_id)
        assert entry.odometer == 15000
        assert entry.next_due_mileage == 45000
        assert entry.warranty_km == 20000
        assert entry.date == date(2026, 4, 2)
        assert db.session.get(Vehicle, vehicle_id).current_mileage == 15000


def test_update_recalculates_the_amount_from_labor_and_parts(app, client, auth_headers):
    user_id, vehicle_id = _seed(app)
    entry_id = _existing_entry(app, user_id, vehicle_id)

    response = client.put(f'/api/services/{entry_id}', headers=auth_headers(user_id),
                          json={'labor_cost': '100.50', 'parts_cost': '9.50'})

    assert response.status_code == 200, response.get_json()
    with app.app_context():
        assert float(db.session.get(ServiceEntry, entry_id).amount) == 110.0


def test_update_clears_a_nullable_date_but_never_the_entry_date(app, client, auth_headers):
    user_id, vehicle_id = _seed(app)
    entry_id = _existing_entry(app, user_id, vehicle_id)

    response = client.put(f'/api/services/{entry_id}', headers=auth_headers(user_id),
                          json={'next_service_date': '', 'date': ''})

    assert response.status_code == 200, response.get_json()
    with app.app_context():
        entry = db.session.get(ServiceEntry, entry_id)
        assert entry.next_due_date is None
        assert entry.date == date(2026, 3, 1)        # NOT NULL — never cleared

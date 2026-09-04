"""Regression tests for R4-10 / R4-11 on the fuel routes.

`create_fuel_entry` called `datetime.fromisoformat` on client input with no
guard, multiplied `float(liters) * float(price_per_liter)` to derive the total,
and assigned `liters`, `price_per_liter`, `total_price`, `odometer` and
`currency` straight onto Numeric / Integer / String(3) columns. Any malformed
value reached the driver as a 500. The mileage bump then compared a raw string
to `vehicle.current_mileage`, and compared against `None` when the vehicle had
no mileage yet.

`update_fuel_entry` shared every gap and assigned field by field as it went, so
a refused write half-applied — and it half-applied *durably*, because the
handler recalculates the vehicle mileage and the efficiency chain from whatever
it had already written.
"""

from datetime import date

import pytest

from app import db
from app.models import FuelEntry, User, Vehicle


def _seed(app, current_mileage=1000):
    with app.app_context():
        user = User(username='fuel', email='fuel@example.com', is_active=True,
                    currency='GBP')
        user.set_password('StrongPass123!')
        db.session.add(user)
        db.session.commit()
        vehicle = Vehicle(user_id=user.id, name='Golf', current_mileage=current_mileage,
                          fuel_type='diesel')
        db.session.add(vehicle)
        db.session.commit()
        return user.id, vehicle.id


def _valid_payload(vehicle_id, **overrides):
    payload = {
        'vehicle_id': vehicle_id,
        'date': '2026-03-01',
        'liters': 45.5,
        'price_per_liter': 1.62,
        'odometer': 5000,
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize('field, bad_value, expected_key', [
    ('date', 'bad', 'validation.invalidDate'),
    ('date', '2026-13-40', 'validation.invalidDate'),
    ('entry_date', 12345, 'validation.invalidDate'),          # was: AttributeError
    ('liters', 'x', 'validation.invalidNumber'),
    ('volume', 'x', 'validation.invalidNumber'),
    ('price_per_liter', 'x', 'validation.invalidNumber'),
    ('total_price', 'x', 'validation.invalidNumber'),
    ('odometer', 'abc', 'validation.invalidNumber'),
    ('mileage', {}, 'validation.invalidNumber'),
    ('currency', 'EURO', 'validation.invalidCurrency'),       # the column is String(3)
])
def test_create_rejects_malformed_input(app, client, auth_headers, field, bad_value, expected_key):
    user_id, vehicle_id = _seed(app)
    payload = _valid_payload(vehicle_id, **{field: bad_value})
    if field == 'entry_date':
        payload.pop('date')                  # 'date' takes precedence over its alias
    if field in ('volume', 'mileage'):
        payload.pop(field.replace('volume', 'liters').replace('mileage', 'odometer'))

    response = client.post('/api/fuel', headers=auth_headers(user_id), json=payload)

    assert response.status_code == 400, response.get_json()   # was: 500
    assert response.get_json()['message_key'] == expected_key
    with app.app_context():
        assert FuelEntry.query.count() == 0
        assert db.session.get(Vehicle, vehicle_id).current_mileage == 1000


def test_create_requires_the_fuel_amount(app, client, auth_headers):
    user_id, vehicle_id = _seed(app)
    payload = _valid_payload(vehicle_id)
    payload.pop('liters')

    response = client.post('/api/fuel', headers=auth_headers(user_id), json=payload)

    assert response.status_code == 400, response.get_json()
    assert response.get_json()['message_key'] == 'validation.required'


def test_create_coerces_the_numeric_strings_a_form_submits(app, client, auth_headers):
    user_id, vehicle_id = _seed(app)

    response = client.post('/api/fuel', headers=auth_headers(user_id),
                           json=_valid_payload(vehicle_id, odometer='5000',
                                               liters='45.50', price_per_liter='1.620',
                                               date='2026-03-01T09:30:00Z'))

    assert response.status_code == 201, response.get_json()
    with app.app_context():
        entry = FuelEntry.query.one()
        assert entry.odometer == 5000
        assert entry.date == date(2026, 3, 1)                 # 'Z' suffix accepted
        assert float(entry.liters) == 45.50
        assert float(entry.price_per_liter) == 1.620
        assert entry.currency == 'GBP'                        # the user's currency
        assert db.session.get(Vehicle, vehicle_id).current_mileage == 5000


def test_create_derives_the_total_from_litres_and_unit_price(app, client, auth_headers):
    user_id, vehicle_id = _seed(app)

    response = client.post('/api/fuel', headers=auth_headers(user_id),
                           json=_valid_payload(vehicle_id, liters='40', price_per_liter='1.50'))

    assert response.status_code == 201, response.get_json()
    with app.app_context():
        entry = FuelEntry.query.one()
        assert float(entry.total_price) == 60.0
        assert float(entry.amount) == 60.0


def test_create_bumps_a_vehicle_that_has_no_mileage_yet(app, client, auth_headers):
    user_id, vehicle_id = _seed(app)
    with app.app_context():
        # The column default is 0, so NULL has to be forced past the ORM — legacy
        # rows predating that default still hold it.
        db.session.execute(
            db.text('UPDATE vehicles SET current_mileage = NULL WHERE id = :id'),
            {'id': vehicle_id})
        db.session.commit()

    response = client.post('/api/fuel', headers=auth_headers(user_id),
                           json=_valid_payload(vehicle_id, odometer=5000))

    assert response.status_code == 201, response.get_json()   # was: TypeError 500
    with app.app_context():
        assert db.session.get(Vehicle, vehicle_id).current_mileage == 5000


def test_create_never_lowers_the_vehicle_mileage(app, client, auth_headers):
    user_id, vehicle_id = _seed(app, current_mileage=20000)

    response = client.post('/api/fuel', headers=auth_headers(user_id),
                           json=_valid_payload(vehicle_id, odometer='5000'))

    assert response.status_code == 201, response.get_json()
    with app.app_context():
        assert db.session.get(Vehicle, vehicle_id).current_mileage == 20000


def _existing_entry(app, user_id, vehicle_id):
    with app.app_context():
        entry = FuelEntry(
            user_id=user_id, vehicle_id=vehicle_id, date=date(2026, 3, 1),
            odometer=5000, amount=73.71, currency='GBP', title='Fuel',
            liters=45.5, price_per_liter=1.62, total_price=73.71,
            fuel_type='diesel', full_tank=True, notes='Original',
        )
        db.session.add(entry)
        db.session.commit()
        return entry.id


@pytest.mark.parametrize('field, bad_value, expected_key', [
    ('date', 'bad', 'validation.invalidDate'),
    ('odometer', 'abc', 'validation.invalidNumber'),
    ('liters', 'x', 'validation.invalidNumber'),
    ('price_per_liter', 'x', 'validation.invalidNumber'),
    ('total_price', 'x', 'validation.invalidNumber'),
    ('currency', 'EURO', 'validation.invalidCurrency'),
])
def test_update_rejects_malformed_input_without_partial_writes(
        app, client, auth_headers, field, bad_value, expected_key):
    user_id, vehicle_id = _seed(app)
    entry_id = _existing_entry(app, user_id, vehicle_id)

    response = client.put(f'/api/fuel/{entry_id}', headers=auth_headers(user_id),
                          json={'notes': 'Renamed', field: bad_value})

    assert response.status_code == 400, response.get_json()   # was: 500
    assert response.get_json()['message_key'] == expected_key
    with app.app_context():
        entry = db.session.get(FuelEntry, entry_id)
        assert entry.notes == 'Original'                      # the valid edit too
        assert entry.date == date(2026, 3, 1)
        assert entry.odometer == 5000
        assert float(entry.liters) == 45.5
        assert float(entry.price_per_liter) == 1.62
        assert float(entry.total_price) == 73.71
        assert entry.currency == 'GBP'


def test_update_stores_numeric_strings(app, client, auth_headers):
    user_id, vehicle_id = _seed(app)
    entry_id = _existing_entry(app, user_id, vehicle_id)

    response = client.put(f'/api/fuel/{entry_id}', headers=auth_headers(user_id),
                          json={'odometer': '9000', 'liters': '50.25',
                                'total_price': '81.50', 'date': '2026-04-02'})

    assert response.status_code == 200, response.get_json()
    with app.app_context():
        entry = db.session.get(FuelEntry, entry_id)
        assert entry.odometer == 9000
        assert float(entry.liters) == 50.25
        assert float(entry.total_price) == 81.50
        assert float(entry.amount) == 81.50
        assert entry.date == date(2026, 4, 2)
        assert db.session.get(Vehicle, vehicle_id).current_mileage == 9000


def test_update_ignores_a_blank_currency(app, client, auth_headers):
    user_id, vehicle_id = _seed(app)
    entry_id = _existing_entry(app, user_id, vehicle_id)

    response = client.put(f'/api/fuel/{entry_id}', headers=auth_headers(user_id),
                          json={'currency': ''})

    assert response.status_code == 200, response.get_json()
    with app.app_context():
        # F48 — a blank code never clears an existing value.
        assert db.session.get(FuelEntry, entry_id).currency == 'GBP'

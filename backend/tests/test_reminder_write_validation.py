"""Regression tests for R4-10 / R4-11 on the reminder routes.

`create_reminder` passed `due_date=None` straight to a NOT NULL column
(`models/reminder.py:22`) when the client omitted it — an IntegrityError 500 —
and called `datetime.fromisoformat` unguarded when it was present, so a
malformed date was a 500 too. `due_mileage`, `notify_days_before` and the
form's `recurrence_interval` reached Integer columns with no coercion.

`update_reminder` shared the unguarded date, and its alias loop assigned the
same integer columns raw while mutating the reminder as it went — so a refused
write half-applied. Every rejection below asserts the stored reminder is
COMPLETELY unchanged.
"""

from datetime import date

import pytest

from app import db
from app.models import Reminder, User, Vehicle


def _seed(app):
    with app.app_context():
        user = User(username='rem', email='rem@example.com', is_active=True)
        user.set_password('StrongPass123!')
        db.session.add(user)
        db.session.commit()
        vehicle = Vehicle(user_id=user.id, name='Golf')
        db.session.add(vehicle)
        db.session.commit()
        return user.id, vehicle.id


def _valid_payload(vehicle_id, **overrides):
    payload = {
        'vehicle_id': vehicle_id,
        'title': 'Change the timing belt',
        'due_date': '2026-06-01',
    }
    payload.update(overrides)
    return payload


def test_create_requires_a_due_date(app, client, auth_headers):
    user_id, vehicle_id = _seed(app)
    payload = _valid_payload(vehicle_id)
    payload.pop('due_date')

    response = client.post('/api/reminders', headers=auth_headers(user_id), json=payload)

    assert response.status_code == 400, response.get_json()   # was: IntegrityError 500
    assert response.get_json()['message_key'] == 'validation.required'
    with app.app_context():
        assert Reminder.query.count() == 0


def test_create_rejects_an_empty_due_date(app, client, auth_headers):
    user_id, vehicle_id = _seed(app)

    response = client.post('/api/reminders', headers=auth_headers(user_id),
                           json=_valid_payload(vehicle_id, due_date=''))

    assert response.status_code == 400, response.get_json()
    assert response.get_json()['message_key'] == 'validation.required'
    with app.app_context():
        assert Reminder.query.count() == 0


@pytest.mark.parametrize('field, bad_value, expected_key', [
    ('due_date', '2026-13-40', 'validation.invalidDate'),
    ('due_date', 'not-a-date', 'validation.invalidDate'),
    ('due_mileage', 'abc', 'validation.invalidNumber'),
    ('due_mileage', {}, 'validation.invalidNumber'),
    ('notify_days_before', 'soon', 'validation.invalidNumber'),
    ('recurrence_interval', 'twice', 'validation.invalidNumber'),
])
def test_create_rejects_malformed_input(app, client, auth_headers, field, bad_value, expected_key):
    user_id, vehicle_id = _seed(app)

    response = client.post('/api/reminders', headers=auth_headers(user_id),
                           json=_valid_payload(vehicle_id, **{field: bad_value}))

    assert response.status_code == 400, response.get_json()   # was: 500
    assert response.get_json()['message_key'] == expected_key
    with app.app_context():
        assert Reminder.query.count() == 0


def test_create_coerces_the_numeric_strings_a_form_submits(app, client, auth_headers):
    user_id, vehicle_id = _seed(app)

    response = client.post('/api/reminders', headers=auth_headers(user_id),
                           json=_valid_payload(vehicle_id, due_mileage='12000',
                                               notify_days_before='14',
                                               recurrence_interval='3',
                                               due_date='2026-06-01T00:00:00Z'))

    assert response.status_code == 201, response.get_json()
    with app.app_context():
        reminder = Reminder.query.one()
        assert reminder.due_date == date(2026, 6, 1)      # 'Z' suffix accepted
        assert reminder.due_mileage == 12000
        assert reminder.notify_days_before == 14
        assert reminder.frequency_value == 3


def test_create_defaults_notify_days_before_when_absent(app, client, auth_headers):
    user_id, vehicle_id = _seed(app)

    response = client.post('/api/reminders', headers=auth_headers(user_id),
                           json=_valid_payload(vehicle_id, due_mileage=''))

    assert response.status_code == 201, response.get_json()
    with app.app_context():
        reminder = Reminder.query.one()
        assert reminder.notify_days_before == 7
        assert reminder.due_mileage is None               # '' means "not provided"


def _existing_reminder(app, user_id, vehicle_id):
    with app.app_context():
        reminder = Reminder(
            user_id=user_id, vehicle_id=vehicle_id, title='Change the timing belt',
            due_date=date(2026, 6, 1), due_mileage=10000, notify_days_before=7,
            frequency_value=1, priority='medium',
        )
        db.session.add(reminder)
        db.session.commit()
        return reminder.id


@pytest.mark.parametrize('field, bad_value, expected_key', [
    ('due_date', '2026-13-40', 'validation.invalidDate'),
    ('due_mileage', 'abc', 'validation.invalidNumber'),
    ('notify_days_before', 'soon', 'validation.invalidNumber'),
    ('recurrence_interval', 'twice', 'validation.invalidNumber'),
])
def test_update_rejects_malformed_input_without_partial_writes(
        app, client, auth_headers, field, bad_value, expected_key):
    user_id, vehicle_id = _seed(app)
    reminder_id = _existing_reminder(app, user_id, vehicle_id)

    response = client.put(f'/api/reminders/{reminder_id}', headers=auth_headers(user_id),
                          json={'title': 'Renamed', field: bad_value})

    assert response.status_code == 400, response.get_json()   # was: 500
    assert response.get_json()['message_key'] == expected_key
    with app.app_context():
        reminder = db.session.get(Reminder, reminder_id)
        assert reminder.title == 'Change the timing belt'     # the valid edit too
        assert reminder.due_date == date(2026, 6, 1)
        assert reminder.due_mileage == 10000
        assert reminder.notify_days_before == 7
        assert reminder.frequency_value == 1


def test_update_stores_a_numeric_string_mileage(app, client, auth_headers):
    user_id, vehicle_id = _seed(app)
    reminder_id = _existing_reminder(app, user_id, vehicle_id)

    response = client.put(f'/api/reminders/{reminder_id}', headers=auth_headers(user_id),
                          json={'due_mileage': '12000', 'notify_days_before': '3',
                                'due_date': '2027-01-15'})

    assert response.status_code == 200, response.get_json()
    with app.app_context():
        reminder = db.session.get(Reminder, reminder_id)
        assert reminder.due_mileage == 12000
        assert reminder.notify_days_before == 3
        assert reminder.due_date == date(2027, 1, 15)


def test_update_clears_the_mileage_with_an_empty_string(app, client, auth_headers):
    user_id, vehicle_id = _seed(app)
    reminder_id = _existing_reminder(app, user_id, vehicle_id)

    response = client.put(f'/api/reminders/{reminder_id}', headers=auth_headers(user_id),
                          json={'due_mileage': ''})

    assert response.status_code == 200, response.get_json()
    with app.app_context():
        assert db.session.get(Reminder, reminder_id).due_mileage is None

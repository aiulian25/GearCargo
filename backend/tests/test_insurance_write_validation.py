"""Regression tests for R4-10 / R4-11 on the insurance routes.

`create_policy` called `datetime.fromisoformat` on two client-supplied dates
with no guard, and assigned `premium`, `coverage_amount`, `deductible` and
`currency` straight onto Numeric / String(3) columns. Malformed input therefore
reached the driver and surfaced as a 500 rather than a 400 the UI can render.

`update_policy` had the same gaps, plus one of its own: a falsy `start_date`
fell through to the raw `setattr`, so clearing a NOT NULL date wrote `''`.

Every rejection is asserted to leave the stored policy COMPLETELY unchanged —
a refused write must not half-apply.
"""

from datetime import date

import pytest

from app import db
from app.models import InsurancePolicy, User, Vehicle


def _seed(app):
    with app.app_context():
        user = User(username='ins', email='ins@example.com', is_active=True,
                    currency='GBP')
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
        'provider': 'Acme Insurance',
        'start_date': '2026-01-01',
        'end_date': '2026-12-31',
        'premium': 42.5,
        'currency': 'GBP',
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize('field, bad_value, expected_key', [
    ('start_date', 'not-a-date', 'validation.invalidDate'),
    ('end_date', '2026-13-45', 'validation.invalidDate'),
    ('premium', 'abc', 'validation.invalidNumber'),
    ('premium', None, 'validation.invalidNumber'),      # the column is NOT NULL
    ('coverage_amount', 'abc', 'validation.invalidNumber'),
    ('deductible', {}, 'validation.invalidNumber'),
    ('currency', 'EURO', 'validation.invalidCurrency'),  # the column is String(3)
    ('currency', 'E1R', 'validation.invalidCurrency'),
])
def test_create_rejects_malformed_input(app, client, auth_headers, field, bad_value, expected_key):
    user_id, vehicle_id = _seed(app)

    response = client.post('/api/insurance', headers=auth_headers(user_id),
                           json=_valid_payload(vehicle_id, **{field: bad_value}))

    assert response.status_code == 400, response.get_json()   # was: 500
    assert response.get_json()['message_key'] == expected_key
    with app.app_context():
        assert InsurancePolicy.query.count() == 0


def test_create_still_works_and_normalizes_the_currency(app, client, auth_headers):
    user_id, vehicle_id = _seed(app)

    response = client.post('/api/insurance', headers=auth_headers(user_id),
                           json=_valid_payload(vehicle_id, currency='eur',
                                               coverage_amount='150000',
                                               deductible=''))

    assert response.status_code == 201, response.get_json()
    with app.app_context():
        policy = InsurancePolicy.query.one()
        assert policy.currency == 'EUR'                 # upper-cased
        assert policy.start_date == date(2026, 1, 1)
        assert float(policy.premium) == 42.5
        assert float(policy.coverage_amount) == 150000  # numeric string accepted
        assert policy.deductible is None                # '' means "not provided"


def test_create_falls_back_to_the_users_currency(app, client, auth_headers):
    user_id, vehicle_id = _seed(app)
    payload = _valid_payload(vehicle_id)
    payload.pop('currency')

    response = client.post('/api/insurance', headers=auth_headers(user_id), json=payload)

    assert response.status_code == 201
    with app.app_context():
        assert InsurancePolicy.query.one().currency == 'GBP'


def _existing_policy(app, user_id, vehicle_id):
    with app.app_context():
        policy = InsurancePolicy(
            user_id=user_id, vehicle_id=vehicle_id, provider='Acme Insurance',
            premium=42.5, currency='GBP',
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
        )
        db.session.add(policy)
        db.session.commit()
        return policy.id


@pytest.mark.parametrize('payload, expected_key', [
    ({'start_date': 'nonsense'}, 'validation.invalidDate'),
    ({'end_date': ''}, 'validation.invalidDate'),        # NOT NULL — cannot be cleared
    ({'premium': 'abc'}, 'validation.invalidNumber'),
    ({'currency': 'POUNDS'}, 'validation.invalidCurrency'),
])
def test_update_rejects_malformed_input_and_changes_nothing(app, client, auth_headers,
                                                            payload, expected_key):
    user_id, vehicle_id = _seed(app)
    policy_id = _existing_policy(app, user_id, vehicle_id)

    # Include a VALID edit alongside the bad one: it must not be applied either.
    payload = {**payload, 'provider': 'Should Not Be Saved'}
    response = client.put(f'/api/insurance/{policy_id}',
                          headers=auth_headers(user_id), json=payload)

    assert response.status_code == 400, response.get_json()
    assert response.get_json()['message_key'] == expected_key
    with app.app_context():
        policy = db.session.get(InsurancePolicy, policy_id)
        assert policy.provider == 'Acme Insurance'       # no partial write
        assert policy.start_date == date(2026, 1, 1)
        assert policy.end_date == date(2026, 12, 31)
        assert float(policy.premium) == 42.5
        assert policy.currency == 'GBP'


def test_update_still_applies_valid_edits(app, client, auth_headers):
    user_id, vehicle_id = _seed(app)
    policy_id = _existing_policy(app, user_id, vehicle_id)

    response = client.put(f'/api/insurance/{policy_id}', headers=auth_headers(user_id),
                          json={'premium': '99.99', 'currency': 'ron',
                                'end_date': '2027-01-31', 'provider': 'New Provider'})

    assert response.status_code == 200, response.get_json()
    with app.app_context():
        policy = db.session.get(InsurancePolicy, policy_id)
        assert float(policy.premium) == 99.99
        assert policy.currency == 'RON'
        assert policy.end_date == date(2027, 1, 31)
        assert policy.provider == 'New Provider'

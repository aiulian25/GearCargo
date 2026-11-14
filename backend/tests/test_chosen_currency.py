"""A money record carries the currency its owner chose, never a built-in one.

Until late July 2026 every expense was saved as EUR and every policy as USD, whatever the
person paid in. These tests pin the owner's currency on every creation path, and the review
that lets a person correct the old labels without converting any amount.
"""
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import null

from app import db
from app.models import FuelEntry, ParkingEntry, TaxEntry, User, Vehicle
from app.models.insurance import InsurancePolicy
from app.models.reconciliation import StatementBatch, StatementMatch, StatementTransaction
from app.models.user import DEFAULT_CURRENCY
from app.services.csv_io import import_entries_csv
from app.services.currency_review import KEPT_CURRENCIES_PREFERENCE
from app.services.lubelog_import import import_lubelog_to_gearcargo
from tests.test_lubelog_import import VEHICLE_ONE, _lubelog_zip

REVIEW_URL = '/api/vehicles/currency-review'
ENTRY_DATE = '2026-03-01'


@pytest.fixture(autouse=True)
def application_context(app):
    with app.app_context():
        yield


def _vehicle(user_id):
    vehicle = Vehicle(user_id=user_id, name='Qashqai', make='Nissan', model='Qashqai',
                      current_mileage=50000, distance_unit='km')
    db.session.add(vehicle)
    db.session.commit()
    return vehicle


def _account(currency, email='ron@example.com'):
    account = User(username=email.split('@')[0], email=email, is_active=True, currency=currency)
    account.set_password('StrongPass123!')
    db.session.add(account)
    db.session.commit()
    return account


@pytest.mark.parametrize('chosen, expected', [('RON', 'RON'), (None, DEFAULT_CURRENCY)])
def test_a_record_saved_without_a_currency_takes_its_owners_currency(app, chosen, expected):
    account = _account(chosen)
    vehicle = _vehicle(account.id)
    db.session.add_all([
        FuelEntry(user_id=account.id, vehicle_id=vehicle.id, date=date(2026, 3, 1), amount=70),
        InsurancePolicy(user_id=account.id, vehicle_id=vehicle.id, provider='Acme', premium=720,
                        start_date=date(2026, 1, 1), end_date=date(2026, 12, 31)),
    ])
    db.session.commit()

    assert FuelEntry.query.one().currency == expected
    assert InsurancePolicy.query.one().currency == expected


def test_a_currency_stored_as_unknown_stays_unknown(app, user):
    """Legacy imports force "unknown" with null(); the default must not guess for them."""
    vehicle = _vehicle(user.id)
    db.session.add(FuelEntry(user_id=user.id, vehicle_id=vehicle.id, date=date(2026, 3, 1),
                             amount=70, currency=null()))
    db.session.commit()

    assert FuelEntry.query.one().currency is None


CREATE_ROUTES = [
    ('/api/fuel', {'liters': 40, 'price_per_liter': 1.5, 'odometer': 51000}),
    ('/api/services', {'service_types': ['oil_change'], 'mileage': 51000, 'total_cost': 80}),
    ('/api/repairs', {'repair_types': ['brakes'], 'mileage': 51000, 'total_cost': 200}),
    ('/api/taxes', {'tax_type': 'road_tax', 'amount': 180, 'status': 'paid'}),
    ('/api/parking', {'parking_type': 'street', 'amount': 5, 'location': 'High St'}),
    ('/api/consumables', {'consumable_type': 'tire', 'amount': 420.5, 'brand': 'Michelin'}),
    ('/api/insurance', {'provider': 'Acme', 'start_date': '2026-01-01', 'end_date': '2026-12-31',
                        'premium': 720}),
]


@pytest.mark.parametrize('url, fields', CREATE_ROUTES, ids=[url for url, _ in CREATE_ROUTES])
def test_every_create_route_defaults_to_the_account_currency(app, client, auth_headers, url, fields):
    account = _account('RON')
    payload = {'vehicle_id': _vehicle(account.id).id, 'date': ENTRY_DATE, **fields}

    response = client.post(url, json=payload, headers=auth_headers(account.id))

    assert response.status_code == 201, response.json
    record = response.json.get('entry') or response.json.get('policy')
    assert record['currency'] == 'RON'


def test_a_currency_given_with_the_record_wins_over_the_account_currency(app, client, auth_headers):
    account = _account('RON')
    payload = {'vehicle_id': _vehicle(account.id).id, 'date': ENTRY_DATE, 'currency': 'EUR',
               'liters': 40, 'price_per_liter': 1.5, 'odometer': 51000}

    response = client.post('/api/fuel', json=payload, headers=auth_headers(account.id))

    assert response.json['entry']['currency'] == 'EUR'


def test_a_lubelogger_import_is_labelled_with_the_importing_accounts_currency(app):
    account = _account('RON', 'lubelog-ron@example.com')
    fill = {'_id': 20, 'VehicleId': 1, 'Gallons': 40.0, 'IsFillToFull': True, 'Cost': 70.0,
            'Mileage': 1000, 'Date': datetime(2026, 3, 1)}

    result = import_lubelog_to_gearcargo(account, _lubelog_zip([VEHICLE_ONE, fill]),
                                         merge_mode='merge', distance_unit='km',
                                         source_volume_unit='liters', source_distance_unit='km')

    assert result.get('error') is None, result
    assert [entry.currency for entry in FuelEntry.query.all()] == ['RON']


def test_a_csv_import_without_a_currency_column_uses_the_account_currency(app):
    account = _account('RON', 'csv-ron@example.com')
    vehicle = _vehicle(account.id)

    summary = import_entries_csv(account, 'fuel', f'vehicle_id,date,amount\n{vehicle.id},{ENTRY_DATE},70\n')

    assert summary['created'] == 1, summary
    assert FuelEntry.query.one().currency == 'RON'


@pytest.fixture()
def legacy_garage(app, user):
    """A GBP account whose older records still carry the built-in EUR and USD labels."""
    vehicle = _vehicle(user.id)
    db.session.add_all([
        FuelEntry(user_id=user.id, vehicle_id=vehicle.id, date=date(2026, 1, 10), amount=70, currency='EUR'),
        TaxEntry(user_id=user.id, vehicle_id=vehicle.id, date=date(2026, 7, 26), amount=180, currency='EUR'),
        FuelEntry(user_id=user.id, vehicle_id=vehicle.id, date=date(2026, 8, 8), amount=71.06, currency='GBP'),
        InsurancePolicy(user_id=user.id, vehicle_id=vehicle.id, provider='Acme', premium=720, currency='USD',
                        start_date=date(2026, 2, 1), end_date=date(2027, 1, 31)),
    ])
    db.session.commit()
    return user, vehicle


def _review(client, headers):
    return client.get(REVIEW_URL, headers=headers).json


def test_the_review_lists_records_still_carrying_a_built_in_label(client, auth_headers, legacy_garage):
    user, _vehicle_row = legacy_garage

    assert _review(client, auth_headers(user.id)) == {'account_currency': 'GBP', 'groups': [
        {'currency': 'EUR', 'count': 2, 'first_date': '2026-01-10', 'last_date': '2026-07-26'},
        {'currency': 'USD', 'count': 1, 'first_date': '2026-02-01', 'last_date': '2026-02-01'},
    ]}


def test_records_in_the_accounts_own_currency_are_never_reviewed(client, auth_headers, legacy_garage):
    user, _vehicle_row = legacy_garage
    user.currency = 'EUR'
    db.session.commit()

    assert [group['currency'] for group in _review(client, auth_headers(user.id))['groups']] == ['USD']


def test_relabelling_changes_the_label_and_never_the_amount(client, auth_headers, legacy_garage):
    user, _vehicle_row = legacy_garage
    headers = auth_headers(user.id)
    revisions_before = {entry.id: entry.revision for entry in FuelEntry.query.all()}

    response = client.post(REVIEW_URL, json={'currency': 'EUR', 'action': 'relabel'}, headers=headers)

    assert response.status_code == 200, response.json
    assert response.json['relabelled'] == 2
    assert [group['currency'] for group in response.json['groups']] == ['USD']
    assert sorted((entry.currency, entry.amount) for entry in FuelEntry.query.all()) == [
        ('GBP', Decimal('70.00')), ('GBP', Decimal('71.06'))]
    assert TaxEntry.query.one().amount == Decimal('180.00')
    assert TaxEntry.query.one().currency == 'GBP'
    relabelled, untouched = FuelEntry.query.order_by(FuelEntry.date).all()
    assert relabelled.revision == revisions_before[relabelled.id] + 1
    assert untouched.revision == revisions_before[untouched.id]
    assert InsurancePolicy.query.one().currency == 'USD'


def test_relabelling_a_policy_group_corrects_its_built_in_label(client, auth_headers, legacy_garage):
    user, _vehicle_row = legacy_garage

    response = client.post(REVIEW_URL, json={'currency': 'USD', 'action': 'relabel'},
                           headers=auth_headers(user.id))

    assert response.json['relabelled'] == 1
    policy = InsurancePolicy.query.one()
    assert (policy.currency, policy.premium) == ('GBP', Decimal('720.00'))


def test_keeping_a_group_leaves_its_records_alone_and_is_not_asked_again(client, auth_headers, legacy_garage):
    user, _vehicle_row = legacy_garage
    headers = auth_headers(user.id)

    response = client.post(REVIEW_URL, json={'currency': 'EUR', 'action': 'keep'}, headers=headers)

    assert response.status_code == 200, response.json
    assert response.json['relabelled'] == 0
    assert [group['currency'] for group in _review(client, headers)['groups']] == ['USD']
    assert TaxEntry.query.one().currency == 'EUR'
    assert db.session.get(User, user.id).preferences[KEPT_CURRENCIES_PREFERENCE] == ['EUR']


def test_an_expense_matched_to_a_statement_keeps_its_recorded_currency(client, auth_headers, legacy_garage):
    """A match is only possible in the statement's own currency, so that label was confirmed."""
    user, _vehicle_row = legacy_garage
    matched = TaxEntry.query.one()
    batch = StatementBatch(user_id=user.id, name='Card', source_key='s' * 64, selection_hash='h' * 64)
    db.session.add(batch)
    db.session.flush()
    transaction = StatementTransaction(batch_id=batch.id, user_id=user.id, row_number=1, fingerprint='t' * 64,
                                       date=matched.date, amount=180, currency='EUR', vendor='DVLA')
    db.session.add(transaction)
    db.session.flush()
    db.session.add(StatementMatch(user_id=user.id, transaction_id=transaction.id, entry_id=matched.id,
                                  amount=180, entry_signature='e' * 64))
    db.session.commit()
    headers = auth_headers(user.id)

    assert _review(client, headers)['groups'][0] == {
        'currency': 'EUR', 'count': 1, 'first_date': '2026-01-10', 'last_date': '2026-01-10'}
    client.post(REVIEW_URL, json={'currency': 'EUR', 'action': 'relabel'}, headers=headers)

    assert TaxEntry.query.one().currency == 'EUR'


def test_another_accounts_records_are_never_relabelled(client, auth_headers, legacy_garage):
    user, _vehicle_row = legacy_garage
    neighbour = _account('GBP', 'neighbour@example.com')
    neighbour_vehicle = _vehicle(neighbour.id)
    db.session.add(ParkingEntry(user_id=neighbour.id, vehicle_id=neighbour_vehicle.id, date=date(2026, 2, 2),
                                amount=5, currency='EUR'))
    db.session.commit()

    client.post(REVIEW_URL, json={'currency': 'EUR', 'action': 'relabel'}, headers=auth_headers(user.id))

    assert ParkingEntry.query.one().currency == 'EUR'


@pytest.mark.parametrize('payload', [
    {'currency': 'EUR', 'action': 'convert'},
    {'currency': 'GBP', 'action': 'relabel'},
    {'currency': 'CHF', 'action': 'keep'},
    {},
])
def test_an_unknown_action_or_currency_is_refused_without_changing_anything(client, auth_headers, legacy_garage, payload):
    user, _vehicle_row = legacy_garage

    response = client.post(REVIEW_URL, json=payload, headers=auth_headers(user.id))

    assert response.status_code == 400
    assert response.json['message_key'] == 'currencyReview.nothingToReview'
    assert TaxEntry.query.one().currency == 'EUR'


def test_the_review_requires_a_signed_in_account(client):
    assert client.get(REVIEW_URL).status_code == 401
    assert client.post(REVIEW_URL, json={'currency': 'EUR', 'action': 'relabel'}).status_code == 401

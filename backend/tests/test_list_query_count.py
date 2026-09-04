"""Regression tests for R4-15 — attachment loading on paginated list endpoints.

`Entry.attachments` was a `lazy='dynamic'` relationship and `Entry.to_dict`
called `self.attachments.all()` per row, so every paginated list ran
1 + per_page queries — 21 at the default page size, and 101 at the maximum.

The attachments cannot simply be dropped from these responses:
`VehicleExpenses.jsx:795` renders a per-row attachment button (count + OCR
badge) for the fuel, service, repair, tax and parking tables, all fed by these
endpoints. So the fix batches the load instead of removing it, and these tests
pin the query count to a constant that does not grow with the page.
"""

from datetime import date, timedelta

import pytest
from sqlalchemy import event

from app import db
from app.models import (FuelEntry, RepairEntry, ServiceEntry, TaxEntry,
                        User, Vehicle)
from app.models.attachment import Attachment

ENTRIES_PER_PAGE = 20


@pytest.fixture
def statement_counter(app):
    """Count SQL statements issued while the block runs."""
    counted = []

    def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        counted.append(statement)

    with app.app_context():
        engine = db.engine
    event.listen(engine, 'before_cursor_execute', _before_cursor_execute)
    yield counted
    event.remove(engine, 'before_cursor_execute', _before_cursor_execute)


def _seed_entries_with_attachments(app, count=ENTRIES_PER_PAGE):
    with app.app_context():
        user = User(username='lists', email='lists@example.com', is_active=True,
                    currency='GBP')
        user.set_password('StrongPass123!')
        db.session.add(user)
        db.session.commit()
        vehicle = Vehicle(user_id=user.id, name='Golf', current_mileage=0)
        db.session.add(vehicle)
        db.session.commit()

        for index in range(count):
            entry = FuelEntry(
                user_id=user.id, vehicle_id=vehicle.id,
                date=date(2026, 1, 1) + timedelta(days=index),
                odometer=1000 + index, amount=50, currency='GBP', title='Fuel',
                liters=40, price_per_liter=1.25, total_price=50, full_tank=True,
            )
            db.session.add(entry)
            db.session.flush()
            db.session.add(Attachment(
                user_id=user.id, entry_id=entry.id, filename=f'receipt{index}.jpg',
                filepath=f'/tmp/receipt{index}.jpg', file_type='image/jpeg',
                file_size=1024, ocr_processed=True, ocr_text='TOTAL 50.00',
            ))
        db.session.commit()
        return user.id, vehicle.id


def _count_statements_for(client, statement_counter, url, user_id, auth_headers):
    statement_counter.clear()
    response = client.get(url, headers=auth_headers(user_id))
    assert response.status_code == 200, response.get_json()
    return len(statement_counter), response


def test_fuel_list_query_count_does_not_grow_with_the_page(
        app, client, auth_headers, statement_counter):
    """The invariant is "constant", not a magic number.

    Comparing two page sizes is immune to the fixed overhead of the request
    (the token lookup issues its own queries), and it is the property that
    actually regressed: before the fix a 20-row page cost 20 more statements
    than a 5-row one.
    """
    user_id, vehicle_id = _seed_entries_with_attachments(app)

    small, _ = _count_statements_for(
        client, statement_counter,
        f'/api/fuel?vehicle_id={vehicle_id}&per_page=5', user_id, auth_headers)
    large, response = _count_statements_for(
        client, statement_counter,
        f'/api/fuel?vehicle_id={vehicle_id}&per_page={ENTRIES_PER_PAGE}',
        user_id, auth_headers)

    assert len(response.get_json()['entries']) == ENTRIES_PER_PAGE
    assert large == small, (
        f'{large} statements for {ENTRIES_PER_PAGE} rows vs {small} for 5 — '
        'the attachment load is still per-row')


def test_fuel_list_still_carries_the_attachment_data_the_table_renders(
        app, client, auth_headers):
    user_id, vehicle_id = _seed_entries_with_attachments(app, count=2)

    response = client.get(f'/api/fuel?vehicle_id={vehicle_id}',
                          headers=auth_headers(user_id))

    assert response.status_code == 200
    for item in response.get_json()['entries']:
        # VehicleExpenses.jsx needs the count and the OCR flags per row.
        assert len(item['attachments']) == 1
        assert item['attachments'][0]['ocr_processed'] is True
        assert item['attachments'][0]['has_text'] is True


def test_single_fuel_entry_still_returns_its_attachments(app, client, auth_headers):
    user_id, vehicle_id = _seed_entries_with_attachments(app, count=1)
    with app.app_context():
        entry_id = FuelEntry.query.one().id

    response = client.get(f'/api/fuel/{entry_id}', headers=auth_headers(user_id))

    assert response.status_code == 200
    assert len(response.get_json()['attachments']) == 1


@pytest.mark.parametrize('model, endpoint, extra', [
    (ServiceEntry, '/api/services', {'service_type': 'oil_change',
                                     'service_types': ['oil_change']}),
    (RepairEntry, '/api/repairs', {'repair_type': 'brakes',
                                   'repair_types': ['brakes']}),
    (TaxEntry, '/api/taxes', {'tax_type': 'road_tax'}),
])
def test_sibling_list_endpoints_do_not_grow_with_the_page(
        app, client, auth_headers, statement_counter, model, endpoint, extra):
    with app.app_context():
        user = User(username=f'l{model.__name__}', email=f'{model.__name__}@example.com',
                    is_active=True, currency='GBP')
        user.set_password('StrongPass123!')
        db.session.add(user)
        db.session.commit()
        vehicle = Vehicle(user_id=user.id, name='Golf')
        db.session.add(vehicle)
        db.session.commit()
        user_id, vehicle_id = user.id, vehicle.id

        for index in range(ENTRIES_PER_PAGE):
            entry = model(user_id=user_id, vehicle_id=vehicle_id,
                          date=date(2026, 1, 1) + timedelta(days=index),
                          amount=50, currency='GBP', title='Entry', **extra)
            db.session.add(entry)
            db.session.flush()
            db.session.add(Attachment(
                user_id=user_id, entry_id=entry.id, filename=f'doc{index}.pdf',
                filepath=f'/tmp/doc{index}.pdf', file_type='application/pdf',
                file_size=2048))
        db.session.commit()

    small, _ = _count_statements_for(
        client, statement_counter, f'{endpoint}?vehicle_id={vehicle_id}&per_page=5',
        user_id, auth_headers)
    large, _ = _count_statements_for(
        client, statement_counter,
        f'{endpoint}?vehicle_id={vehicle_id}&per_page={ENTRIES_PER_PAGE}',
        user_id, auth_headers)

    assert large == small, (
        f'{endpoint}: {large} statements for {ENTRIES_PER_PAGE} rows vs '
        f'{small} for 5 — the attachment load is still per-row')

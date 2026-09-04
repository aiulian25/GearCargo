"""Tests for F38 — Gethomepage widget v2 (due items, fines owed, fuel price).

Covers the full API-key flow (generate → call with X-API-Key) since no widget
tests existed before.
"""

from datetime import date, timedelta

import pytest
from sqlalchemy import event

from app import db
from app.models import Reminder, User, Vehicle, ParkingEntry
from app.models.fuel import FuelEntry
from app.models.insurance import InsurancePolicy
from app.models.repair import RepairEntry
from app.models.service import ServiceEntry
import app.services.fuel_price_service as fps

TODAY = date.today()


@pytest.fixture(autouse=True)
def _fixed_prices(monkeypatch):
    """Deterministic, offline fuel prices."""
    monkeypatch.setattr(fps, 'get_prices', lambda country, app, force=False: {
        'diesel': 1.52, 'petrol': 1.44, 'lpg': 0.80, 'premium': None,
        'currency': '€', 'currency_code': 'EUR',
        'last_update': TODAY.isoformat(), 'baseline': False, 'stale': False,
    })


def _api_key(client, user, auth_headers):
    resp = client.post('/api/widget/api-key', headers=auth_headers(user.id))
    assert resp.status_code in (200, 201), resp.get_data(as_text=True)
    key = resp.get_json()['raw_key']   # returned exactly once (S07)
    assert key
    return key


def test_widget_requires_api_key(client):
    assert client.get('/api/widget/v1/homepage').status_code == 401
    assert client.get('/api/widget/v1/homepage',
                      headers={'X-API-Key': 'wrong-key'}).status_code == 401


def test_widget_rejects_query_param_key(client, user, auth_headers):
    """L4: a VALID key in the ?key= query string is rejected (401); only the
    X-API-Key header is accepted (query-string creds leak into logs/history)."""
    key = _api_key(client, user, auth_headers)
    # Query param no longer accepted → 401 (was 200 before the fix), both endpoints.
    assert client.get(f'/api/widget/v1/homepage?key={key}').status_code == 401
    assert client.get(f'/api/widget/v1/vehicles?key={key}').status_code == 401
    # The header form still works.
    assert client.get('/api/widget/v1/homepage', headers={'X-API-Key': key}).status_code == 200
    assert client.get('/api/widget/v1/vehicles', headers={'X-API-Key': key}).status_code == 200


def test_widget_v2_fields(app, client, user, auth_headers):
    with app.app_context():
        v = Vehicle(user_id=user.id, name='Golf', make='VW', model='Golf')
        db.session.add(v)
        db.session.commit()
        # Due item: insurance ending in 6 days (lands in the F4 feed).
        db.session.add(InsurancePolicy(
            user_id=user.id, vehicle_id=v.id, provider='Acme', status='active',
            premium=420, start_date=TODAY - timedelta(days=359),
            end_date=TODAY + timedelta(days=6)))
        # Outstanding fine: 60 pending.
        db.session.add(ParkingEntry(
            user_id=user.id, vehicle_id=v.id, amount=60, date=TODAY,
            parking_type='fine', fine_reason='Bus lane', fine_status='pending'))
        db.session.commit()
        u = db.session.get(type(user), user.id)
        u.currency = 'EUR'
        db.session.commit()

    key = _api_key(client, user, auth_headers)
    resp = client.get('/api/widget/v1/homepage', headers={'X-API-Key': key})
    assert resp.status_code == 200
    body = resp.get_json()

    # Original fields still present (backward-compatible mappings).
    for field in ('vehicles', 'service_records', 'reminders', 'next_reminder', 'subtitle'):
        assert field in body
    assert body['vehicles'] == 1

    # F38 fields.
    assert body['due_soon'] >= 1
    assert 'Golf' in body['next_due'] and '(6d)' in body['next_due']
    assert body['fines_owed'] == '60.00 EUR'
    assert body['fuel_price'] == 'diesel 1.52 €/L'


def test_widget_degrades_gracefully(app, client, user, auth_headers, monkeypatch):
    """Price service down + no data → 200 with safe defaults, never a 500."""
    monkeypatch.setattr(fps, 'get_prices',
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError('down')))

    key = _api_key(client, user, auth_headers)
    resp = client.get('/api/widget/v1/homepage', headers={'X-API-Key': key})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['due_soon'] == 0
    assert body['next_due'] == 'None'
    assert body['fines_owed'] == '0.00 GBP'
    assert body['fuel_price'] == 'N/A'


# ---------------------------------------------------------------------------
# R4-17 — /widget/v1/vehicles issued four queries per vehicle (three counts
# plus the next reminder), so the cost grew with the size of the fleet. The
# widget is polled on a schedule by Gethomepage, so this ran repeatedly.
# ---------------------------------------------------------------------------

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


def _fleet_with_history(app, user_id, vehicle_count):
    """A fleet where every vehicle has one of each entry type and a reminder."""
    with app.app_context():
        vehicle_ids = []
        for index in range(vehicle_count):
            vehicle = Vehicle(user_id=user_id, name=f'Car {index}', make='Ford',
                              model='Focus', year=2020, current_mileage=1000 * index)
            db.session.add(vehicle)
            db.session.flush()
            vehicle_ids.append(vehicle.id)

            common = dict(user_id=user_id, vehicle_id=vehicle.id, date=TODAY,
                          amount=50, currency='GBP')
            db.session.add(ServiceEntry(title='Service', service_type='oil_change',
                                        service_types=['oil_change'], **common))
            db.session.add(RepairEntry(title='Repair', repair_type='brakes',
                                       repair_types=['brakes'], **common))
            db.session.add(FuelEntry(title='Fuel', liters=40, price_per_liter=1.25,
                                     total_price=50, full_tank=True, **common))
            # Two reminders — the widget must report the EARLIER one.
            db.session.add(Reminder(user_id=user_id, vehicle_id=vehicle.id,
                                    title=f'Later {index}',
                                    due_date=TODAY + timedelta(days=30)))
            db.session.add(Reminder(user_id=user_id, vehicle_id=vehicle.id,
                                    title=f'Next {index}',
                                    due_date=TODAY + timedelta(days=7)))
            # Already past — must never be chosen as "next".
            db.session.add(Reminder(user_id=user_id, vehicle_id=vehicle.id,
                                    title=f'Overdue {index}',
                                    due_date=TODAY - timedelta(days=5)))
        db.session.commit()
        return vehicle_ids


def test_widget_vehicles_query_count_does_not_grow_with_the_fleet(
        app, client, user, auth_headers, statement_counter):
    """The invariant is "constant", not a magic number — the API-key lookup
    issues its own queries, and that overhead is unrelated to this finding."""
    key = _api_key(client, user, auth_headers)

    _fleet_with_history(app, user.id, vehicle_count=1)
    statement_counter.clear()
    client.get('/api/widget/v1/vehicles', headers={'X-API-Key': key})
    one_vehicle = len(statement_counter)

    _fleet_with_history(app, user.id, vehicle_count=3)
    statement_counter.clear()
    response = client.get('/api/widget/v1/vehicles', headers={'X-API-Key': key})
    four_vehicles = len(statement_counter)

    assert response.status_code == 200
    assert len(response.get_json()) == 4
    assert four_vehicles == one_vehicle, (
        f'{four_vehicles} statements for 4 vehicles vs {one_vehicle} for 1 — '
        'the per-vehicle queries are still there')


def test_widget_vehicles_reports_the_same_figures_as_before(
        app, client, user, auth_headers):
    key = _api_key(client, user, auth_headers)
    _fleet_with_history(app, user.id, vehicle_count=2)

    response = client.get('/api/widget/v1/vehicles', headers={'X-API-Key': key})

    assert response.status_code == 200
    payload = response.get_json()
    assert len(payload) == 2
    for item in payload:
        assert item['service_records'] == 2        # one service + one repair
        assert item['fuel_entries'] == 1
        assert item['next_reminder'].startswith('Next ')   # not the later one
        assert item['next_reminder_date'] == (TODAY + timedelta(days=7)).isoformat()


def test_widget_vehicles_handles_a_vehicle_with_no_history(
        app, client, user, auth_headers):
    key = _api_key(client, user, auth_headers)
    with app.app_context():
        db.session.add(Vehicle(user_id=user.id, name='Empty', make='Ford',
                               model='Ka', current_mileage=0))
        db.session.commit()

    response = client.get('/api/widget/v1/vehicles', headers={'X-API-Key': key})

    assert response.status_code == 200
    empty = next(item for item in response.get_json() if item['name'] == 'Empty')
    assert empty['service_records'] == 0
    assert empty['fuel_entries'] == 0
    assert empty['next_reminder'] is None
    assert empty['next_reminder_date'] is None


def test_widget_vehicles_excludes_completed_and_dismissed_reminders(
        app, client, user, auth_headers):
    key = _api_key(client, user, auth_headers)
    with app.app_context():
        vehicle = Vehicle(user_id=user.id, name='Solo', make='Ford', model='Focus')
        db.session.add(vehicle)
        db.session.commit()
        db.session.add(Reminder(user_id=user.id, vehicle_id=vehicle.id,
                                title='Done', completed=True,
                                due_date=TODAY + timedelta(days=1)))
        db.session.add(Reminder(user_id=user.id, vehicle_id=vehicle.id,
                                title='Dismissed', dismissed=True,
                                due_date=TODAY + timedelta(days=2)))
        db.session.add(Reminder(user_id=user.id, vehicle_id=vehicle.id,
                                title='Real', due_date=TODAY + timedelta(days=3)))
        db.session.commit()

    response = client.get('/api/widget/v1/vehicles', headers={'X-API-Key': key})

    assert response.status_code == 200
    solo = next(item for item in response.get_json() if item['name'] == 'Solo')
    assert solo['next_reminder'] == 'Real'


def test_widget_vehicles_never_leaks_another_users_fleet(
        app, client, user, auth_headers):
    key = _api_key(client, user, auth_headers)
    _fleet_with_history(app, user.id, vehicle_count=1)
    with app.app_context():
        other = User(username='intruder', email='intruder@example.com', is_active=True)
        other.set_password('StrongPass123!')
        db.session.add(other)
        db.session.commit()
        stranger = Vehicle(user_id=other.id, name='Not Mine', make='Audi', model='A4')
        db.session.add(stranger)
        db.session.commit()
        db.session.add(Reminder(user_id=other.id, vehicle_id=stranger.id,
                                title='Their reminder',
                                due_date=TODAY + timedelta(days=1)))
        db.session.commit()

    response = client.get('/api/widget/v1/vehicles', headers={'X-API-Key': key})

    assert response.status_code == 200
    names = [item['name'] for item in response.get_json()]
    assert 'Not Mine' not in names

"""GC-029: preserve calendar days, and serialize instants with an explicit zone."""
from datetime import date, datetime, timedelta, timezone

import pytest

from app import db
from app.models import FuelEntry, Vehicle
from app.routes import calendar_sync
from app.utils.timeutils import isoformat_utc


@pytest.mark.parametrize('value, expected', [
    (None, None),
    (datetime(2026, 1, 1, 0, 30), '2026-01-01T00:30:00Z'),
    (datetime(2026, 1, 1, 0, 30, tzinfo=timezone.utc), '2026-01-01T00:30:00Z'),
    (datetime(2026, 1, 1, 2, 30, tzinfo=timezone(timedelta(hours=2))), '2026-01-01T00:30:00Z'),
    (datetime(2025, 12, 31, 16, 30, 0, 123456, tzinfo=timezone(timedelta(hours=-8))), '2026-01-01T00:30:00.123456Z'),
])
def test_instants_have_explicit_utc_offset_without_mutating_input(value, expected):
    assert isoformat_utc(value) == expected
    if value:
        assert datetime.fromisoformat(expected.replace('Z', '+00:00')).tzinfo == timezone.utc


def test_calendar_dates_cannot_accidentally_be_serialized_as_instants():
    with pytest.raises(TypeError):
        isoformat_utc(date(2024, 2, 29))


@pytest.mark.parametrize('year,month,last', [
    (2026, 1, '2026-02-28'), (2024, 1, '2024-02-29'),
    (2026, 2, '2026-03-31'), (2026, 3, '2026-04-30'),
    (2026, 4, '2026-05-31'), (2026, 5, '2026-06-30'),
    (2026, 6, '2026-07-31'), (2026, 7, '2026-08-31'),
    (2026, 8, '2026-09-30'), (2026, 9, '2026-10-31'),
    (2026, 10, '2026-11-30'), (2026, 11, '2026-12-31'),
    (2026, 12, '2027-01-31'),
])
def test_calendar_default_window_crosses_month_and_year_boundaries(client, user, auth_headers, monkeypatch, year, month, last):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(year, month, 28, 23, 55, tzinfo=timezone.utc)
    monkeypatch.setattr(calendar_sync, 'datetime', Clock)
    response = client.get('/api/calendar/entries', headers=auth_headers(user.id))
    assert response.status_code == 200, response.json
    assert response.json['start_date'] == f'{year}-{month:02d}-01'
    assert response.json['end_date'] == last


@pytest.mark.parametrize('zone', ['Europe/London', 'America/Los_Angeles', 'Pacific/Auckland'])
def test_api_preserves_date_only_records_and_year_grouping(app, client, user, auth_headers, zone):
    user.timezone = zone
    user.currency = 'GBP'
    vehicle = Vehicle(user_id=user.id, name='Calendar boundaries')
    db.session.add(vehicle)
    db.session.flush()
    for day in [date(2024, 2, 29), date(2025, 12, 31), date(2026, 1, 1), date(2026, 7, 1)]:
        db.session.add(FuelEntry(user_id=user.id, vehicle_id=vehicle.id, date=day,
            liters=1, total_price=10, amount=10, currency='GBP',
            created_at=datetime(2026, 1, 1, 0, 30)))
    db.session.commit()
    headers = auth_headers(user.id)
    response = client.get('/api/calendar/entries?start_date=2024-01-01&end_date=2026-12-31', headers=headers)
    assert response.status_code == 200, response.json
    assert {row['date'] for row in response.json['entries']} == {'2024-02-29', '2025-12-31', '2026-01-01', '2026-07-01'}
    response = client.get(f'/api/vehicles/{vehicle.id}/expenses-summary?year=2026', headers=headers)
    assert response.status_code == 200, response.json
    assert response.json['totals']['fuel'] == 20
    assert next(row for row in response.json['monthly'] if row['month'] == '2026-01')['total'] == 10
    entry = FuelEntry.query.filter_by(vehicle_id=vehicle.id, date=date(2026, 1, 1)).one()
    assert entry.to_dict()['date'] == '2026-01-01'
    assert entry.to_dict()['created_at'] == '2026-01-01T00:30:00Z'
    assert entry.created_at == datetime(2026, 1, 1, 0, 30)
    assert client.get('/api/auth/me', headers=headers).json['created_at'].endswith('Z')


@pytest.mark.parametrize('zone,day', [
    ('Europe/London', '2026-07-01'),
    ('America/Los_Angeles', '2026-01-01'),
    ('Pacific/Auckland', '2024-02-29'),
])
def test_date_input_roundtrips_through_create_api(client, user, auth_headers, zone, day):
    user.timezone = zone
    vehicle = Vehicle(user_id=user.id, name='Local input')
    db.session.add(vehicle)
    db.session.commit()
    headers = auth_headers(user.id)
    response = client.post('/api/fuel', headers=headers, json={
        'vehicle_id': vehicle.id, 'date': day, 'liters': 2,
        'price_per_liter': 5, 'total_price': 10, 'odometer': 100,
        'currency': 'GBP',
    })
    assert response.status_code == 201, response.json
    assert response.json['entry']['date'] == day
    stored = db.session.get(FuelEntry, response.json['entry']['id'])
    assert stored.date == date.fromisoformat(day)
    response = client.get(f"/api/fuel/{stored.id}", headers=headers)
    assert response.status_code == 200
    assert response.json['date'] == day
    assert response.json['created_at'].endswith('Z')

"""Tests for F19 — the legacy endpoints that 500'd on first use.

Each endpoint referenced columns that don't exist (entry_date, cost,
next_service_date, valid_until, is_permit, location_name, Reminder.status),
raising AttributeError/ArgumentError at request time. These tests seed one
row per endpoint and assert 200 + the expected shape.
"""

from datetime import date, timedelta

import pytest

from app import db
from app.models import (
    Vehicle, ServiceEntry, RepairEntry, TaxEntry, ParkingEntry, Reminder,
)

TODAY = date.today()


@pytest.fixture
def vehicle(app, user):
    with app.app_context():
        v = Vehicle(user_id=user.id, name='Ioniq', make='Hyundai', model='Ioniq 5',
                    current_mileage=30000, distance_unit='km')
        db.session.add(v)
        db.session.commit()
        db.session.refresh(v)
        db.session.expunge(v)
        return v


def test_upcoming_services(app, client, user, auth_headers, vehicle):
    with app.app_context():
        db.session.add(ServiceEntry(user_id=user.id, vehicle_id=vehicle.id, amount=100,
                                    date=TODAY - timedelta(days=180), title='Oil',
                                    next_due_date=TODAY + timedelta(days=30)))
        # Past pointer and no pointer — both excluded.
        db.session.add(ServiceEntry(user_id=user.id, vehicle_id=vehicle.id, amount=90,
                                    date=TODAY - timedelta(days=400), title='Old',
                                    next_due_date=TODAY - timedelta(days=35)))
        db.session.add(ServiceEntry(user_id=user.id, vehicle_id=vehicle.id, amount=80,
                                    date=TODAY, title='No pointer'))
        db.session.commit()

    resp = client.get('/api/services/upcoming', headers=auth_headers(user.id))
    assert resp.status_code == 200
    entries = resp.get_json()['entries']
    assert len(entries) == 1
    assert entries[0]['title'] == 'Oil'


def test_service_stats(app, client, user, auth_headers, vehicle):
    with app.app_context():
        db.session.add(ServiceEntry(user_id=user.id, vehicle_id=vehicle.id, date=TODAY,
                                    amount=150, labor_cost=100, parts_cost=50,
                                    service_type='oil_change'))
        db.session.add(ServiceEntry(user_id=user.id, vehicle_id=vehicle.id, date=TODAY,
                                    amount=60, service_type='oil_change'))
        db.session.commit()

    resp = client.get('/api/services/stats', headers=auth_headers(user.id))
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['total_cost'] == 210.0
    assert data['total_labor_cost'] == 100.0
    assert data['by_type']['oil_change'] == {'count': 2, 'cost': 210.0}


def test_repair_stats(app, client, user, auth_headers, vehicle):
    with app.app_context():
        db.session.add(RepairEntry(user_id=user.id, vehicle_id=vehicle.id, date=TODAY,
                                   amount=300, repair_type='brakes', severity='high'))
        db.session.add(RepairEntry(user_id=user.id, vehicle_id=vehicle.id, date=TODAY,
                                   amount=200, repair_type='brakes',
                                   under_warranty=True))
        db.session.commit()

    resp = client.get('/api/repairs/stats', headers=auth_headers(user.id))
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['total_cost'] == 500.0
    assert data['warranty_savings'] == 200.0
    assert data['insurance_claims'] == 0.0
    assert data['by_severity']['high'] == 1
    assert data['by_type']['brakes']['count'] == 2


def test_expiring_taxes(app, client, user, auth_headers, vehicle):
    with app.app_context():
        db.session.add(TaxEntry(user_id=user.id, vehicle_id=vehicle.id, amount=15,
                                date=TODAY, tax_type='road_tax', title='Soon',
                                due_date=TODAY + timedelta(days=10)))
        db.session.add(TaxEntry(user_id=user.id, vehicle_id=vehicle.id, amount=15,
                                date=TODAY, tax_type='road_tax', title='Far',
                                due_date=TODAY + timedelta(days=90)))
        db.session.add(TaxEntry(user_id=user.id, vehicle_id=vehicle.id, amount=15,
                                date=TODAY, tax_type='road_tax', title='Past',
                                due_date=TODAY - timedelta(days=5)))
        db.session.commit()

    resp = client.get('/api/taxes/expiring?days=30', headers=auth_headers(user.id))
    assert resp.status_code == 200
    titles = [e['title'] for e in resp.get_json()['entries']]
    assert titles == ['Soon']


def test_tax_stats(app, client, user, auth_headers, vehicle):
    with app.app_context():
        db.session.add(TaxEntry(user_id=user.id, vehicle_id=vehicle.id, amount=120,
                                date=date(TODAY.year, 1, 10), tax_type='road_tax'))
        db.session.add(TaxEntry(user_id=user.id, vehicle_id=vehicle.id, amount=80,
                                date=date(TODAY.year - 1, 6, 1), tax_type='mot'))
        db.session.commit()

    resp = client.get('/api/taxes/stats', headers=auth_headers(user.id))
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['total_cost'] == 200.0
    assert data['yearly_breakdown'][str(TODAY.year)] == 120.0
    assert data['by_type']['mot']['cost'] == 80.0


def test_active_permits(app, client, user, auth_headers, vehicle):
    with app.app_context():
        db.session.add(ParkingEntry(user_id=user.id, vehicle_id=vehicle.id, amount=60,
                                    date=TODAY, parking_type='monthly', title='Active',
                                    permit_expires=TODAY + timedelta(days=20)))
        db.session.add(ParkingEntry(user_id=user.id, vehicle_id=vehicle.id, amount=60,
                                    date=TODAY - timedelta(days=60),
                                    parking_type='monthly', title='Expired',
                                    permit_expires=TODAY - timedelta(days=30)))
        db.session.add(ParkingEntry(user_id=user.id, vehicle_id=vehicle.id, amount=5,
                                    date=TODAY, parking_type='street', title='Street'))
        db.session.commit()

    resp = client.get('/api/parking/permits', headers=auth_headers(user.id))
    assert resp.status_code == 200
    permits = resp.get_json()['permits']
    assert [p['title'] for p in permits] == ['Active']


def test_parking_stats(app, client, user, auth_headers, vehicle):
    with app.app_context():
        db.session.add(ParkingEntry(user_id=user.id, vehicle_id=vehicle.id, amount=8,
                                    date=TODAY, parking_type='street',
                                    location='High St', duration_minutes=90))
        db.session.add(ParkingEntry(user_id=user.id, vehicle_id=vehicle.id, amount=12,
                                    date=TODAY, parking_type='street',
                                    location='High St'))
        db.session.commit()

    resp = client.get('/api/parking/stats', headers=auth_headers(user.id))
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['total_cost'] == 20.0
    assert data['total_duration_minutes'] == 90
    assert data['top_locations']['High St']['count'] == 2


def test_reminders_by_mileage(app, client, user, auth_headers, vehicle):
    with app.app_context():
        db.session.add(Reminder(user_id=user.id, vehicle_id=vehicle.id, title='Oil soon',
                                due_date=TODAY + timedelta(days=90), due_mileage=30500))
        db.session.add(Reminder(user_id=user.id, vehicle_id=vehicle.id, title='Far off',
                                due_date=TODAY + timedelta(days=365), due_mileage=45000))
        db.session.add(Reminder(user_id=user.id, vehicle_id=vehicle.id, title='Done',
                                due_date=TODAY, due_mileage=30100, completed=True))
        db.session.commit()

    resp = client.get(f'/api/reminders/by-mileage?vehicle_id={vehicle.id}',
                      headers=auth_headers(user.id))
    assert resp.status_code == 200
    data = resp.get_json()
    assert [r['title'] for r in data['reminders']] == ['Oil soon']
    assert data['current_mileage'] == 30000

    # vehicle_id is mandatory.
    assert client.get('/api/reminders/by-mileage',
                      headers=auth_headers(user.id)).status_code == 400


def test_suggest_reminder_survives_history_gathering(
        app, client, user, auth_headers, vehicle, monkeypatch):
    """The route must get PAST the history queries (the old AttributeError
    site) — the model call itself is mocked, mirroring test_fleet_chat.py."""
    import app.routes.vehicles as v

    app.config['OLLAMA_ENABLED'] = True
    app.config['OLLAMA_BASE_URL'] = 'http://localhost:11434'
    try:
        with app.app_context():
            db.session.add(ServiceEntry(user_id=user.id, vehicle_id=vehicle.id,
                                        date=TODAY - timedelta(days=90), amount=120,
                                        service_type='oil_change', odometer=28000))
            db.session.add(RepairEntry(user_id=user.id, vehicle_id=vehicle.id,
                                       date=TODAY - timedelta(days=30), amount=250,
                                       repair_type='brakes', severity='high',
                                       odometer=29500))
            db.session.commit()

        monkeypatch.setattr(v, 'resolve_model', lambda *_a, **_k: 'test-model')
        monkeypatch.setattr(v, 'ai_cache_get', lambda *_a, **_k: None)
        monkeypatch.setattr(v, 'ai_cache_set', lambda *_a, **_k: None)
        monkeypatch.setattr(v, 'ollama_chat', lambda **_k: {'suggestions': [{
            'title': 'Oil change', 'reminder_type': 'oil_change',
            'due_in_days': 60, 'priority': 'medium',
        }]})

        resp = client.post(f'/api/vehicles/{vehicle.id}/suggest-reminder',
                           json={}, headers=auth_headers(user.id))
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['suggestions'][0]['title'] == 'Oil change'
    finally:
        app.config['OLLAMA_ENABLED'] = False

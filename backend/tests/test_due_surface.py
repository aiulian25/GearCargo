"""Tests for F4 — unified "Due & Expiring" surface (GET /api/due)."""

from datetime import date, timedelta

from app import db
from app.models import (
    User, Vehicle, Reminder, ServiceEntry, TaxEntry, InsurancePolicy,
    Attachment, ParkingEntry, ConsumableEntry,
)

TODAY = date.today()


def _mk_vehicle(user_id, name='Focus', mileage=0, archived=False):
    v = Vehicle(user_id=user_id, name=name, make='Ford', model='Focus',
                current_mileage=mileage, archived=archived)
    db.session.add(v)
    db.session.commit()
    db.session.refresh(v)
    return v


def _seed_one_of_each(user_id, vehicle_id):
    """Seed a due/expiring record of every kind (all within the 30-day window)."""
    db.session.add(Reminder(
        user_id=user_id, vehicle_id=vehicle_id, title='Oil change',
        due_date=TODAY + timedelta(days=3), reminder_type='maintenance'))
    db.session.add(ServiceEntry(
        user_id=user_id, vehicle_id=vehicle_id, date=TODAY, amount=0,
        service_type='oil', next_due_date=TODAY + timedelta(days=10)))
    db.session.add(TaxEntry(
        user_id=user_id, vehicle_id=vehicle_id, date=TODAY, amount=0,
        tax_type='road_tax', next_due_date=TODAY + timedelta(days=15)))
    db.session.add(InsurancePolicy(
        user_id=user_id, vehicle_id=vehicle_id, provider='Acme',
        premium=500, status='active',
        start_date=TODAY - timedelta(days=340), end_date=TODAY + timedelta(days=20)))
    db.session.add(Attachment(
        user_id=user_id, vehicle_id=vehicle_id, filename='mot.pdf',
        filepath='/x/mot.pdf', original_filename='MOT.pdf',
        expires_at=TODAY + timedelta(days=25)))
    db.session.add(ParkingEntry(
        user_id=user_id, vehicle_id=vehicle_id, date=TODAY, amount=0,
        parking_type='permit', location='Downtown',
        permit_expires=TODAY + timedelta(days=12)))
    # Consumable worn to 100% → 'replace' (mileage-based).
    db.session.add(ConsumableEntry(
        user_id=user_id, vehicle_id=vehicle_id, date=TODAY, amount=0,
        consumable_type='tire', install_odometer=0, odometer=0,
        expected_lifespan_km=1000))
    db.session.commit()


def test_requires_auth(client):
    assert client.get('/api/due').status_code == 401


def test_merges_all_sources(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id, 'Golf', mileage=1000)  # 100% wear on the tire
        _seed_one_of_each(user.id, v.id)

    resp = client.get('/api/due', headers=auth_headers(user.id))
    assert resp.status_code == 200
    body = resp.get_json()
    kinds = {it['kind'] for it in body['items']}
    assert kinds == {'reminder', 'service', 'tax', 'insurance', 'document',
                     'parking', 'consumable'}
    assert body['count'] == len(body['items']) == 7
    # Every item deep-links and is labelled.
    for it in body['items']:
        assert it['link'] and it['link'].startswith('/')
        assert it['title']
        assert it['severity'] in ('critical', 'warning', 'info')


def test_overdue_reminder_sorts_above_future_insurance(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id, 'Golf')
        db.session.add(Reminder(
            user_id=user.id, vehicle_id=v.id, title='Overdue inspection',
            due_date=TODAY - timedelta(days=5), reminder_type='inspection'))
        db.session.add(InsurancePolicy(
            user_id=user.id, vehicle_id=v.id, provider='Acme', premium=500,
            status='active', start_date=TODAY - timedelta(days=340),
            end_date=TODAY + timedelta(days=20)))
        db.session.commit()

    items = client.get('/api/due', headers=auth_headers(user.id)).get_json()['items']
    assert items[0]['kind'] == 'reminder'
    assert items[0]['severity'] == 'critical'
    assert items[0]['days_left'] == -5
    assert items[1]['kind'] == 'insurance'
    assert items[1]['severity'] == 'info'  # 20 days out


def test_empty_fleet_returns_empty(app, client, user, auth_headers):
    resp = client.get('/api/due', headers=auth_headers(user.id))
    assert resp.status_code == 200
    assert resp.get_json() == {'items': [], 'count': 0}


def test_days_horizon_excludes_far_future(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id, 'Golf')
        db.session.add(Reminder(
            user_id=user.id, vehicle_id=v.id, title='Far reminder',
            due_date=TODAY + timedelta(days=200), reminder_type='maintenance'))
        db.session.commit()

    # Default 30-day window hides it…
    assert client.get('/api/due', headers=auth_headers(user.id)).get_json()['count'] == 0
    # …a wider window surfaces it.
    body = client.get('/api/due?days=365', headers=auth_headers(user.id)).get_json()
    assert body['count'] == 1
    assert body['items'][0]['kind'] == 'reminder'


def test_archived_vehicle_entries_excluded(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id, 'Archived', mileage=1000, archived=True)
        db.session.add(ServiceEntry(
            user_id=user.id, vehicle_id=v.id, date=TODAY, amount=0,
            service_type='oil', next_due_date=TODAY + timedelta(days=5)))
        db.session.commit()

    # Service on an archived vehicle must not surface.
    assert client.get('/api/due', headers=auth_headers(user.id)).get_json()['count'] == 0


def test_duplicates_collapse_to_most_urgent(app, client, user, auth_headers):
    """F39: same kind+vehicle+title collapses to ONE row (most urgent) with a count."""
    with app.app_context():
        v = _mk_vehicle(user.id, 'Golf')
        for days_ago in (30, 20, 10):  # three overdue MOT reminders
            db.session.add(Reminder(
                user_id=user.id, vehicle_id=v.id, title='MOT',
                due_date=TODAY - timedelta(days=days_ago), reminder_type='inspection'))
        db.session.commit()

    body = client.get('/api/due', headers=auth_headers(user.id)).get_json()
    assert body['count'] == 1
    item = body['items'][0]
    assert item['title'] == 'MOT'
    assert item['count'] == 3
    # The surviving row is the MOST urgent occurrence (furthest overdue).
    assert item['days_left'] == -30
    assert item['severity'] == 'critical'


def test_duplicates_not_merged_across_vehicles_or_kinds(app, client, user, auth_headers):
    with app.app_context():
        v1 = _mk_vehicle(user.id, 'Golf')
        v2 = _mk_vehicle(user.id, 'Qashqai')
        # Same title on two different vehicles → two rows.
        for vid in (v1.id, v2.id):
            db.session.add(Reminder(
                user_id=user.id, vehicle_id=vid, title='MOT',
                due_date=TODAY + timedelta(days=2), reminder_type='inspection'))
        # Same title, different kind (tax vs reminder) on v1 → separate row.
        db.session.add(TaxEntry(
            user_id=user.id, vehicle_id=v1.id, date=TODAY, amount=0,
            tax_type='road_tax', title='MOT', next_due_date=TODAY + timedelta(days=2)))
        db.session.commit()

    items = client.get('/api/due', headers=auth_headers(user.id)).get_json()['items']
    assert len(items) == 3
    assert all(it['count'] == 1 for it in items)


def test_ownership_isolation(app, client, user, auth_headers):
    with app.app_context():
        other = User(email='other@example.com', username='other', is_active=True)
        other.set_password('Str0ng!Passw0rd')
        db.session.add(other)
        db.session.commit()
        ov = _mk_vehicle(other.id, 'Theirs')
        db.session.add(Reminder(
            user_id=other.id, vehicle_id=ov.id, title='Their reminder',
            due_date=TODAY + timedelta(days=2), reminder_type='maintenance'))
        db.session.commit()

    # The requesting user sees none of the other user's due items.
    assert client.get('/api/due', headers=auth_headers(user.id)).get_json()['count'] == 0

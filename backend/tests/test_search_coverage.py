"""Tests for F8 / F49 — global search coverage across all searchable record fields."""

from datetime import date, timedelta

from app import db
from app.models import (
    User, Vehicle, Reminder, ServiceEntry, ParkingEntry, InsurancePolicy,
    FuelEntry, ConsumableEntry, TaxEntry, RepairEntry, Todo,
)

TODAY = date.today()


def _mk_user(email, username):
    u = User(email=email, username=username, is_active=True)
    u.set_password('Str0ng!Passw0rd')
    db.session.add(u)
    db.session.commit()
    return u


def _mk_vehicle(user_id, name='Focus'):
    v = Vehicle(user_id=user_id, name=name, make='Ford', model='Focus')
    db.session.add(v)
    db.session.commit()
    db.session.refresh(v)
    return v


def _seed(user_id, vehicle_id, tag):
    """Seed one of each new searchable record, stamped with a unique `tag`."""
    db.session.add(ServiceEntry(
        user_id=user_id, vehicle_id=vehicle_id, date=TODAY, amount=0,
        service_type='oil', garage_name=f'{tag}Garage'))
    db.session.add(ParkingEntry(
        user_id=user_id, vehicle_id=vehicle_id, date=TODAY, amount=0,
        parking_type='street', location=f'{tag}Lot'))
    db.session.add(InsurancePolicy(
        user_id=user_id, vehicle_id=vehicle_id, provider=f'{tag}Insure',
        policy_number=f'{tag}-POL-1', premium=500, status='active',
        start_date=TODAY - timedelta(days=10), end_date=TODAY + timedelta(days=300)))
    db.session.add(Reminder(
        user_id=user_id, vehicle_id=vehicle_id, title=f'{tag}Inspection',
        due_date=TODAY + timedelta(days=5), reminder_type='inspection'))
    # F49 — subtype identifier columns + todos.
    db.session.add(FuelEntry(
        user_id=user_id, vehicle_id=vehicle_id, date=TODAY, amount=60,
        station=f'{tag}Station'))
    db.session.add(ConsumableEntry(
        user_id=user_id, vehicle_id=vehicle_id, date=TODAY, amount=400,
        consumable_type='tire', brand=f'{tag}Brand'))
    db.session.add(TaxEntry(
        user_id=user_id, vehicle_id=vehicle_id, date=TODAY, amount=120,
        tax_type='road_tax', reference_number=f'{tag}-REF-9'))
    db.session.add(RepairEntry(
        user_id=user_id, vehicle_id=vehicle_id, date=TODAY, amount=250,
        diagnosis=f'{tag}Diagnosis', symptoms=f'{tag}Symptom'))
    db.session.add(Todo(
        user_id=user_id, vehicle_id=vehicle_id, title=f'{tag}Todo',
        due_date=TODAY + timedelta(days=3)))
    db.session.commit()


def test_garage_name_match_returns_service(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        _seed(user.id, v.id, 'Zqx')

    body = client.get('/api/search?q=ZqxGarage', headers=auth_headers(user.id)).get_json()
    assert body['total'] >= 1
    kinds = [e['type'] for e in body['results']['entries']]
    assert 'service' in kinds


def test_parking_location_match_returns_parking(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        _seed(user.id, v.id, 'Zqx')

    body = client.get('/api/search?q=ZqxLot', headers=auth_headers(user.id)).get_json()
    kinds = [e['type'] for e in body['results']['entries']]
    assert 'parking' in kinds


def test_provider_match_returns_policy(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        _seed(user.id, v.id, 'Zqx')

    body = client.get('/api/search?q=ZqxInsure', headers=auth_headers(user.id)).get_json()
    ins = body['results']['insurance']
    assert len(ins) == 1
    assert ins[0]['provider'] == 'ZqxInsure'
    assert ins[0]['vehicle_name'] == 'Focus'


def test_policy_number_match_returns_policy(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        _seed(user.id, v.id, 'Zqx')

    body = client.get('/api/search?q=Zqx-POL-1', headers=auth_headers(user.id)).get_json()
    assert len(body['results']['insurance']) == 1


def test_reminder_title_match_returns_reminder(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        _seed(user.id, v.id, 'Zqx')

    body = client.get('/api/search?q=ZqxInspection', headers=auth_headers(user.id)).get_json()
    rem = body['results']['reminders']
    assert len(rem) == 1
    assert rem[0]['title'] == 'ZqxInspection'


def test_fuel_station_match_returns_fuel(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        _seed(user.id, v.id, 'Zqx')

    body = client.get('/api/search?q=ZqxStation', headers=auth_headers(user.id)).get_json()
    kinds = [e['type'] for e in body['results']['entries']]
    assert 'fuel' in kinds


def test_consumable_brand_match_returns_consumable(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        _seed(user.id, v.id, 'Zqx')

    body = client.get('/api/search?q=ZqxBrand', headers=auth_headers(user.id)).get_json()
    kinds = [e['type'] for e in body['results']['entries']]
    assert 'consumable' in kinds


def test_tax_reference_match_returns_tax(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        _seed(user.id, v.id, 'Zqx')

    body = client.get('/api/search?q=Zqx-REF-9', headers=auth_headers(user.id)).get_json()
    kinds = [e['type'] for e in body['results']['entries']]
    assert 'tax' in kinds


def test_repair_diagnosis_match_returns_repair(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        _seed(user.id, v.id, 'Zqx')

    body = client.get('/api/search?q=ZqxDiagnosis', headers=auth_headers(user.id)).get_json()
    kinds = [e['type'] for e in body['results']['entries']]
    assert 'repair' in kinds


def test_repair_symptoms_match_returns_repair(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        _seed(user.id, v.id, 'Zqx')

    body = client.get('/api/search?q=ZqxSymptom', headers=auth_headers(user.id)).get_json()
    kinds = [e['type'] for e in body['results']['entries']]
    assert 'repair' in kinds


def test_todo_title_match_returns_todo(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        _seed(user.id, v.id, 'Zqx')

    body = client.get('/api/search?q=ZqxTodo', headers=auth_headers(user.id)).get_json()
    todos = body['results']['todos']
    assert len(todos) == 1
    assert todos[0]['title'] == 'ZqxTodo'
    assert todos[0]['vehicle_name'] == 'Focus'


def test_cross_user_isolation(app, client, user, auth_headers):
    with app.app_context():
        other = _mk_user('other8@example.com', 'other8')
        ov = _mk_vehicle(other.id, 'Theirs')
        _seed(other.id, ov.id, 'Secret')

    # The requesting user must never see the other user's matching records —
    # including every new F49 field (station, brand, tax ref, diagnosis, todo).
    for term in ('SecretStation', 'SecretBrand', 'Secret-REF-9',
                 'SecretDiagnosis', 'SecretTodo'):
        body = client.get(f'/api/search?q={term}', headers=auth_headers(user.id)).get_json()
        assert body['total'] == 0, term
        assert body['results']['entries'] == []
        assert body['results']['todos'] == []


def test_short_query_returns_new_groups(app, client, user, auth_headers):
    body = client.get('/api/search?q=a', headers=auth_headers(user.id)).get_json()
    assert 'reminders' in body['results']
    assert 'insurance' in body['results']
    assert 'todos' in body['results']
    assert body['total'] == 0

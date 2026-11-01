"""Feature proposal 3: real owner-scoped lifecycle, recovery and retry behavior."""
import copy
import json
import uuid
from datetime import date
from decimal import Decimal
from io import BytesIO
import pytest
from app import db
from app.models import Vehicle, ConsumableEntry, User, Attachment


@pytest.fixture
def car(user):
    vehicle = Vehicle(user_id=user.id, name='Tire test car', distance_unit='km', current_mileage=10000)
    db.session.add(vehicle); db.session.commit()
    return vehicle


def headers(auth_headers, user, record=None, key=None):
    result = {**auth_headers(user.id), 'Idempotency-Key': key or uuid.uuid4().hex, 'X-GearCargo-Mutation-Version': '1'}
    if record: result['If-Match'] = f'"{record["revision"]}"'
    return result


def create(client, user, car, auth_headers, **kw):
    response = client.post('/api/tire-sets', headers=headers(auth_headers, user), json={
        'vehicle_id': car.id, 'name': 'Summer set', 'tires': ['A', 'B', 'C', 'D'], **kw})
    assert response.status_code == 201, response.get_json()
    return response.json


def event(client, user, auth_headers, record, kind, odo, when='2026-01-01', positions=None, **kw):
    return client.post(f'/api/tire-sets/{record["id"]}/events', headers=headers(auth_headers, user, record, kw.get('key')),
        json={'kind': kind, 'date': when, 'odometer': odo, 'positions': positions or record['positions']})


def test_create_four_tire_identities(client, user, car, auth_headers):
    record = create(client, user, car, auth_headers)
    assert len(record['tires']) == 4 and record['positions'] == dict(zip(('FL', 'FR', 'RL', 'RR'), 'ABCD'))
    assert record['distance'] == 0 and record['installed'] is False


@pytest.mark.parametrize('unit,end,expected', [('km', 2609.344, 1609.344), ('miles', 2000, 1609.344)])
def test_seasonal_segments_rotation_replay_and_units(client, user, car, auth_headers, unit, end, expected):
    car.distance_unit = unit; db.session.commit()
    record = create(client, user, car, auth_headers)
    initial_ids = record['tires']
    response = event(client, user, auth_headers, record, 'install', 1000)
    assert response.status_code == 201; record = response.json
    positions = dict(zip(('FL', 'FR', 'RL', 'RR'), 'CDAB'))
    key = uuid.uuid4().hex
    response = event(client, user, auth_headers, record, 'rotate', 1500, '2026-02-01', positions, key=key)
    assert response.status_code == 201
    replay = event(client, user, auth_headers, record, 'rotate', 1500, '2026-02-01', positions, key=key)
    assert replay.status_code == 201 and replay.headers['Idempotent-Replay'] == 'true'
    record = replay.json
    assert record['tires'] == initial_ids and record['positions'] == positions and len(record['events']) == 2
    record = event(client, user, auth_headers, record, 'remove', end, '2026-03-01').json
    assert record['known_distance_km'] == pytest.approx(expected)
    car.current_mileage = 99999; db.session.commit()
    reread = client.get(f'/api/tire-sets/{record["id"]}', headers=auth_headers(user.id)).json
    assert reread['distance'] == record['distance'] and reread['installed'] is False
    record = event(client, user, auth_headers, reread, 'install', 100000, '2026-04-01').json
    assert record['unknown_intervals'] == 1  # current odometer behind fitment, never negative distance
    record = event(client, user, auth_headers, record, 'remove', 100100, '2026-05-01').json
    assert record['distance'] == pytest.approx(float(end) - 1000 + 100)


def test_missing_odometer_correction_and_stale_revision(client, user, car, auth_headers):
    record = create(client, user, car, auth_headers)
    record = event(client, user, auth_headers, record, 'install', None).json
    record = event(client, user, auth_headers, record, 'remove', 1500, '2026-02-01').json
    assert record['distance'] is None and record['unknown_intervals'] == 1
    stale = record
    result = client.put(f'/api/tire-sets/{record["id"]}/events/{record["events"][0]["id"]}',
        headers=headers(auth_headers, user, record), json={'date': '2026-01-01', 'odometer': 1000})
    assert result.status_code == 200 and result.json['distance'] == 500
    rejected = client.put(f'/api/tire-sets/{record["id"]}', headers=headers(auth_headers, user, stale), json={'name': 'Stale'})
    assert rejected.status_code == 409


@pytest.mark.parametrize('damage', ['overlap', 'backwards', 'duplicate_position', 'remove_stored', 'future', 'negative', 'nan'])
def test_invalid_fitments_do_not_change_history(client, user, car, auth_headers, damage):
    record = create(client, user, car, auth_headers)
    if damage != 'remove_stored': record = event(client, user, auth_headers, record, 'install', 1000).json
    if damage == 'overlap':
        another = create(client, user, car, auth_headers, name='Winter')
        response = event(client, user, auth_headers, another, 'install', 2000)
    else:
        positions = dict(record['positions'])
        if damage == 'duplicate_position': positions['FL'] = positions['FR']
        response = event(client, user, auth_headers, record, 'remove',
            {'backwards': 500, 'negative': -1, 'nan': 'NaN'}.get(damage, 2000),
            '2999-01-01' if damage == 'future' else '2026-02-01', positions)
    assert response.status_code == 400, response.get_json()
    assert client.get(f'/api/tire-sets/{record["id"]}', headers=auth_headers(user.id)).json['events'] == record['events']


def test_readings_threshold_due_and_owner_isolation(client, user, car, auth_headers):
    from app.services.due import build_due_items
    record = create(client, user, car, auth_headers, rotation_interval=1000, tread_unit='mm', tread_threshold=3.175)
    record = event(client, user, auth_headers, record, 'install', 1000).json
    key = uuid.uuid4().hex; request_headers = headers(auth_headers, user, record, key)
    payload = {'tire_id': record['tires'][0]['id'], 'date': '2026-02-01', 'depth': 4, 'unit': '32nds'}
    response = client.post(f'/api/tire-sets/{record["id"]}/readings', headers=request_headers, json=payload)
    assert response.status_code == 201 and set(response.json['alerts']) == {'rotation', 'tread'}
    assert client.post(f'/api/tire-sets/{record["id"]}/readings', headers=request_headers, json=payload).headers['Idempotent-Replay'] == 'true'
    record = response.json
    assert len(record['readings']) == 1
    due = [d for d in build_due_items(user.id) if d['kind'].startswith('tire_')]
    assert len(due) == 2 and all(d['link'] == f'/vehicles/{car.id}/tires' for d in due)
    stranger = User(username='tire-other', email='tire-other@example.invalid'); stranger.set_password('Test123456!')
    db.session.add(stranger); db.session.commit()
    assert client.get(f'/api/tire-sets/{record["id"]}', headers=auth_headers(stranger.id)).status_code == 404
    assert client.get(f'/api/tire-sets?vehicle_id={car.id}', headers=auth_headers(stranger.id)).status_code == 404
    response = client.post(f'/api/tire-sets/{record["id"]}/readings', headers=headers(auth_headers, stranger, record), json=payload)
    assert response.status_code in (404, 409)
    assert build_due_items(stranger.id) == []
    car.archived = True; db.session.commit()
    assert not [d for d in build_due_items(user.id) if d['kind'].startswith('tire_')]
    assert client.post(f'/api/tire-sets/{record["id"]}/readings', headers=headers(auth_headers, user, record), json=payload).status_code == 400


@pytest.mark.parametrize('depth', [-1, 'NaN', 'Infinity', None, 101, True])
def test_invalid_readings(client, user, car, auth_headers, depth):
    record = create(client, user, car, auth_headers)
    response = client.post(f'/api/tire-sets/{record["id"]}/readings', headers=headers(auth_headers, user, record),
        json={'tire_id': record['tires'][0]['id'], 'date': '2026-02-01', 'depth': depth, 'unit': 'mm'})
    assert response.status_code == 400


def test_purchase_receipt_and_lifecycle_roundtrip_once(client, user, car, auth_headers, tmp_path, monkeypatch):
    from app.routes import backup
    from app.models import TireSet, Tire, FitmentEvent, TreadReading
    from app.services.backup_schema import prepare_backup, BackupSchemaError
    monkeypatch.setattr(backup, 'get_uploads_folder', lambda: str(tmp_path / 'photos'))
    expense = ConsumableEntry(user_id=user.id, vehicle_id=car.id, date=date(2026, 1, 1), amount=400, currency='EUR', consumable_type='tire')
    db.session.add(expense); db.session.flush()
    receipt = tmp_path / 'receipt.pdf'; receipt.write_bytes(b'synthetic receipt')
    db.session.add(Attachment(user_id=user.id, vehicle_id=car.id, entry_id=expense.id, filename='receipt.pdf', filepath=str(receipt), file_size=17))
    db.session.commit()
    record = create(client, user, car, auth_headers, purchase_entry_id=expense.id)
    record = event(client, user, auth_headers, record, 'install', 1000).json
    record = event(client, user, auth_headers, record, 'remove', 2000, '2026-02-01').json
    response = client.post(f'/api/tire-sets/{record["id"]}/readings', headers=headers(auth_headers, user, record),
        json={'tire_id': record['tires'][0]['id'], 'date': '2026-02-01', 'depth': 5, 'unit': 'mm'})
    assert response.status_code == 201
    artifact, data = backup.create_backup_zip(user)
    assert len(data['vehicles'][0]['consumable_entries']) == 1 and len(data['tire_sets']) == 1
    damaged = copy.deepcopy(data); damaged['tire_fitments'][1]['odometer'] = '1'
    with pytest.raises(BackupSchemaError): prepare_backup(damaged)
    target = User(username='tire-target', email='tire-target@example.invalid'); target.set_password('Test123456!'); db.session.add(target); db.session.commit()
    with app_request_context(client):
        result = backup.restore_from_zip(target, BytesIO(artifact.getvalue()))
    assert result.status_code == 200, result.get_json()
    restored = TireSet.query.filter_by(user_id=target.id).one()
    assert restored.to_dict()['distance'] == 1000
    assert ConsumableEntry.query.filter_by(user_id=target.id).count() == 1
    assert restored.purchase_entry_id == ConsumableEntry.query.filter_by(user_id=target.id).one().id
    assert Tire.query.filter_by(user_id=target.id).count() == 4 and FitmentEvent.query.filter_by(user_id=target.id).count() == 2
    reading = TreadReading.query.filter_by(user_id=target.id).one()
    assert reading.tire_id in {t.id for t in restored.tires}
    with app_request_context(client): result = backup.restore_from_zip(target, BytesIO(artifact.getvalue()))
    assert result.status_code == 200 and TireSet.query.filter_by(user_id=target.id).count() == 1
    assert Attachment.query.filter_by(user_id=target.id).one().entry_id == restored.purchase_entry_id


def app_request_context(client):
    return client.application.test_request_context()


def test_vehicle_deletion_includes_all_tire_records(client, user, car, auth_headers):
    from app.models import TireSet, Tire, FitmentEvent, TreadReading
    from app.services.deletion import delete_owned_data
    record = create(client, user, car, auth_headers)
    record = event(client, user, auth_headers, record, 'install', 1000).json
    result = client.post(f'/api/tire-sets/{record["id"]}/readings', headers=headers(auth_headers, user, record),
        json={'tire_id': record['tires'][0]['id'], 'date': '2026-02-01', 'depth': 5, 'unit': 'mm'})
    assert result.status_code == 201
    delete_owned_data(user.id, vehicle_id=car.id)
    assert all(model.query.filter_by(user_id=user.id).count() == 0 for model in (TireSet, Tire, FitmentEvent, TreadReading))


def test_rotation_interval_survives_seasonal_storage(client, user, car, auth_headers):
    record = create(client, user, car, auth_headers, rotation_interval=100)
    record = event(client, user, auth_headers, record, 'install', 100).json
    record = event(client, user, auth_headers, record, 'remove', 180, '2026-02-01').json
    car.current_mileage = 330; db.session.commit()
    record = event(client, user, auth_headers, record, 'install', 300, '2026-03-01').json
    assert record['distance'] == 110 and record['rotation_remaining'] == -10
    assert record['alerts'] == ['rotation']
    positions = dict(zip(('FL', 'FR', 'RL', 'RR'), 'CDAB'))
    record = event(client, user, auth_headers, record, 'rotate', 320, '2026-04-01', positions).json
    assert record['distance'] == 110 and record['rotation_remaining'] == 90
    assert record['alerts'] == []

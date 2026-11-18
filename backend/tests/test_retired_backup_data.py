"""Backups written before format 4.8 carry data that no release keeps any more. They still import."""
from copy import deepcopy
from datetime import date
from decimal import Decimal

import pytest

from app import db
from app.models import FuelEntry, ImportIdentity, Todo, User, Vehicle
from app.services.backup_schema import (BackupSchemaError, USER_BACKUP_VERSION, _without_retired_data,
                                        export_user_data, import_records, prepare_backup)
from app.services.import_identity import digest, same_source

PREVIOUS_VERSION = '4.7'
RETIRED_PREDICTION_ID = 7
RETIRED_VEHICLE_VALUES = {'prediction_accuracy_score': 0.8, 'last_prediction_at': '2026-11-01T03:00:00'}
RETIRED_FUEL_VALUES = {'ocr_populated': False}


def other_user():
    user = User(username='destination', email='destination@example.invalid')
    user.set_password('FixturePassword123!')
    db.session.add(user)
    db.session.commit()
    return user


def account_with_records(user):
    car = Vehicle(user_id=user.id, name='Car', distance_unit='km')
    db.session.add(car)
    db.session.flush()
    db.session.add(FuelEntry(user_id=user.id, vehicle_id=car.id, date=date(2026, 1, 1),
                             amount=Decimal('60'), liters=Decimal('40'), odometer=1000))
    db.session.add(Todo(user_id=user.id, vehicle_id=car.id, title='Check the tyres'))
    db.session.commit()


def previous_release_backup(user):
    """The account as the previous release exported it, retired data included."""
    payload = export_user_data(user)
    payload['version'] = PREVIOUS_VERSION
    car = payload['vehicles'][0]
    car.update(RETIRED_VEHICLE_VALUES)
    for entry in car['fuel_entries']:
        entry.update(RETIRED_FUEL_VALUES)
    payload['predictions'] = [{'id': RETIRED_PREDICTION_ID, 'vehicle_id': car['id'],
                               'alert_type': 'oil_change', 'title': 'Oil change soon'}]
    payload['due_dismissals'].append({'id': 99, 'kind': 'prediction', 'ref_id': RETIRED_PREDICTION_ID})
    payload['user']['preferences']['email_smart_alerts'] = True
    return payload


def apply(user, payload):
    result = import_records(user, prepare_backup(deepcopy(payload)), 'merge', {}, {})
    db.session.commit()
    return result


def test_previous_release_backup_imports_without_its_retired_data(app, user):
    account_with_records(user)
    target = other_user()

    imported = apply(target, previous_release_backup(user))

    assert (imported['vehicles'], imported['fuel_entries'], imported['todos']) == (1, 1, 1)
    assert 'predictions' not in imported and imported['due_dismissals'] == 0
    assert Vehicle.query.filter_by(user_id=target.id).one().name == 'Car'


def test_current_format_refuses_the_retired_collection(app, user):
    account_with_records(user)
    payload = previous_release_backup(user)
    payload['version'] = USER_BACKUP_VERSION

    with pytest.raises(BackupSchemaError):
        prepare_backup(payload)


def test_file_fingerprint_is_taken_before_anything_is_dropped(app, user):
    account_with_records(user)
    payload = previous_release_backup(user)

    assert prepare_backup(deepcopy(payload)).batch_key == digest(payload)


def test_task_linked_to_a_prediction_becomes_a_plain_task():
    linked_to_prediction = {'id': 1, 'title': 'Replace the belt', 'prediction_id': RETIRED_PREDICTION_ID,
                            'todo_id': None, 'source_signature': 'a' * 64}
    linked_to_todo = {'id': 2, 'title': 'Check the tyres', 'prediction_id': None,
                      'todo_id': 5, 'source_signature': 'b' * 64}

    tasks = _without_retired_data({'appointment_tasks': [linked_to_prediction, linked_to_todo]})['appointment_tasks']

    assert tasks == [{'id': 1, 'title': 'Replace the belt', 'todo_id': None, 'source_signature': None},
                     {'id': 2, 'title': 'Check the tyres', 'todo_id': 5, 'source_signature': 'b' * 64}]


def test_provenance_from_the_previous_release_matches_the_same_record_today():
    today = {'name': 'Car', 'distance_unit': 'km'}

    assert same_source({**today, **RETIRED_VEHICLE_VALUES}, today)
    assert not same_source({**today, **RETIRED_VEHICLE_VALUES, 'name': 'Another car'}, today)


def test_repeat_of_a_file_the_previous_release_imported_is_not_a_conflict(app, user):
    account_with_records(user)
    payload = previous_release_backup(user)
    target = other_user()
    first = apply(target, payload)
    retired_values = {'vehicles': RETIRED_VEHICLE_VALUES, 'fuel_entries': RETIRED_FUEL_VALUES}
    for identity in ImportIdentity.query.filter_by(user_id=target.id):
        identity.source_payload = {**identity.source_payload, **retired_values.get(identity.entity_kind, {})}
        identity.source_hash = digest(identity.source_payload)
    db.session.commit()

    again = apply(target, payload)

    assert again['new_records'] == 0 and again['exact_repeats'] == first['new_records']
    assert Vehicle.query.filter_by(user_id=target.id).count() == 1

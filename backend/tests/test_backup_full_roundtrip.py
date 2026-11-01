"""GC-001: personal backups preserve stored data rather than display serializers."""
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from app import db
from app.models import (
    User, Vehicle, FuelEntry, ServiceEntry, RepairEntry, TaxEntry, ParkingEntry,
    ConsumableEntry, Reminder, Todo, InsurancePolicy, Attachment,
)


def make_target():
    target = User(username='restored', email='restored@example.invalid')
    target.set_password('TestOnlyPassword123!')
    db.session.add(target)
    db.session.commit()
    return target


def test_reported_roundtrip_preserves_units_money_tasks_and_receipt(app, user, tmp_path, monkeypatch):
    from app.routes import backup

    monkeypatch.setattr(backup, 'get_uploads_folder', lambda: str(tmp_path / 'photos'))
    vehicle = Vehicle(user_id=user.id, name='Backup car', distance_unit='miles',
                      purchase_price=Decimal('12345.67'), current_mileage=1234,
                      tank_capacity=Decimal('42.5'), monthly_budget=Decimal('0'),
                      maintenance_intervals={'oil_change': 5000}, vehicle_height_cm=150)
    db.session.add(vehicle)
    db.session.flush()
    service = ServiceEntry(user_id=user.id, vehicle_id=vehicle.id, date=date(2026, 1, 1),
                           amount=Decimal('50.01'), currency='GBP', service_type='oil_change',
                           service_types=['oil_change', 'inspection'], warranty_notes='Keep this',
                           warranty_expires=date(2027, 1, 1), labor_cost=Decimal('0'),
                           garage_phone='01234', postcode='TEST', notes='Service notes')
    consumable = ConsumableEntry(user_id=user.id, vehicle_id=vehicle.id,
                                date=date(2026, 2, 1), amount=Decimal('80'), currency='RON',
                                consumable_type='tire', install_odometer=1200, quantity=4)
    task = Todo(user_id=user.id, vehicle_id=vehicle.id, title='Check pressure', completed=True,
                completed_at=datetime(2026, 2, 2, 9), recurring=True, frequency='monthly',
                frequency_value=2, due_date=date(2026, 3, 2))
    db.session.add_all([service, consumable, task])
    db.session.flush()
    reminder = Reminder(user_id=user.id, vehicle_id=vehicle.id, source_service_id=service.id,
                        title='Next service', due_date=date(2027, 1, 1), due_mileage=5000,
                        snoozed_until=datetime(2026, 5, 1), completed=True, notify_push=False)
    receipt = tmp_path / 'receipt.jpg'
    receipt.write_bytes(b'synthetic-receipt')
    attachment = Attachment(user_id=user.id, vehicle_id=vehicle.id, entry_id=service.id,
                            filename='receipt.jpg', filepath=str(receipt), file_type='image/jpeg',
                            file_size=17, ocr_text='Receipt text', ocr_processed=True,
                            expires_at=date(2027, 2, 1), expiry_notified=True, tags=['warranty'])
    db.session.add_all([reminder, attachment])
    db.session.commit()
    archive, payload = backup.create_backup_zip(user)
    assert len(payload['vehicles'][0]['consumable_entries']) == 1
    target = make_target()
    with app.test_request_context():
        response = backup.restore_from_zip(target, BytesIO(archive.getvalue()))
    assert response.status_code == 200, response.get_json()
    restored = Vehicle.query.filter_by(user_id=target.id).one()
    assert restored.distance_unit == 'miles'
    assert restored.purchase_price == Decimal('12345.67')
    assert restored.monthly_budget == 0 and restored.vehicle_height_cm == 150
    assert restored.maintenance_intervals == {'oil_change': 5000}
    restored_service = ServiceEntry.query.filter_by(user_id=target.id).one()
    assert restored_service.currency == 'GBP' and restored_service.amount == Decimal('50.01')
    assert restored_service.warranty_notes == 'Keep this'
    assert restored_service.warranty_expires == date(2027, 1, 1)
    assert restored_service.labor_cost == 0 and restored_service.garage_phone == '01234'
    assert restored_service.service_types == ['oil_change', 'inspection']
    assert ConsumableEntry.query.filter_by(user_id=target.id).one().quantity == 4
    restored_task = Todo.query.filter_by(user_id=target.id).one()
    assert restored_task.vehicle_id == restored.id and restored_task.completed
    assert restored_task.completed_at == datetime(2026, 2, 2, 9)
    assert restored_task.recurring and restored_task.frequency_value == 2
    restored_reminder = Reminder.query.filter_by(user_id=target.id).one()
    assert restored_reminder.source_service_id == restored_service.id
    assert restored_reminder.due_mileage == 5000 and restored_reminder.completed
    assert restored_reminder.snoozed_until == datetime(2026, 5, 1)
    assert restored_reminder.notify_push is False
    restored_attachment = Attachment.query.filter_by(user_id=target.id).one()
    assert restored_attachment.entry_id == restored_service.id
    assert restored_attachment.expires_at == date(2027, 2, 1)
    assert restored_attachment.ocr_text == 'Receipt text' and restored_attachment.ocr_processed
    assert restored_attachment.expiry_notified and restored_attachment.tags == ['warranty']
    assert Path(restored_attachment.filepath).read_bytes() == b'synthetic-receipt'

import hashlib
import json
import zipfile
from copy import deepcopy

import pytest
from sqlalchemy import Boolean, Date, DateTime, Float, Integer, JSON, Numeric, String, inspect, null, text
from app.models import PredictionAlert, DueDismissal


# Independent ORM inventory: an added column must receive an explicit decision.
def test_every_supported_column_has_a_backup_decision():
    from app.services.backup_schema import MODELS, FIELDS, EXCLUDED_COLUMNS
    for kind, model in MODELS.items():
        assert set(FIELDS[kind]).isdisjoint(EXCLUDED_COLUMNS[kind])
        assert set(inspect(model).columns.keys()) == set(FIELDS[kind]) | set(EXCLUDED_COLUMNS[kind]), kind


def _stored_values(model, nullable):
    values = {}
    for column in inspect(model).columns:
        key = column.key
        if key in {'id', 'user_id', 'vehicle_id', 'type'} or column.foreign_keys:
            continue
        if nullable and column.nullable:
            values[key] = null() if not isinstance(column.type, JSON) else None
        elif isinstance(column.type, DateTime):
            values[key] = datetime(2025, 6, 7, 8, 9, 10)
        elif isinstance(column.type, Date):
            values[key] = date(2025, 6, 7)
        elif isinstance(column.type, Boolean):
            values[key] = False
        elif isinstance(column.type, Integer):
            values[key] = 0
        elif isinstance(column.type, Numeric):
            values[key] = Decimal('0')
        elif isinstance(column.type, Float):
            values[key] = 0.0
        elif isinstance(column.type, JSON):
            values[key] = {'sample': [0, False, None, 'păstrat']}
        elif isinstance(column.type, String):
            values[key] = 'x'
    # GC-014: keep the independent all-column roundtrip assertions, but seed
    # actual domain values rather than "x" enums/zero years/invalid JSON shapes.
    valid_domains = {
        'season': 'winter', 'tread_unit': 'mm', 'unit': 'mm', 'rotation_interval': 1000,
        'kind': 'install', 'positions': dict(zip(('FL', 'FR', 'RL', 'RR'), 'ABCD')),
        'year': 2020, 'tax_year': 2020, 'quantity': 1, 'frequency_value': 1,
        'expected_lifespan_km': 1, 'expected_lifespan_months': 1, 'repeat_mileage': 1,
        'currency': 'GBP', 'purchase_currency': 'GBP', 'distance_unit': 'km', 'fuel_type': 'petrol',
        'transmission': 'manual', 'drivetrain': 'fwd', 'severity': 'minor',
        'tax_type': 'road_tax', 'tax_period': 'annual', 'parking_type': 'street',
        'fine_status': 'paid', 'policy_type': 'comprehensive',
        'payment_frequency': 'annual', 'recurrence_type': 'annual',
        'priority': 'medium', 'frequency': 'monthly', 'reminder_type': 'custom',
        'service_type': 'oil_change', 'service_types': ['oil_change'],
        'repair_type': 'other', 'repair_types': ['other'], 'consumable_type': 'tire',
        'maintenance_intervals': {'oil_change': 5000},
        'status': 'paid' if model.__tablename__ == 'tax_entries' else 'active',
    }
    for key, value in valid_domains.items():
        if key in values and (not nullable or not inspect(model).columns[key].nullable):
            values[key] = value
    return values


@pytest.mark.parametrize('nullable', [False, True], ids=['zero-false-and-values', 'explicit-nulls'])
def test_all_stored_columns_and_relationships_roundtrip(app, user, tmp_path, monkeypatch, nullable):
    from app.routes import backup
    from app.services.backup_schema import MODELS, EXCLUDED_COLUMNS
    monkeypatch.setattr(backup, 'get_uploads_folder', lambda: str(tmp_path / 'photos'))
    if db.engine.dialect.name == 'sqlite':
        db.session.execute(text('PRAGMA foreign_keys=ON'))
    vehicle = Vehicle(user_id=user.id, **_stored_values(Vehicle, nullable))
    vehicle.photo = None
    # Tire history requires a declared vehicle distance unit.
    vehicle.distance_unit = 'km'
    db.session.add(vehicle)
    db.session.flush()
    source = {'vehicles': vehicle}
    for kind in ('fuel_entries', 'service_entries', 'repair_entries', 'tax_entries',
                 'parking_entries', 'consumable_entries', 'insurance_policies',
                 'reminders', 'todos', 'predictions', 'attachments'):
        model = MODELS[kind]
        values = _stored_values(model, nullable)
        if kind == 'fuel_entries':
            values['receipt_image'] = None  # unused legacy path, explicitly excluded
        if kind == 'reminders':
            for field in EXCLUDED_COLUMNS[kind]:
                if field != 'user_id':
                    values.pop(field, None)
        if kind == 'predictions':
            values['source_data'] = {'vehicle_id': vehicle.id, 'mileage_notified': True,
                                     'trigger_entry_id': source['fuel_entries'].id}
        if kind == 'attachments':
            path = tmp_path / 'full.jpg'; path.write_bytes(b'complete-file')
            values.update(filename='full.jpg', filepath=str(path), file_type='image/jpeg')
            if not nullable:
                values['original_filename'] = 'original.jpg'
        row = model(user_id=user.id, vehicle_id=vehicle.id, **values)
        db.session.add(row); db.session.flush()
        source[kind] = row
    for kind in ('tire_sets', 'tires', 'tire_fitments', 'tread_readings'):
        model = MODELS[kind]
        values = _stored_values(model, nullable)
        if kind == 'tire_sets':
            values['purchase_entry_id'] = source['consumable_entries'].id
        else:
            values['tire_set_id'] = source['tire_sets'].id
        if kind == 'tires':
            values['identifier'] = 'A'
        if kind == 'tread_readings':
            values['tire_id'] = source['tires'].id
        row = model(user_id=user.id, vehicle_id=vehicle.id, **values)
        db.session.add(row); db.session.flush(); source[kind] = row
    for identifier in 'BCD':
        db.session.add(MODELS['tires'](user_id=user.id, vehicle_id=vehicle.id,
            tire_set_id=source['tire_sets'].id, identifier=identifier))
    for kind in ('appointments', 'appointment_tasks', 'appointment_expenses'):
        model = MODELS[kind]
        values = _stored_values(model, nullable)
        if kind == 'appointments':
            values.update(status='completed', time_zone='Europe/London', start_at=datetime(2026, 1, 1, 9),
                end_at=datetime(2026, 1, 1, 17), confirmed_at=datetime(2025, 12, 1),
                dropoff_at=datetime(2026, 1, 1, 9), pickup_at=datetime(2026, 1, 1, 17),
                preparation_reminder_id=source['reminders'].id)
            source['reminders'].reminder_type = 'workshop_preparation'
        else:
            values['appointment_id'] = source['appointments'].id
        if kind == 'appointment_tasks':
            for field in ('reminder_id', 'service_id', 'prediction_id'): values[field] = None
            values['todo_id'] = source['todos'].id
        if kind == 'appointment_expenses': values['entry_id'] = source['repair_entries'].id
        row = model(user_id=user.id, vehicle_id=vehicle.id, **values)
        db.session.add(row); db.session.flush(); source[kind] = row
    from app.services.reconciliation import signature
    from app.services.import_identity import digest
    from app.models import StatementBatch, StatementTransaction, StatementMatch
    source['service_entries'].amount = Decimal('12.34')
    source['service_entries'].currency = 'GBP'
    selected_row = dict(row_number=2, date=date(2025,6,7), amount=Decimal('12.34'), currency='GBP', vendor='Selected vendor')
    statement = StatementBatch(user_id=user.id, name='Selected statement', source_key='a'*64,
        selection_hash=digest([selected_row]), status='open')
    db.session.add(statement); db.session.flush()
    transaction = StatementTransaction(user_id=user.id, batch_id=statement.id, fingerprint=digest(['a'*64,2]), **selected_row)
    db.session.add(transaction); db.session.flush()
    allocation = StatementMatch(user_id=user.id, transaction_id=transaction.id, entry_id=None if nullable else source['service_entries'].id,
        amount=Decimal('12.34'), entry_signature=signature(source['service_entries']))
    db.session.add(allocation); db.session.flush()
    source.update(statement_batches=statement, statement_transactions=transaction, statement_matches=allocation)
    source['tax_entries'].insurance_policy_id = source['insurance_policies'].id
    source['reminders'].source_service_id = source['service_entries'].id
    source['attachments'].entry_id = source['service_entries'].id
    source['insurance_policies'].document_attachment_id = source['attachments'].id
    # Self reference exercises the second pass without inventing a source FK.
    source['insurance_policies'].renewed_from_id = source['insurance_policies'].id
    dismissal = DueDismissal(user_id=user.id, kind='document', ref_id=source['attachments'].id,
                             due_date=None, created_at=datetime(2025, 6, 7, 8, 9, 10))
    db.session.add(dismissal); db.session.commit()
    source['due_dismissals'] = dismissal
    # Snapshot independently of the backup serializer.
    expected = {kind: {col.key: deepcopy(getattr(row, col.key)) for col in inspect(type(row)).columns}
                for kind, row in source.items()}
    archive, _ = backup.create_backup_zip(user)
    target = make_target()
    with app.test_request_context():
        response = backup.restore_from_zip(target, BytesIO(archive.getvalue()))
    assert response.status_code == 200, response.get_json()
    assert not response.get_json()['imported']['warnings']
    restored = {kind: (model.query.filter_by(user_id=target.id, identifier='A').one() if kind == 'tires'
                      else model.query.filter_by(user_id=target.id).one()) for kind, model in MODELS.items()}
    assert MODELS['tires'].query.filter_by(user_id=target.id).count() == 4
    assert restored['tire_sets'].purchase_entry_id == restored['consumable_entries'].id
    assert all(restored[kind].tire_set_id == restored['tire_sets'].id for kind in ('tires', 'tire_fitments', 'tread_readings'))
    assert restored['tread_readings'].tire_id == restored['tires'].id
    assert restored['statement_transactions'].batch_id == restored['statement_batches'].id
    assert restored['statement_matches'].transaction_id == restored['statement_transactions'].id
    assert restored['statement_matches'].entry_id == (None if nullable else restored['service_entries'].id)
    assert restored['appointments'].preparation_reminder_id == restored['reminders'].id
    assert restored['appointment_tasks'].appointment_id == restored['appointments'].id
    assert restored['appointment_tasks'].todo_id == restored['todos'].id
    assert restored['appointment_expenses'].appointment_id == restored['appointments'].id
    assert restored['appointment_expenses'].entry_id == restored['repair_entries'].id
    for kind, row in restored.items():
        ignored = set(EXCLUDED_COLUMNS[kind]) | {'id', 'vehicle_id', 'insurance_policy_id',
            'source_service_id', 'document_attachment_id', 'renewed_from_id', 'entry_id', 'ref_id',
            'purchase_entry_id', 'tire_set_id', 'tire_id', 'appointment_id', 'preparation_reminder_id', 'todo_id', 'batch_id', 'transaction_id'}
        for column, value in expected[kind].items():
            if column in ignored:
                continue
            # GC-015 recomputes derived values; this fixture has no full-to-full window.
            if kind == 'fuel_entries' and column in ('trip_distance', 'fuel_efficiency'):
                value = None
            if kind == 'vehicles' and column in ('avg_fuel_efficiency', 'cost_per_km', 'health_score', 'health_computed_at'):
                value = None
            if kind == 'predictions' and column == 'source_data':
                value = {**value, 'vehicle_id': restored['vehicles'].id,
                         'trigger_entry_id': restored['fuel_entries'].id}
            assert getattr(row, column) == value, (kind, column, getattr(row, column), value)
        assert row.user_id == target.id
    assert restored['tax_entries'].insurance_policy_id == restored['insurance_policies'].id
    assert restored['reminders'].source_service_id == restored['service_entries'].id
    assert restored['insurance_policies'].document_attachment_id == restored['attachments'].id
    assert restored['insurance_policies'].renewed_from_id == restored['insurance_policies'].id
    assert restored['attachments'].entry_id == restored['service_entries'].id
    assert restored['due_dismissals'].ref_id == restored['attachments'].id
    assert Path(restored['attachments'].filepath).read_bytes() == b'complete-file'


def test_portable_preferences_survive_but_security_and_integrations_stay_local(app, user):
    from app.routes.backup import gather_user_data, import_backup_data
    user.language = 'ro'; user.currency = 'RON'; user.distance_unit = 'miles'
    user.volume_unit = 'gallons'; user.date_format = 'YYYY-MM-DD'
    user.preferences = {'seasonal_checklists': {'winter': {'completed': ['tires']}},
                        'checklist_settings': {'enabled': False}, 'calendar_password': 'DO-NOT-EXPORT'}
    user.calendar_password = 'DO-NOT-EXPORT'
    db.session.commit()
    payload = gather_user_data(user, False)
    assert 'DO-NOT-EXPORT' not in json.dumps(payload)
    assert 'password_hash' not in json.dumps(payload) and 'is_admin' not in json.dumps(payload)
    target = make_target(); old_hash = target.password_hash
    target.preferences = {'integration_setting': 'keep'}; target.calendar_password = 'KEEP-LOCAL'
    db.session.commit()
    import_backup_data(target, payload)
    assert target.language == 'ro' and target.currency == 'RON'
    assert target.distance_unit == 'miles' and target.volume_unit == 'gallons'
    assert target.date_format == 'YYYY-MM-DD'
    assert target.preferences['seasonal_checklists'] == {'winter': {'completed': ['tires']}}
    assert target.preferences['integration_setting'] == 'keep'
    assert target.calendar_password == 'KEEP-LOCAL' and target.password_hash == old_hash
    assert target.email == 'restored@example.invalid' and not target.is_admin


@pytest.mark.parametrize('version', [None, '1.0', '2.0'])
def test_legacy_gaps_are_reported_and_never_guess_units_or_currency(app, user, version):
    from app.routes.backup import import_backup_data
    payload = {'vehicles': [{'id': 1, 'name': 'Old car', 'fuel_entries': [
        {'id': 2, 'date': '2026-01-01T00:00:00', 'amount': 0, 'total_cost': 99, 'liters': 0,
         'volume': 10, 'odometer': 0, 'mileage': 100}]}],
        'todos': [{'id': 3, 'vehicle_id': 1, 'title': 'Legacy task', 'completed': True,
                   'due_date': '2026-02-01', 'recurring': True, 'frequency': 'monthly'}]}
    if version is not None:
        payload['version'] = version
    result, _, _ = import_backup_data(user, payload)
    assert result['todos'] == 1 and result['warnings'][0]['code'] == 'legacy_incomplete'
    vehicle = Vehicle.query.filter_by(user_id=user.id).one()
    fuel = FuelEntry.query.filter_by(user_id=user.id).one()
    assert vehicle.distance_unit is None and fuel.currency is None
    assert fuel.amount == 0 and fuel.odometer == 0 and fuel.liters == 0
    task = Todo.query.filter_by(user_id=user.id).one()
    assert task.completed and task.recurring and task.vehicle_id == vehicle.id


@pytest.mark.parametrize('mutation', ['version', 'unknown_collection', 'unknown_field', 'missing_field',
                                     'bad_todo', 'unknown_reference', 'account_permissions', 'unknown_json_reference'])
def test_invalid_current_backup_is_rejected_before_writing(app, client, user, auth_headers, mutation):
    from app.routes.backup import gather_user_data
    vehicle = Vehicle(user_id=user.id, name='Source'); db.session.add(vehicle); db.session.flush()
    db.session.add(Todo(user_id=user.id, vehicle_id=vehicle.id, title='A task'))
    db.session.add(PredictionAlert(user_id=user.id, vehicle_id=vehicle.id,
                                   alert_type='maintenance', description='Test', source_data={}))
    db.session.commit()
    data = gather_user_data(user, False)
    if mutation == 'version': data['version'] = '999.0'
    elif mutation == 'unknown_collection': data['new_records'] = [{}]
    elif mutation == 'unknown_field': data['todos'][0]['future_field'] = True
    elif mutation == 'missing_field': del data['todos'][0]['completed']
    elif mutation == 'bad_todo': data['todos'][0]['title'] = None
    elif mutation == 'unknown_reference': data['todos'][0]['vehicle_id'] = 987654
    elif mutation == 'account_permissions': data['user']['preferences']['is_admin'] = True
    elif mutation == 'unknown_json_reference': data['predictions'][0]['source_data']['trigger_entry_id'] = 987654
    target = make_target()
    response = client.post('/api/backup/import', headers=auth_headers(target.id), data={
        'file': (BytesIO(json.dumps(data).encode()), 'backup.json')})
    assert response.status_code == 400, response.get_json()
    assert response.get_json()['issues'][0]['path']
    assert Vehicle.query.filter_by(user_id=target.id).count() == 0
    assert Todo.query.filter_by(user_id=target.id).count() == 0


def test_same_day_same_amount_and_same_title_records_survive_fresh_restore(app, user):
    from app.routes.backup import gather_user_data, import_backup_data
    vehicle = Vehicle(user_id=user.id, name='Car'); db.session.add(vehicle); db.session.flush()
    for kind in ['oil_change', 'inspection']:
        db.session.add(ServiceEntry(user_id=user.id, vehicle_id=vehicle.id, date=date(2026, 1, 1),
                                    amount=50, service_type=kind))
        db.session.add(Todo(user_id=user.id, vehicle_id=vehicle.id, title='Check', description=kind))
    db.session.commit()
    payload = gather_user_data(user, False); target = make_target()
    imported, _, _ = import_backup_data(target, payload)
    assert imported['service_entries'] == 2 and imported['todos'] == 2
    assert {s.service_type for s in ServiceEntry.query.filter_by(user_id=target.id)} == {'oil_change', 'inspection'}


def test_data_only_restores_document_metadata_and_reports_missing_bytes(app, user, tmp_path):
    from app.routes.backup import gather_user_data, restore_from_json
    vehicle = Vehicle(user_id=user.id, name='Car'); db.session.add(vehicle); db.session.flush()
    db.session.add(Attachment(user_id=user.id, vehicle_id=vehicle.id, filename='missing.pdf',
                              filepath=str(tmp_path / 'not-there'), ocr_text='Keep extracted text'))
    db.session.commit()
    data = gather_user_data(user, False); target = make_target()
    with app.test_request_context():
        response = restore_from_json(target, BytesIO(json.dumps(data).encode()))
    assert response.status_code == 200
    assert any(w['code'] == 'media_omitted' for w in response.get_json()['imported']['warnings'])
    doc = Attachment.query.filter_by(user_id=target.id).one()
    assert doc.ocr_text == 'Keep extracted text' and not Path(doc.filepath).exists()


def test_full_backup_missing_source_file_fails_instead_of_succeeding(app, user, tmp_path):
    from app.routes.backup import create_backup_zip
    from app.services.backup_schema import BackupSchemaError
    db.session.add(Attachment(user_id=user.id, filename='missing.pdf', filepath=str(tmp_path / 'gone')))
    db.session.commit()
    with pytest.raises(BackupSchemaError, match='referenced file is missing'):
        create_backup_zip(user)


def test_same_named_different_files_and_vehicle_photo_keep_their_hashes(app, user, tmp_path, monkeypatch):
    from app.routes import backup
    photos = tmp_path / 'photos'; (photos / 'vehicles').mkdir(parents=True)
    monkeypatch.setattr(backup, 'get_uploads_folder', lambda: str(photos))
    (photos / 'vehicles' / 'photo.jpg').write_bytes(b'vehicle-photo')
    saved_timestamp = datetime(2024, 6, 1, 12, 30)
    vehicle = Vehicle(user_id=user.id, name='Car', photo='/uploads/vehicles/photo.jpg',
                      updated_at=saved_timestamp)
    db.session.add(vehicle); db.session.flush()
    for i, content in enumerate([b'first-file', b'different-file', b'long-filename']):
        path = tmp_path / f'{i}.jpg'; path.write_bytes(content)
        db.session.add(Attachment(user_id=user.id, vehicle_id=vehicle.id,
                                  filename='receipt.jpg' if i < 2 else 'r' * 240 + '.jpg',
                                  filepath=str(path), description=str(i)))
    db.session.commit()
    archive, _ = backup.create_backup_zip(user); target = make_target()
    with app.test_request_context():
        response = backup.restore_from_zip(target, BytesIO(archive.getvalue()))
    assert response.status_code == 200, response.get_json()
    docs = Attachment.query.filter_by(user_id=target.id).order_by(Attachment.description).all()
    assert [hashlib.sha256(Path(a.filepath).read_bytes()).hexdigest() for a in docs] == [
        hashlib.sha256(content).hexdigest() for content in [b'first-file', b'different-file', b'long-filename']]
    assert docs[2].filename == 'r' * 240 + '.jpg'
    restored = Vehicle.query.filter_by(user_id=target.id).one()
    assert (photos / 'vehicles' / Path(restored.photo).name).read_bytes() == b'vehicle-photo'
    assert restored.updated_at == saved_timestamp


def test_json_export_reports_data_only_and_validates_records(app, client, user, auth_headers):
    headers = auth_headers(user.id)
    vehicle = Vehicle(user_id=user.id, name='Car')
    db.session.add(vehicle)
    db.session.commit()
    response = client.post('/api/backup/export', json={'format': 'json'}, headers=headers)
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['version'] == '4.7' and data['media_included'] is False
    assert any(w['code'] == 'media_omitted' for w in data['warnings'])
    # Invalid stored references must not produce a supposedly complete JSON backup.
    other = make_target()
    other_vehicle = Vehicle(user_id=other.id, name='Other car')
    db.session.add(other_vehicle)
    db.session.flush()
    other_service = ServiceEntry(user_id=other.id, vehicle_id=other_vehicle.id, date=date(2026, 1, 1))
    db.session.add(other_service)
    db.session.flush()
    reminder = Reminder(user_id=user.id, title='Bad reference', due_date=date(2027, 1, 1),
                        source_service_id=other_service.id)
    db.session.add(reminder)
    db.session.commit()
    response = client.post('/api/backup/export', json={'format': 'json'}, headers=headers)
    assert response.status_code == 400
    assert response.get_json()['issues'][0]['path'].endswith('.source_service_id')


@pytest.mark.parametrize('damage', ['missing', 'corrupt', 'data', 'future_manifest'])
def test_damaged_zip_rejected_before_records(app, user, tmp_path, damage):
    from app.routes import backup
    path = tmp_path / 'a.jpg'; path.write_bytes(b'file')
    db.session.add(Attachment(user_id=user.id, filename='a.jpg', filepath=str(path)))
    db.session.commit()
    original, _ = backup.create_backup_zip(user)
    changed = BytesIO()
    with zipfile.ZipFile(original) as source, zipfile.ZipFile(changed, 'w') as dest:
        for name in source.namelist():
            body = source.read(name)
            if name.startswith('attachments/'):
                if damage == 'missing': continue
                if damage == 'corrupt': body = b'corrupt'
            if name == 'backup_data.json' and damage == 'data':
                body += b' '
            if name == 'manifest.json' and damage == 'future_manifest':
                data = json.loads(body); data['version'] = '99.0'; body = json.dumps(data).encode()
            dest.writestr(name, body)
    target = make_target(); changed.seek(0)
    with app.test_request_context():
        response, status = backup.restore_from_zip(target, changed)
    assert status == 400, response.get_json()
    assert Attachment.query.filter_by(user_id=target.id).count() == 0


def test_all_models_and_account_columns_have_explicit_scope():
    from app.services.backup_schema import MODELS, EXCLUDED_MODELS, PREFERENCE_FIELDS, ACCOUNT_EXCLUDED_COLUMNS
    assert {m.class_.__name__ for m in db.Model.registry.mappers} == {m.__name__ for m in MODELS.values()} | set(EXCLUDED_MODELS)
    assert set(inspect(User).columns.keys()) == set(PREFERENCE_FIELDS) | set(ACCOUNT_EXCLUDED_COLUMNS) | {'preferences'}


def test_unlinked_reminder_and_todo_are_not_silently_skipped(app, user):
    from app.routes.backup import gather_user_data, import_backup_data
    db.session.add(Reminder(user_id=user.id, title='Global reminder', due_date=date(2027, 1, 1)))
    db.session.add(Todo(user_id=user.id, title='Global task', completed=True))
    db.session.commit()
    data = gather_user_data(user, False); target = make_target()
    result, _, _ = import_backup_data(target, data)
    assert result['reminders'] == 1 and result['todos'] == 1
    assert Reminder.query.filter_by(user_id=target.id).one().vehicle_id is None
    assert Todo.query.filter_by(user_id=target.id).one().vehicle_id is None

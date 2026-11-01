"""GC-016: provenance is identity; content similarity never removes an expense."""
import json
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import User, Vehicle, ServiceEntry, TaxEntry, Reminder, Attachment, ImportBatch, ImportIdentity
from app.routes import backup
from app.services.backup_schema import export_user_data, prepare_backup, import_records, BackupSchemaError
from app.services.csv_io import import_entries_csv, export_entries_csv
from app.services.import_identity import ImportPlan, ImportConflict
from app.services.lubelog_import import import_lubelog_to_gearcargo
from test_lubelog_import import _lubelog_zip, VEHICLE_ONE


def other_user(name='destination'):
    user = User(username=name, email=f'{name}@example.invalid')
    user.set_password('FixturePassword123!')
    db.session.add(user)
    db.session.commit()
    return user


def vehicle(user, **kwargs):
    result = Vehicle(user_id=user.id, name='Car', **kwargs)
    db.session.add(result)
    db.session.commit()
    return result


def source_graph(user):
    car = vehicle(user)
    vehicle(user)  # No plate/VIN: two equal-looking cars remain distinct.
    for title in ('Oil service', 'Inspection', 'Inspection'):
        db.session.add(ServiceEntry(user_id=user.id, vehicle_id=car.id, date=date(2026, 1, 1),
                                    amount=Decimal('50'), title=title))
    for due in (date(2026, 6, 1), date(2026, 7, 1)):
        db.session.add(Reminder(user_id=user.id, vehicle_id=car.id, title='Service', due_date=due))
    db.session.commit()
    return export_user_data(user)


def apply(user, payload, **kwargs):
    result = import_records(user, prepare_backup(deepcopy(payload)), 'merge', {}, {}, **kwargs)
    db.session.commit()
    return result


def csv_rows(car, values, ids=False):
    header = ('source_id,' if ids else '') + 'vehicle_id,date,amount,title\n'
    return header + ''.join((f'{source_id},' if ids else '') + f'{car.id},2026-01-01,{amount},Service\n'
                           for source_id, amount in values)


def test_backup_equal_costs_occurrences_unidentified_cars_and_replay(app, user):
    payload = source_graph(user)
    target = other_user()
    first = apply(target, payload)
    assert (first['vehicles'], first['service_entries'], first['reminders']) == (2, 3, 2)
    assert sum(row.amount for row in ServiceEntry.query.filter_by(user_id=target.id)) == 150
    assert len({row.due_date for row in Reminder.query.filter_by(user_id=target.id)}) == 2
    again = apply(target, payload)
    assert again['new_records'] == 0 and again['exact_repeats'] == 7
    assert ImportIdentity.query.filter_by(user_id=target.id).count() == 7
    assert ImportBatch.query.filter_by(user_id=target.id).count() == 1
    payload['source_namespace'] = 'another-source'
    preview = ImportPlan(target, prepare_backup(payload)).preview
    assert preview['new_records'] == 7 and preview['possible_duplicates'] == 7
    assert apply(target, payload)['service_entries'] == 3
    assert sum(row.amount for row in ServiceEntry.query.filter_by(user_id=target.id)) == 300


def test_changed_source_requires_decision_preserves_original_and_local_edits(app, user):
    payload = source_graph(user)
    target = other_user()
    apply(target, payload)
    existing = ServiceEntry.query.filter_by(user_id=target.id).first()
    existing.title = 'Local correction'
    db.session.commit()
    assert apply(target, payload)['exact_repeats'] == 7
    assert existing.title == 'Local correction'
    edited = deepcopy(payload)
    edited['vehicles'][0]['service_entries'][0]['amount'] = '99'
    with pytest.raises(ImportConflict):
        apply(target, edited)
    db.session.rollback()
    assert ImportBatch.query.filter_by(user_id=target.id).count() == 1
    result = apply(target, edited, conflict_policy='keep_existing')
    assert result['skipped_conflicts'] == 1 and existing.amount == 50
    receipt = ImportIdentity.query.filter_by(user_id=target.id, entity_kind='service_entries', target_id=existing.id).one()
    assert receipt.original_payload['amount'] == '50' and receipt.source_payload['amount'] == '99'
    assert apply(target, edited)['new_records'] == 0


def test_csv_equal_rows_replay_namespaces_and_native_export(app, user):
    car = vehicle(user)
    text = csv_rows(car, [(None, 50), (None, 50)])
    assert import_entries_csv(user, 'service', text)['created'] == 2
    assert import_entries_csv(user, 'service', text)['skipped'] == 2
    stable = csv_rows(car, [('10', 50), ('11', 50)], ids=True)
    assert import_entries_csv(user, 'service', stable, source_label='Garage A')['created'] == 2
    assert import_entries_csv(user, 'service', stable, source_label='Garage B')['created'] == 2
    assert import_entries_csv(user, 'service', stable, source_label='Garage A')['skipped'] == 2
    exported = export_entries_csv(user, 'service')
    assert import_entries_csv(user, 'service', exported)['created'] == 0
    assert ServiceEntry.query.count() == 6
    changed = csv_rows(car, [('10', 60), ('11', 50)], ids=True)
    with pytest.raises(ImportConflict):
        import_entries_csv(user, 'service', changed, source_label='Garage A')
    db.session.rollback()
    assert sum(row.amount for row in ServiceEntry.query.all()) == 300


def test_preview_is_read_only_and_stale_preview_rejected(app, user, client, auth_headers):
    car = vehicle(user)
    text = csv_rows(car, [('10', 50), ('11', 50)], ids=True)
    headers = auth_headers(user.id)
    def post(**options):
        return client.post('/api/backup/import/csv', headers=headers, data={
            'file': (BytesIO(text.encode()), 'services.csv'), 'type': 'service', 'source_label': 'Garage', **options})
    result = post(preview='true')
    assert result.status_code == 200, result.json
    assert result.json['preview']['new_records'] == 2
    assert ServiceEntry.query.count() == ImportIdentity.query.count() == ImportBatch.query.count() == 0
    token = result.json['preview']['preview_token']
    assert post(preview_token=token).status_code == 200
    stale = post(preview_token=token)
    assert stale.status_code == 409 and stale.json['code'] == 'IMPORT_REVIEW_REQUIRED'
    assert ServiceEntry.query.count() == 2
    assert post(preview_token=stale.json['preview']['preview_token']).status_code == 200


def test_duplicate_source_ids_and_invalid_metadata_fail_without_writes(app, user):
    car = vehicle(user)
    text = csv_rows(car, [('10', 50), ('10', 70)], ids=True)
    with pytest.raises(ValueError, match='Duplicate source'):
        import_entries_csv(user, 'service', text)
    assert ServiceEntry.query.count() == ImportIdentity.query.count() == 0
    payload = export_user_data(user)
    payload['source_metadata'] = [{'kind': []}]
    with pytest.raises(BackupSchemaError):
        prepare_backup(payload)


def test_deleted_target_is_not_resurrected_and_owner_isolation(app, user):
    car = vehicle(user)
    text = csv_rows(car, [('10', 50)], ids=True)
    import_entries_csv(user, 'service', text, source_label='Garage')
    row = ServiceEntry.query.one()
    db.session.delete(row)
    db.session.commit()
    with pytest.raises(ImportConflict):
        import_entries_csv(user, 'service', text, source_label='Garage')
    db.session.rollback()
    assert import_entries_csv(user, 'service', text, source_label='Garage', conflict_policy='keep_existing')['created'] == 0
    assert ServiceEntry.query.count() == 0
    second = other_user()
    car2 = vehicle(second)
    assert import_entries_csv(second, 'service', csv_rows(car2, [('10', 50)], ids=True), source_label='Garage')['created'] == 1


def test_export_import_preserves_original_source_aliases(app, user):
    payload = source_graph(user)
    middle = other_user('middle')
    apply(middle, payload)
    transported = export_user_data(middle)
    target = other_user('target')
    apply(target, transported)
    assert apply(target, payload)['new_records'] == 0
    assert ImportIdentity.query.filter_by(user_id=target.id).count() == 14
    assert ServiceEntry.query.filter_by(user_id=target.id).count() == 3
    assert all(item['original_payload'] for item in export_user_data(target)['source_metadata'])


def zip_graph(user, tmp_path, monkeypatch):
    monkeypatch.setattr(backup, 'get_uploads_folder', lambda: str(tmp_path / 'photos'))
    source_graph(user)
    car = Vehicle.query.filter_by(user_id=user.id).first()
    photos = tmp_path / 'photos' / 'vehicles'
    photos.mkdir(parents=True)
    (photos / 'source.jpg').write_bytes(b'photo')
    car.photo = '/uploads/vehicles/source.jpg'
    source = tmp_path / 'receipt.jpg'
    source.write_bytes(b'shared receipt bytes')
    for row in ServiceEntry.query.filter_by(user_id=user.id).limit(2):
        db.session.add(Attachment(user_id=user.id, vehicle_id=car.id, entry_id=row.id,
            filename='receipt.jpg', filepath=str(source), file_size=20))
    db.session.commit()
    archive, data = backup.create_backup_zip(user)
    return archive.getvalue(), data


def restore_zip(app, user, archive):
    with app.test_request_context():
        response = backup.restore_from_zip(user, BytesIO(archive))
    return response if isinstance(response, tuple) else (response, response.status_code)


def test_zip_replay_receipt_bytes_distinct_links_and_photo_are_stable(app, user, tmp_path, monkeypatch):
    archive, _ = zip_graph(user, tmp_path, monkeypatch)
    target = other_user()
    response, status = restore_zip(app, target, archive)
    assert status == 200, response.json
    rows = Attachment.query.filter_by(user_id=target.id).all()
    assert len(rows) == 2 and len({row.entry_id for row in rows}) == 2
    assert len({row.filepath for row in rows}) == 1
    assert Path(rows[0].filepath).read_bytes() == b'shared receipt bytes'
    photo = Vehicle.query.filter_by(user_id=target.id).first().photo
    files = sorted(str(path) for path in tmp_path.rglob('*') if path.is_file() and 'restore_' in path.name)
    response, status = restore_zip(app, target, archive)
    assert status == 200 and response.json['imported']['new_records'] == 0
    assert Vehicle.query.filter_by(user_id=target.id).first().photo == photo
    assert files == sorted(str(path) for path in tmp_path.rglob('*') if path.is_file() and 'restore_' in path.name)
    assert Attachment.query.filter_by(user_id=target.id).count() == 2


def test_json_then_zip_materializes_existing_documents(app, user, tmp_path, monkeypatch):
    archive, payload = zip_graph(user, tmp_path, monkeypatch)
    target = other_user()
    with app.test_request_context():
        response = backup.restore_from_json(target, BytesIO(json.dumps(payload).encode()))
    assert response.status_code == 200
    before = {row.id: row.filepath for row in Attachment.query.filter_by(user_id=target.id)}
    assert not any(Path(path).exists() for path in before.values())
    response, status = restore_zip(app, target, archive)
    assert status == 200, response.json
    assert response.json['imported']['new_records'] == 0
    assert before == {row.id: row.filepath for row in Attachment.query.filter_by(user_id=target.id)}
    assert all(Path(path).read_bytes() == b'shared receipt bytes' for path in before.values())


def test_restore_failure_rolls_back_provenance_records_and_files(app, user, tmp_path, monkeypatch):
    archive, _ = zip_graph(user, tmp_path, monkeypatch)
    target = other_user()
    def fail(name, *args):
        if name == 'after_db_write':
            raise OSError('Synthetic disk failure')
    monkeypatch.setattr(backup.restore_tx, 'checkpoint', fail)
    response, status = restore_zip(app, target, archive)
    assert status == 500 and response.json['recovery']['state'] == 'rolled_back'
    assert Vehicle.query.filter_by(user_id=target.id).count() == 0
    assert ImportBatch.query.filter_by(user_id=target.id).count() == 0
    assert ImportIdentity.query.filter_by(user_id=target.id).count() == 0


def lube_records(amount=50.0):
    car = {**VEHICLE_ONE, 'LicensePlate': ''}
    return [car, *[{'_id': i, 'VehicleId': 1, 'Description': 'Road tax', 'Cost': amount,
                   'IsRecurring': False, 'RecurringInterval': 'OneMonth', 'Date': datetime(2026, 1, 1)} for i in (10, 11)]]


def test_lubelog_repeat_equal_costs_changed_source_and_other_namespace(app, user):
    records = lube_records()
    run = lambda docs, **kwargs: import_lubelog_to_gearcargo(user, _lubelog_zip(docs), distance_unit='km', **kwargs)
    assert run(records, source_label='Source A')['imported']['tax_entries'] == 2
    assert run(records, source_label='Source A')['imported']['new_records'] == 0
    with pytest.raises(ImportConflict):
        run(lube_records(60.0), source_label='Source A')
    db.session.rollback()
    assert sum(row.amount for row in TaxEntry.query.all()) == 100
    assert run(records, source_label='Source B')['imported']['tax_entries'] == 2
    assert Vehicle.query.count() == 2 and TaxEntry.query.count() == 4


def test_database_source_unique_constraint(app, user):
    car = vehicle(user)
    import_entries_csv(user, 'service', csv_rows(car, [('1', 50)], ids=True))
    row = ImportIdentity.query.one()
    db.session.add(ImportIdentity(**{column.name: getattr(row, column.name)
        for column in ImportIdentity.__table__.columns if column.name != 'id'}))
    with pytest.raises(IntegrityError):
        db.session.flush()
    db.session.rollback()
    assert ServiceEntry.query.count() == ImportIdentity.query.count() == 1


def test_concurrent_csv_replay_creates_once(app, user):
    if db.engine.dialect.name != 'postgresql':
        pytest.skip('PostgreSQL advisory-lock concurrency check')
    car = vehicle(user)
    text = csv_rows(car, [('1', 50), ('2', 50)], ids=True)
    user_id = user.id
    db.session.rollback()
    barrier = Barrier(2)
    def run():
        with app.app_context():
            owner = db.session.get(User, user_id)
            barrier.wait(timeout=10)
            return import_entries_csv(owner, 'service', text)['created']
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run) for _ in range(2)]
        assert sorted(f.result(timeout=30) for f in futures) == [0, 2]
    assert ServiceEntry.query.count() == ImportIdentity.query.count() == 2


def test_migration_keeps_legacy_rows_and_refuses_to_drop_provenance(app, user):
    import importlib.util
    from alembic.operations import Operations
    from alembic.migration import MigrationContext
    from sqlalchemy import text
    source_graph(user)
    owner_id = user.id
    source = Path(__file__).parents[1] / 'migrations/versions/gc016_import_provenance.py'
    spec = importlib.util.spec_from_file_location('gc016_test_migration', source)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    db.session.remove()
    with db.engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.downgrade()
        assert connection.execute(text('SELECT count(*) FROM entries')).scalar_one() == 3
        migration.upgrade()
        assert len(connection.execute(text('SELECT export_namespace FROM users')).scalar_one()) == 36
        assert connection.execute(text('SELECT count(*) FROM entries')).scalar_one() == 3
        assert connection.execute(text('SELECT count(*) FROM import_identities')).scalar_one() == 0
    owner = db.session.get(User, owner_id)
    car = Vehicle.query.filter_by(user_id=owner.id).first()
    import_entries_csv(owner, 'service', csv_rows(car, [('one', 50)], ids=True))
    db.session.remove()
    with db.engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        with pytest.raises(RuntimeError, match='Preserve import provenance'):
            migration.downgrade()


def test_account_deletion_removes_source_payloads(app, user):
    from app.services.deletion import delete_owned_data
    car = vehicle(user)
    owner_id = user.id
    import_entries_csv(user, 'service', csv_rows(car, [('one', 50)], ids=True))
    delete_owned_data(owner_id)
    assert ImportIdentity.query.filter_by(user_id=owner_id).count() == 0
    assert ImportBatch.query.filter_by(user_id=owner_id).count() == 0


def test_csv_cleared_field_is_a_changed_source(app, user):
    car = vehicle(user)
    text = csv_rows(car, [('one', 50)], ids=True).replace('title\n', 'title,notes\n').replace('Service\n', 'Service,Original\n')
    import_entries_csv(user, 'service', text, source_label='Garage')
    with pytest.raises(ImportConflict):
        import_entries_csv(user, 'service', text.replace('Original', ''), source_label='Garage')
    db.session.rollback()
    assert ServiceEntry.query.one().notes == 'Original'


def test_lubelog_incremental_file_keeps_other_vehicle_references(app, user):
    records = lube_records() + [{**VEHICLE_ONE, '_id': 2, 'LicensePlate': ''},
                              {**lube_records()[-1], '_id': 21, 'VehicleId': 2}]
    run = lambda docs: import_lubelog_to_gearcargo(user, _lubelog_zip(docs), distance_unit='km', source_label='Garage')
    assert run(records)['imported']['tax_entries'] == 3
    updated = records + [{**records[1], '_id': 12}]
    result = run(updated)['imported']
    assert result['conflicts'] == 0 and result['new_records'] == 1
    assert TaxEntry.query.count() == 4 and Vehicle.query.count() == 2


def test_changed_receipt_bytes_require_review_and_keep_retains_original(app, user, tmp_path, monkeypatch):
    archive, _ = zip_graph(user, tmp_path, monkeypatch)
    target = other_user()
    assert restore_zip(app, target, archive)[1] == 200
    (tmp_path / 'receipt.jpg').write_bytes(b'changed source bytes')
    updated, _ = backup.create_backup_zip(user)
    response, status = restore_zip(app, target, updated.getvalue())
    assert status == 409 and response.json['preview']['conflicts'] == 2
    assert all(Path(row.filepath).read_bytes() == b'shared receipt bytes' for row in Attachment.query.filter_by(user_id=target.id))


def test_external_preview_does_not_save_or_replace_archive(app, user, client, auth_headers, tmp_path, monkeypatch):
    from types import SimpleNamespace
    archive, _ = zip_graph(user, tmp_path, monkeypatch)
    monkeypatch.setattr(backup, '_is_allowed_webdav_url', lambda *a: True)
    monkeypatch.setattr(backup, '_resolve_webdav_auth', lambda *a: (('fixture', 'fixture'), None))
    monkeypatch.setattr(backup, '_safe_webdav_request', lambda *a, **k: SimpleNamespace(status_code=200, content=archive))
    folder = Path(backup.get_backup_folder()) / str(user.id)
    folder.mkdir(parents=True, exist_ok=True)
    stored = folder / 'preview.zip'
    stored.write_bytes(b'previous stored archive')
    response = client.post('/api/backup/external/restore', headers=auth_headers(user.id), json={
        'filename': stored.name, 'url': 'https://fixture.invalid', 'preview': True})
    assert response.status_code == 200 and 'preview' in response.json
    assert stored.read_bytes() == b'previous stored archive'
    assert ImportBatch.query.count() == ImportIdentity.query.count() == 0

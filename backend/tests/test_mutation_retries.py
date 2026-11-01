"""GC-008: durable retry outcomes and stale-write rejection at the HTTP boundary."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier
from uuid import uuid4
from io import BytesIO
from pathlib import Path
import json

import pytest
from sqlalchemy import select

from app import db
from app.models import Vehicle, FuelEntry, Reminder, Todo, User
from app.models.mutation import MutationOperation


def operation(auth, revision=None, key=None):
    headers = {**auth, 'Idempotency-Key': key or str(uuid4()), 'X-GearCargo-Mutation-Version': '1'}
    if revision is not None:
        headers['If-Match'] = f'"{revision}"'
    return headers


def car(user):
    row = Vehicle(user_id=user.id, name='Retry car')
    db.session.add(row)
    db.session.commit()
    return row


def fuel(client, auth, vehicle):
    response = client.post('/api/fuel', headers=operation(auth), json={
        'vehicle_id': vehicle.id, 'liters': 10, 'total_price': 20, 'date': '2026-10-28'})
    assert response.status_code == 201, response.json
    return response.json['entry']


def test_committed_response_loss_replays_exact_outcome(client, user, auth_headers):
    auth = auth_headers(user.id)
    headers = operation(auth)
    payload = {'vehicle_id': car(user).id, 'liters': 10, 'total_price': 20}
    first = client.post('/api/fuel', headers=headers, json=payload)
    # Discard the response, then reconnect with the original request identity.
    retry = client.post('/api/fuel', headers=headers, json=payload)
    assert first.status_code == retry.status_code == 201
    assert first.data == retry.data
    assert retry.headers['Idempotent-Replay'] == 'true'
    assert FuelEntry.query.count() == MutationOperation.query.count() == 1
    changed = client.post('/api/fuel', headers=headers, json={**payload, 'liters': 11})
    assert changed.status_code == 409 and changed.json['code'] == 'OPERATION_KEY_REUSED'
    assert FuelEntry.query.count() == 1


def test_two_editor_snapshots_conflict_and_delete_retry(client, user, auth_headers):
    auth = auth_headers(user.id)
    entry = fuel(client, auth, car(user))
    url = f'/api/fuel/{entry["id"]}'
    first = client.put(url, headers=operation(auth, entry['revision']), json={'liters': 12})
    assert first.status_code == 200, first.json
    newer = first.json['entry']
    assert newer['revision'] == entry['revision'] + 1  # joined-table-only edit
    stale = client.put(url, headers=operation(auth, entry['revision']), json={'notes': 'stale'})
    assert stale.status_code == 409 and stale.json['code'] == 'REVISION_CONFLICT'
    assert stale.json['current']['liters'] == 12
    assert stale.json['current_revision'] == newer['revision']
    delete_headers = operation(auth, newer['revision'])
    deleted = client.delete(url, headers=delete_headers)
    retry = client.delete(url, headers=delete_headers)
    assert deleted.status_code == retry.status_code == 200
    assert deleted.data == retry.data
    assert client.put(url, headers=operation(auth, newer['revision']), json={'notes': 'resurrect'}).status_code == 409
    assert FuelEntry.query.count() == 0


@pytest.mark.parametrize('kind,model', [('reminders', Reminder), ('todos', Todo)])
def test_completion_is_a_single_transition_even_for_legacy_clients(client, user, auth_headers, kind, model):
    row = model(user_id=user.id, title='Monthly', due_date=date(2026, 10, 28),
                recurring=True, frequency='monthly', frequency_value=1)
    db.session.add(row); db.session.commit()
    auth = auth_headers(user.id)
    first = client.post(f'/api/{kind}/{row.id}/complete', headers=auth)
    assert first.status_code == 200, first.json
    completed_at = row.completed_at
    retry = client.post(f'/api/{kind}/{row.id}/complete', headers=auth)
    assert retry.status_code == 200
    assert model.query.filter_by(completed_from_id=row.id).count() == 1
    assert row.completed_at == completed_at


def test_rollback_does_not_leave_receipt_or_record(client, user, auth_headers, monkeypatch):
    auth = auth_headers(user.id)
    headers = operation(auth)
    original = db.session.commit
    def fail_commit():
        raise RuntimeError('Injected failure before durable commit')
    monkeypatch.setattr(db.session, 'commit', fail_commit)
    with pytest.raises(RuntimeError, match='Injected failure'):
        client.post('/api/vehicles', headers=headers, json={'name': 'Atomic'})
    assert Vehicle.query.count() == MutationOperation.query.count() == 0
    monkeypatch.setattr(db.session, 'commit', original)
    assert client.post('/api/vehicles', headers=headers, json={'name': 'Atomic'}).status_code == 201


def test_keys_are_owner_scoped_and_conflicts_do_not_leak_foreign_rows(client, user, auth_headers):
    auth = auth_headers(user.id)
    key = str(uuid4())
    first = client.post('/api/vehicles', headers=operation(auth, key=key), json={'name': 'A'})
    other = User(username='retry_other', email='retry-other@example.invalid', is_active=True)
    other.set_password('StrongPass123!')
    db.session.add(other); db.session.commit()
    other_auth = auth_headers(other.id, jti='other-session')
    assert client.post('/api/vehicles', headers=operation(other_auth, key=key), json={'name': 'B'}).status_code == 201
    vehicle = first.json['vehicle']
    conflict = client.put(f'/api/vehicles/{vehicle["id"]}', headers=operation(other_auth, vehicle['revision']), json={'name': 'Foreign'})
    assert conflict.status_code == 409 and conflict.json['current'] is None
    assert MutationOperation.query.count() == 2


@pytest.mark.parametrize('headers,status,code', [
    ({'X-GearCargo-Mutation-Version': '1'}, 400, 'OPERATION_ID_REQUIRED'),
    ({'Idempotency-Key': 'short'}, 400, 'INVALID_OPERATION_ID'),
    ({'If-Match': '*'}, 400, 'INVALID_REVISION'),
    ({'X-GearCargo-Mutation-Version': '2'}, 400, 'MUTATION_PROTOCOL'),
])
def test_invalid_protocol_is_rejected_before_write(client, user, auth_headers, headers, status, code):
    response = client.post('/api/vehicles', headers={**auth_headers(user.id), **headers}, json={'name': 'Invalid'})
    assert response.status_code == status and response.json['code'] == code
    assert Vehicle.query.count() == MutationOperation.query.count() == 0


def test_new_protocol_requires_revision_but_legacy_online_still_works(client, user, auth_headers):
    auth = auth_headers(user.id)
    vehicle = car(user)
    url = f'/api/vehicles/{vehicle.id}'
    assert client.put(url, headers=operation(auth), json={'name': 'Missing'}).status_code == 428
    assert client.put(url, headers=auth, json={'name': 'Legacy'}).status_code == 200


def test_older_worker_cannot_strip_retry_protocol_from_identity_bound_write(client, user, auth_headers):
    auth = auth_headers(user.id)
    identity = client.get('/api/auth/offline-identity', headers=auth).json
    headers = {**auth, 'X-GearCargo-Offline-Owner': identity['owner_key'],
               'X-GearCargo-Offline-Generation': identity['generation']}
    response = client.post('/api/vehicles', headers=headers, json={'name': 'Unsafe old worker'})
    assert response.status_code == 428 and response.json['code'] == 'MUTATION_PROTOCOL_REQUIRED'
    assert Vehicle.query.count() == 0


@pytest.mark.parametrize('scenario', ['same_key', 'different_payload', 'stale_edit', 'completion'])
def test_concurrent_requests_on_postgres(app, user, auth_headers, scenario):
    if db.engine.dialect.name != 'postgresql':
        pytest.skip('Row-lock concurrency is verified on the production PostgreSQL engine')
    auth = auth_headers(user.id)
    vehicle = car(user)
    key = str(uuid4())
    url, payload, method, revision = '/api/fuel', {'vehicle_id': vehicle.id, 'liters': 10, 'total_price': 20}, 'post', None
    if scenario == 'stale_edit':
        entry = fuel(app.test_client(), auth, vehicle)
        url, payload, method, revision = f'/api/fuel/{entry["id"]}', {'notes': 'first'}, 'put', entry['revision']
    elif scenario == 'completion':
        reminder = Reminder(user_id=user.id, title='Concurrent', due_date=date(2026, 10, 28), recurring=True, frequency='monthly', frequency_value=1)
        db.session.add(reminder); db.session.commit()
        url, payload = f'/api/reminders/{reminder.id}/complete', {}
    barrier = Barrier(2)
    def perform(index):
        local_payload = dict(payload)
        if index and scenario == 'different_payload': local_payload['liters'] = 11
        if index and scenario == 'stale_edit': local_payload['notes'] = 'second'
        headers = operation(auth, revision, key if scenario in ('same_key', 'different_payload') else str(uuid4()))
        if scenario == 'completion': headers = auth  # legacy race still guarded
        barrier.wait(timeout=10)
        response = getattr(app.test_client(), method)(url, headers=headers, json=local_payload)
        return response.status_code, response.data
    db.session.remove()
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(perform, [0, 1]))
    statuses = sorted(status for status, _ in outcomes)
    assert statuses == ({'same_key': [201, 201], 'different_payload': [201, 409], 'stale_edit': [200, 409], 'completion': [200, 200]}[scenario]), outcomes
    if scenario == 'same_key': assert outcomes[0][1] == outcomes[1][1]
    if scenario == 'completion': assert db.session.scalar(select(db.func.count()).select_from(Reminder).where(Reminder.completed_from_id.is_not(None))) == 1
    else: assert FuelEntry.query.count() == 1


@pytest.mark.parametrize('resource,payload,result_key', [
    ('vehicles', {'name': 'New'}, 'vehicle'),
    ('services', {'service_type': 'oil_change'}, 'entry'),
    ('repairs', {'repair_type': 'brakes'}, 'entry'),
    ('taxes', {'tax_type': 'road_tax'}, 'entry'),
    ('parking', {'parking_type': 'hourly'}, 'entry'),
    ('consumables', {'consumable_type': 'tire'}, 'entry'),
    ('insurance', {'provider': 'Test', 'start_date': '2026-01-01', 'end_date': '2027-01-01'}, 'policy'),
    ('reminders', {'title': 'Test', 'due_date': '2027-01-01'}, 'reminder'),
    ('todos', {'title': 'Test'}, 'todo'),
])
def test_every_record_surface_replays_creates_and_rejects_stale_edits(client, user, auth_headers, resource, payload, result_key):
    auth = auth_headers(user.id)
    payload = {**payload, 'vehicle_id': car(user).id}
    headers = operation(auth)
    first = client.post(f'/api/{resource}', headers=headers, json=payload)
    assert first.status_code == 201, first.json
    retry = client.post(f'/api/{resource}', headers=headers, json=payload)
    assert retry.data == first.data and retry.status_code == first.status_code
    row = first.json[result_key]
    changed = client.put(f'/api/{resource}/{row["id"]}', headers=operation(auth, row['revision']), json={
        'name': 'Changed', 'title': 'Changed', 'notes': 'Changed', 'description': 'Changed'})
    assert changed.status_code == 200, changed.json
    stale = client.delete(f'/api/{resource}/{row["id"]}', headers=operation(auth, row['revision']))
    assert stale.status_code == 409, stale.json


def test_attachment_retry_and_commit_failure_do_not_duplicate_files_or_tasks(app, client, user, auth_headers, monkeypatch):
    from PIL import Image
    from app.models import Attachment
    from app.services import ocr_queue
    image = BytesIO(); Image.new('RGB', (5, 5)).save(image, format='PNG')
    calls = []
    original_enqueue = ocr_queue.enqueue_attachment
    def enqueue(attachment, **kwargs):
        calls.append(attachment.id)
        return original_enqueue(attachment, **kwargs)
    monkeypatch.setattr(ocr_queue, 'enqueue_attachment', enqueue)
    auth = auth_headers(user.id)
    headers = operation(auth)
    def upload(h):
        return client.post('/api/attachments', headers=h, data={'file': (BytesIO(image.getvalue()), 'receipt.png')})
    first = upload(headers); retry = upload(headers)
    assert first.status_code == retry.status_code == 201, first.json
    assert first.data == retry.data and Attachment.query.count() == 1 and len(calls) == 1
    files = list(Path(app.config['UPLOAD_FOLDER']).rglob('*'))
    original = db.session.commit
    monkeypatch.setattr(db.session, 'commit', lambda: (_ for _ in ()).throw(RuntimeError('commit fault')))
    with pytest.raises(RuntimeError, match='commit fault'): upload(operation(auth))
    monkeypatch.setattr(db.session, 'commit', original)
    assert list(Path(app.config['UPLOAD_FOLDER']).rglob('*')) == files
    assert Attachment.query.count() == 1
    assert Attachment.query.filter_by(ocr_state='queued').count() == 1
    row = Attachment.query.one()
    path = Path(row.filepath)
    delete_headers = operation(auth, row.revision)
    deleted = client.delete(f'/api/attachments/{row.id}', headers=delete_headers)
    assert deleted.status_code == 200 and not path.exists()
    assert client.delete(f'/api/attachments/{row.id}', headers=delete_headers).data == deleted.data


def test_restore_preserves_completion_links_but_not_receipts_or_revisions(app, client, user, auth_headers):
    from app.routes.backup import gather_user_data
    auth = auth_headers(user.id)
    headers = operation(auth)
    first = client.post('/api/vehicles', headers=headers, json={'name': 'Portable', 'license_plate': 'PORTABLE'})
    vehicle = first.json['vehicle']
    reminder = Reminder(user_id=user.id, vehicle_id=vehicle['id'], title='Chain', due_date=date(2026, 10, 28), recurring=True, frequency='monthly')
    db.session.add(reminder); db.session.commit()
    client.post(f'/api/reminders/{reminder.id}/complete', headers=auth)
    payload = gather_user_data(user, False)
    assert 'revision' not in payload['vehicles'][0] and 'mutation_operations' not in payload
    target = User(username='restore_retry', email='restore-retry@example.invalid', is_active=True)
    target.set_password('StrongPass123!'); db.session.add(target); db.session.commit()
    target_auth = auth_headers(target.id, jti='restore-session')
    def restore(data, headers, mode='merge', **options):
        return client.post('/api/backup/import', headers=headers, data={'file': (BytesIO(json.dumps(data).encode()), 'backup.json'), 'merge_mode': mode, **options})
    result = restore(payload, target_auth)
    assert result.status_code == 200, result.json
    restored = Vehicle.query.filter_by(user_id=target.id).one()
    assert restored.revision != vehicle['revision']
    successor = Reminder.query.filter(Reminder.user_id == target.id, Reminder.completed_from_id.is_not(None)).one()
    assert db.session.get(Reminder, successor.completed_from_id).user_id == target.id
    assert MutationOperation.query.filter_by(user_id=target.id).count() == 0
    # GC-016: changed source fields require review, including legacy replace.
    # Keeping existing values does not invalidate forms or overwrite local data.
    payload['vehicles'][0]['name'] = 'Restored name'
    prior_revision = db.session.get(Vehicle, vehicle['id']).revision
    rejected = restore(payload, auth, 'replace')
    assert rejected.status_code == 409 and rejected.json['code'] == 'IMPORT_REVIEW_REQUIRED'
    assert restore(payload, auth, 'replace', conflict_policy='keep_existing').status_code == 200
    db.session.expire_all()
    assert db.session.get(Vehicle, vehicle['id']).name == 'Portable'
    assert db.session.get(Vehicle, vehicle['id']).revision == prior_revision
    assert client.post('/api/vehicles', headers=headers, json={'name': 'Portable', 'license_plate': 'PORTABLE'}).data == first.data
    assert MutationOperation.query.filter_by(user_id=user.id).count() == 1
    # Pre-protocol v4 archives remain readable with unknown origin links.
    payload['version'] = '4.0'
    payload.pop('source_namespace')
    payload.pop('source_metadata')
    for kind in ('reminders', 'todos'):
        for row in payload[kind]: row.pop('completed_from_id', None)
    from app.services.backup_schema import prepare_backup
    assert all(row['completed_from_id'] is None for row in prepare_backup(payload).records['reminders'])


def test_restore_rejects_duplicate_successor_origins_before_writes(user):
    from app.routes.backup import gather_user_data
    from app.services.backup_schema import prepare_backup, BackupSchemaError
    rows = [Reminder(user_id=user.id, title=str(n), due_date=date(2027, 1, 1)) for n in range(3)]
    db.session.add_all(rows); db.session.commit()
    payload = gather_user_data(user, False)
    payload['reminders'][1]['completed_from_id'] = rows[0].id
    payload['reminders'][2]['completed_from_id'] = rows[0].id
    with pytest.raises(BackupSchemaError, match='Multiple successors'):
        prepare_backup(payload)


def test_import_cannot_add_a_second_successor_to_an_existing_completion(client, user, auth_headers):
    from app.routes.backup import gather_user_data
    parent = Reminder(user_id=user.id, title='Existing parent', due_date=date(2027, 1, 1), completed=True)
    db.session.add(parent); db.session.flush()
    child = Reminder(user_id=user.id, title='Existing successor', due_date=date(2027, 2, 1), completed_from_id=parent.id)
    db.session.add(child); db.session.commit()
    payload = gather_user_data(user, False)
    incoming = next(row for row in payload['reminders'] if row['id'] == child.id)
    # A genuinely new source successor must still fail the recurrence constraint.
    # An edit to the existing ID is now a source conflict instead (GC-016).
    incoming['id'] = child.id + 100
    incoming['title'] = 'Another archive successor'
    response = client.post('/api/backup/import', headers=auth_headers(user.id), data={
        'file': (BytesIO(json.dumps(payload).encode()), 'backup.json')})
    assert response.status_code == 400, response.json
    assert Reminder.query.count() == 2
    assert Reminder.query.filter_by(completed_from_id=parent.id).one().title == 'Existing successor'
    assert response.json['issues'][0]['path'].endswith('.completed_from_id')


def test_previous_v4_zip_still_requires_a_valid_matching_manifest(app, user):
    import zipfile
    from app.routes.backup import gather_user_data, restore_from_zip, calculate_checksum
    payload = gather_user_data(user, False)
    payload['version'] = '4.0'
    payload.pop('source_namespace')
    payload.pop('source_metadata')
    raw = json.dumps(payload).encode()
    def archive(manifest):
        output = BytesIO()
        with zipfile.ZipFile(output, 'w') as zf:
            zf.writestr('backup_data.json', raw)
            if manifest is not None: zf.writestr('manifest.json', json.dumps(manifest))
        output.seek(0)
        return output
    good = {'version': '4.0', 'checksum': calculate_checksum(raw)}
    for manifest in (None, {**good, 'checksum': 'wrong'}, {**good, 'version': '4.1'}):
        with app.test_request_context(): response, status = restore_from_zip(user, archive(manifest))
        assert status == 400 and response.json['issues'][0]['path'].startswith('manifest')
    with app.test_request_context(): response = restore_from_zip(user, archive(good))
    assert response.status_code == 200, response.json


def test_migration_preserves_historical_duplicates_and_refuses_receipt_loss(app, user):
    import importlib.util
    from alembic.operations import Operations
    from alembic.migration import MigrationContext
    from sqlalchemy import text
    source = Path(__file__).parents[1] / 'migrations/versions/gc008_mutation_identity.py'
    spec = importlib.util.spec_from_file_location('gc008_migration_test', source)
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    user_id = user.id
    db.session.remove()
    with db.engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.downgrade()  # empty ledger: reproduce the pre-GC008 schema
        for _ in range(3):
            connection.execute(text("INSERT INTO reminders (user_id, title, due_date) VALUES (:owner, 'Historical duplicate', '2027-01-01')"), {'owner': user_id})
        migration.upgrade()
        rows = connection.execute(text('SELECT revision, completed_from_id FROM reminders')).all()
        assert rows == [(1, None)] * 3
        connection.execute(text("INSERT INTO mutation_operations (user_id, operation_key, fingerprint, status, body, created_at) VALUES (:owner, 'historical-operation-key', :hash, 201, '{}', CURRENT_TIMESTAMP)"), {'owner': user_id, 'hash': 'a' * 64})
        with pytest.raises(RuntimeError, match='preserve mutation receipts'):
            migration.downgrade()
        assert connection.execute(text('SELECT count(*) FROM reminders')).scalar_one() == 3
        assert connection.execute(text('SELECT count(*) FROM mutation_operations')).scalar_one() == 1

"""GC-017: protect the complete attachment/parent/vehicle relationship."""
import json
from datetime import date
from io import BytesIO
from pathlib import Path
from threading import Barrier
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import update

from app import db
from app.models import User, Vehicle, ServiceEntry, Attachment, InsurancePolicy, ImportIdentity
from app.services.attachment_consistency import AttachmentParentError, scan_relationships, create_consistency_app
from app.services.backup_schema import export_user_data, prepare_backup, BackupSchemaError
from tests.test_receipt_draft_links import upload, PDF
from tests.test_mutation_retries import operation


@pytest.fixture(autouse=True)
def no_background(monkeypatch):
    monkeypatch.setattr('app.services.task_queue.enqueue_task', lambda *a, **kw: None)


def car(user, name='Car'):
    row = Vehicle(user_id=user.id, name=name)
    db.session.add(row); db.session.commit()
    return row


def expense(user, vehicle):
    row = ServiceEntry(user_id=user.id, vehicle_id=vehicle.id, title='Service', amount=25, date=date(2026, 1, 1))
    db.session.add(row); db.session.commit()
    return row


def policy(user, vehicle):
    row = InsurancePolicy(user_id=user.id, vehicle_id=vehicle.id, provider='Test', premium=25,
                          start_date=date(2026, 1, 1), end_date=date(2027, 1, 1))
    db.session.add(row); db.session.commit()
    return row


def other_user():
    row = User(username='other', email='other@example.invalid')
    row.set_password('FixturePassword123!'); db.session.add(row); db.session.commit()
    return row


def corrupt_attachment(attachment_id, **values):
    # Explicit maintenance SQL models historical data written before GC-017.
    db.session.remove()
    with db.engine.begin() as connection:
        connection.execute(update(Attachment.__table__).where(Attachment.id == attachment_id).values(**values))


def test_explicit_relink_moves_vehicle_and_expense_atomically(app, user, client, auth_headers):
    auth = auth_headers(user.id)
    a, b = car(user), car(user)
    first, second = expense(user, a), expense(user, b)
    receipt = upload(client, auth, a.id, first.id).json['attachment']
    response = client.put(f'/api/attachments/{receipt["id"]}', headers=operation(auth, receipt['revision']),
                          json={'vehicle_id': b.id, 'entry_id': second.id, 'description': 'Reviewed move'})
    assert response.status_code == 200, response.json
    row = db.session.get(Attachment, receipt['id'])
    assert (row.vehicle_id, row.entry_id, row.description) == (b.id, second.id, 'Reviewed move')
    assert client.get(f'/api/attachments/{row.id}/download', headers=auth).data == PDF
    payload = export_user_data(user)
    assert payload['attachments'][0]['vehicle_id'] == b.id
    assert payload['attachments'][0]['entry_id'] == second.id
    assert client.delete(f'/api/vehicles/{a.id}?hard=true', headers=auth).status_code == 200
    assert client.get(f'/api/attachments/{row.id}/download', headers=auth).data == PDF


@pytest.mark.parametrize('changes', [{'vehicle': 'other'}, {'entry': 'other'}, {'entry': 'wrong'}, {'vehicle': 'wrong'}])
def test_rejected_move_preserves_all_metadata_and_file(user, client, auth_headers, changes):
    auth = auth_headers(user.id)
    a, b = car(user), car(user)
    entry, wrong_entry = expense(user, a), expense(user, b)
    outsider = other_user(); foreign_car = car(outsider); foreign_entry = expense(outsider, foreign_car)
    receipt = upload(client, auth, a.id, entry.id).json['attachment']
    data = {'description': 'must not persist'}
    if 'vehicle' in changes: data['vehicle_id'] = foreign_car.id if changes['vehicle'] == 'other' else b.id
    if 'entry' in changes: data['entry_id'] = foreign_entry.id if changes['entry'] == 'other' else wrong_entry.id
    response = client.put(f'/api/attachments/{receipt["id"]}', headers=operation(auth, receipt['revision']), json=data)
    assert response.status_code in (400, 404, 409), response.json
    db.session.expire_all()
    stored = db.session.get(Attachment, receipt['id'])
    assert (stored.vehicle_id, stored.entry_id, stored.description) == (a.id, entry.id, None)
    assert client.get(f'/api/attachments/{stored.id}/download', headers=auth).data == PDF


@pytest.mark.parametrize('field', ['entry_id', 'vehicle_id'])
def test_upload_rejects_invalid_supplied_ids_before_file_creation(app, user, client, auth_headers, field):
    response = client.post('/api/attachments', headers=auth_headers(user.id), data={
        'file': (BytesIO(PDF), 'receipt.pdf'), field: 'not-an-id'})
    assert response.status_code == 400
    assert Attachment.query.count() == 0
    assert not list(Path(app.config['UPLOAD_FOLDER']).rglob('*.pdf'))


def test_orm_guards_receipt_policy_and_parent_move(user):
    a, b = car(user), car(user)
    entry = expense(user, a)
    receipt = Attachment(user_id=user.id, vehicle_id=b.id, entry_id=entry.id, filename='x', filepath='x')
    db.session.add(receipt)
    with pytest.raises(AttachmentParentError): db.session.flush()
    db.session.rollback()
    receipt = Attachment(user_id=user.id, vehicle_id=a.id, entry_id=entry.id, filename='x', filepath='x')
    db.session.add(receipt); db.session.commit()
    receipt_id, entry_id, b_id = receipt.id, entry.id, b.id
    entry.vehicle_id = b.id
    with pytest.raises(AttachmentParentError): db.session.commit()
    db.session.rollback()
    assert db.session.get(ServiceEntry, entry_id).vehicle_id == a.id
    p = policy(user, b)
    p.document_attachment_id = receipt_id
    with pytest.raises(AttachmentParentError): db.session.commit()
    db.session.rollback()
    # Moving both sides in one flush is valid and cannot expose a half-move.
    with db.session.no_autoflush:
        db.session.get(ServiceEntry, entry_id).vehicle_id = b_id
        db.session.get(Attachment, receipt_id).vehicle_id = b_id
    db.session.commit()
    assert scan_relationships(db.session.connection())['issue_count'] == 0


def test_policy_document_blocks_vehicle_move_and_supports_explicit_detach(user, client, auth_headers):
    auth = auth_headers(user.id)
    a, b = car(user), car(user)
    p = policy(user, a)
    receipt = upload(client, auth, a.id, p.id, 'insurance_document').json['attachment']
    path = f'/api/attachments/{receipt["id"]}'
    denied = client.put(path, headers=operation(auth, receipt['revision']), json={'vehicle_id': b.id, 'description': 'bad'})
    assert denied.status_code == 409
    assert p.document_attachment_id == receipt['id']
    moved = client.put(path, headers=operation(auth, receipt['revision']), json={'vehicle_id': b.id, 'insurance_id': None})
    assert moved.status_code == 200, moved.json
    assert p.document_attachment_id is None
    assert db.session.get(Attachment, receipt['id']).vehicle_id == b.id


def archive_with_receipt(user):
    a, b = car(user), car(user)
    entry = expense(user, b)
    receipt = Attachment(user_id=user.id, vehicle_id=b.id, entry_id=entry.id, filename='x.pdf', filepath='missing')
    db.session.add(receipt); db.session.commit()
    return export_user_data(user), a.id, b.id


def test_backup_preflight_rejects_cross_vehicle_parent_before_any_rows(user, client, auth_headers):
    payload, wrong_vehicle, _ = archive_with_receipt(user)
    payload['attachments'][0]['vehicle_id'] = wrong_vehicle
    target = other_user()
    response = client.post('/api/backup/import', headers=auth_headers(target.id), data={
        'file': (BytesIO(json.dumps(payload).encode()), 'backup.json')})
    assert response.status_code == 400, response.json
    assert response.json['issues'][0]['path'].startswith('attachments')
    assert Attachment.query.filter_by(user_id=target.id).count() == 0
    assert Vehicle.query.filter_by(user_id=target.id).count() == 0
    assert ImportIdentity.query.filter_by(user_id=target.id).count() == 0


def test_archive_derives_absent_vehicle_and_rejects_conflicting_policy(user):
    payload, wrong_vehicle, correct_vehicle = archive_with_receipt(user)
    payload['attachments'][0]['vehicle_id'] = None
    assert prepare_backup(payload).records['attachments'][0]['vehicle_id'] == correct_vehicle
    p = policy(user, db.session.get(Vehicle, wrong_vehicle))
    payload['insurance_policies'] = export_user_data(user)['insurance_policies']
    payload['insurance_policies'][0]['document_attachment_id'] = payload['attachments'][0]['id']
    with pytest.raises(BackupSchemaError, match='conflicts'):
        prepare_backup(payload)
    assert p.document_attachment_id is None


def test_historical_scan_is_read_only_and_explicit_repair_preserves_file(app, user, client, auth_headers):
    uid = user.id; auth = auth_headers(uid)
    a, b = car(user), car(user)
    aid, bid = a.id, b.id
    entry = expense(user, b); eid = entry.id
    receipt = upload(client, auth, a.id).json['attachment']
    corrupt_attachment(receipt['id'], entry_id=eid)
    with db.engine.connect() as connection:
        report = scan_relationships(connection)
    assert report['read_only'] and report['issue_count'] == 1
    assert report['issues'][0]['code'] == 'entry_vehicle_mismatch'
    assert db.session.get(Attachment, receipt['id']).vehicle_id == aid
    with pytest.raises(BackupSchemaError):
        export_user_data(db.session.get(User, uid))
    # Wrong vehicle deletion refuses to lose a receipt needed by the other car.
    assert client.delete(f'/api/vehicles/{aid}?hard=true', headers=auth).status_code == 409
    result = client.put(f'/api/attachments/{receipt["id"]}', headers=operation(auth, receipt['revision']), json={'vehicle_id': bid})
    assert result.status_code == 200, result.json
    assert client.get(f'/api/attachments/{receipt["id"]}/download', headers=auth).data == PDF
    assert scan_relationships(db.session.connection())['issue_count'] == 0
    cli_app = create_consistency_app(app.config['SQLALCHEMY_DATABASE_URI'])
    result = cli_app.test_cli_runner().invoke(args=['check-attachment-links'])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)['issue_count'] == 0


def test_foreign_policy_reference_is_reported_and_not_repaired_implicitly(user):
    a = car(user)
    receipt = Attachment(user_id=user.id, vehicle_id=a.id, filename='x', filepath='x')
    db.session.add(receipt); db.session.commit()
    outsider = other_user(); b = car(outsider); p = policy(outsider, b)
    rid, pid = receipt.id, p.id
    db.session.remove()
    with db.engine.begin() as connection:
        connection.execute(update(InsurancePolicy.__table__).where(InsurancePolicy.id == pid).values(document_attachment_id=rid))
        report = scan_relationships(connection)
    assert any(issue['code'] == 'policy_owner_mismatch' for issue in report['issues'])
    assert db.session.get(InsurancePolicy, pid).document_attachment_id == rid


def test_concurrent_parent_move_and_link_cannot_commit_mismatch(app, user):
    if db.engine.dialect.name != 'postgresql': pytest.skip('PostgreSQL transaction-lock concurrency test')
    a, b = car(user), car(user); entry = expense(user, a)
    aid, bid, eid, uid = a.id, b.id, entry.id, user.id
    db.session.rollback()
    barrier = Barrier(2)
    def run(link):
        with app.app_context():
            if link:
                db.session.add(Attachment(user_id=uid, vehicle_id=aid, entry_id=eid, filename='x', filepath='x'))
            else:
                db.session.get(ServiceEntry, eid).vehicle_id = bid
            barrier.wait(timeout=10)
            try:
                db.session.commit()
                return 'committed'
            except AttachmentParentError:
                db.session.rollback()
                return 'rejected'
    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks = [pool.submit(run, link) for link in (True, False)]
        assert sorted(task.result(timeout=30) for task in tasks) == ['committed', 'rejected']
    assert scan_relationships(db.session.connection())['issue_count'] == 0


@pytest.mark.parametrize('parameter_mapping', [False, True])
def test_bulk_relationship_update_cannot_bypass_model_guard(user, parameter_mapping):
    a, b = car(user), car(user)
    entry = expense(user, a)
    receipt = Attachment(user_id=user.id, vehicle_id=a.id, entry_id=entry.id, filename='x', filepath='x')
    db.session.add(receipt); db.session.commit()
    with pytest.raises(AttachmentParentError):
        if parameter_mapping:
            db.session.execute(update(Attachment), [{'id': receipt.id, 'vehicle_id': b.id}])
        else:
            db.session.execute(update(Attachment).where(Attachment.id == receipt.id).values(vehicle_id=b.id))
    db.session.rollback()
    assert db.session.get(Attachment, receipt.id).vehicle_id == a.id


def test_restore_rechecks_destination_after_provenance_mapping(app, user, client, auth_headers):
    payload, source_a, source_b = archive_with_receipt(user)
    target = other_user(); target_auth = auth_headers(target.id)
    target_id = target.id
    def restore(data):
        return client.post('/api/backup/import', headers=target_auth, data={
            'file': (BytesIO(json.dumps(data).encode()), 'backup.json')})
    first = {**payload, 'attachments': []}
    assert restore(first).status_code == 200
    entry = ServiceEntry.query.filter_by(user_id=target_id).one()
    mapping = ImportIdentity.query.filter_by(user_id=target_id, entity_kind='vehicles', source_id=str(source_a)).one()
    # A local move before the receipt arrives is valid. The original source
    # receipt must not then reuse that entry with its old vehicle silently.
    entry.vehicle_id = mapping.target_id
    db.session.commit()
    identities_before = ImportIdentity.query.filter_by(user_id=target_id).count()
    response = restore(payload)
    assert response.status_code == 400, response.json
    assert response.json['issues'][0]['path'].startswith('attachments')
    assert Attachment.query.filter_by(user_id=target_id).count() == 0
    assert ImportIdentity.query.filter_by(user_id=target_id).count() == identities_before

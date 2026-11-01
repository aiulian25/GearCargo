"""GC-003 regressions run with real FK enforcement on SQLite and PostgreSQL."""
from datetime import date, timedelta
import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.exc import OperationalError

from app import db
from app.models import (Attachment, ActivityLog, Backup, BackupSchedule, BlockedDevice,
                        BlockedIP, ConsumableEntry, DueDismissal, EmailConsentLog, Entry,
                        FuelEntry, InsurancePolicy, NotificationLog, ParkingEntry,
                        PredictionAlert, PushSubscription, Reminder, RepairEntry,
                        ReportShare, ServiceEntry, TaxEntry, Todo, User, UserSession, Vehicle)
from app.utils.timeutils import utc_naive_now


@pytest.fixture(autouse=True)
def enforced_constraints(app, monkeypatch, tmp_path):
    from app.routes import backup
    monkeypatch.setattr(backup, 'get_uploads_folder', lambda: str(tmp_path / 'photos'))
    with app.app_context():
        if db.engine.dialect.name == 'sqlite':
            def enable(connection, _record):
                connection.execute('PRAGMA foreign_keys=ON')
            event.listen(db.engine, 'connect', enable)
            db.session.execute(text('PRAGMA foreign_keys=ON'))
            assert db.session.execute(text('PRAGMA foreign_keys')).scalar() == 1
            db.session.commit()
    yield


def write_file(root, relative, data=b'private receipt'):
    path = Path(root) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def simple_vehicle(app, user):
    v = Vehicle(user_id=user.id, name='Delete me')
    db.session.add(v); db.session.flush()
    path = write_file(app.config['UPLOAD_FOLDER'], f'{user.id}/receipt-{v.id}.pdf')
    db.session.add(Attachment(user_id=user.id, vehicle_id=v.id, filename=path.name, filepath=str(path)))
    db.session.commit()
    return v.id, path


def test_commit_failure_preserves_vehicle_and_receipt(app, user, monkeypatch):
    """The unchanged route deletes this file before its injected commit failure."""
    from app.routes.vehicles import delete_vehicle
    vid, receipt = simple_vehicle(app, user)
    uid = user.id
    def fail_commit():
        raise OperationalError('COMMIT', {}, RuntimeError('injected commit failure'))
    monkeypatch.setattr(db.session, 'commit', fail_commit)
    with app.test_request_context(f'/api/vehicles/{vid}?hard=true', method='DELETE'):
        try:
            response = delete_vehicle.__wrapped__(user, vid)
        except OperationalError:  # Baseline propagates; both paths must retain bytes.
            pass
        else:
            assert response[1] == 500
    db.session.rollback(); db.session.expire_all()
    assert receipt.read_bytes() == b'private receipt'
    assert db.session.get(Vehicle, vid).user_id == uid
    assert Attachment.query.filter_by(vehicle_id=vid).count() == 1


def populate_all(app, user):
    from app.routes.backup import get_uploads_folder
    vid, receipt = simple_vehicle(app, user)
    uid = user.id
    entries = []
    for cls in (FuelEntry, ServiceEntry, RepairEntry, TaxEntry, ParkingEntry, ConsumableEntry, Entry):
        row = cls(user_id=uid, vehicle_id=vid, date=date.today(), title=cls.__name__, amount=10)
        db.session.add(row); db.session.flush(); entries.append(row)
    service = entries[1]
    indirect_file = write_file(app.config['UPLOAD_FOLDER'], f'{uid}/indirect.pdf')
    indirect = Attachment(user_id=uid, vehicle_id=vid, entry_id=service.id, filename='indirect.pdf', filepath=str(indirect_file))
    db.session.add(indirect); db.session.flush()
    policy = InsurancePolicy(user_id=uid, vehicle_id=vid, provider='Company', premium=10,
        start_date=date.today(), end_date=date.today()+timedelta(days=30), document_attachment_id=indirect.id)
    db.session.add(policy); db.session.flush()
    renewal = InsurancePolicy(user_id=uid, vehicle_id=vid, provider='Company', premium=11,
        start_date=date.today(), end_date=date.today()+timedelta(days=60), renewed_from_id=policy.id)
    entries[3].insurance_policy_id = policy.id
    reminder = Reminder(user_id=uid, title='Reminder', due_date=date.today(), source_service_id=service.id)
    prediction = PredictionAlert(user_id=uid, vehicle_id=vid, alert_type='oil_change', title='Alert')
    todo = Todo(user_id=uid, vehicle_id=vid, title='Task')
    db.session.add_all([renewal, reminder, prediction, todo]); db.session.flush()
    db.session.add(NotificationLog(user_id=uid, reminder_id=reminder.id, prediction_id=prediction.id,
                                    title='Notice', notification_type='reminder', channel='push'))
    kinds = {'service': service.id, 'tax': entries[3].id, 'fine': entries[4].id,
             'parking': entries[4].id, 'consumable': entries[5].id, 'insurance': policy.id,
             'document': indirect.id, 'reminder': reminder.id, 'prediction': prediction.id, 'todo': todo.id}
    for kind, rid in kinds.items():
        db.session.add(DueDismissal(user_id=uid, kind=kind, ref_id=rid))
    photo = write_file(get_uploads_folder(), f'vehicles/{vid}.jpg', b'car photo')
    db.session.get(Vehicle, vid).photo = f'/uploads/vehicles/{vid}.jpg'
    share = ReportShare(user_id=uid, token_hash='a'*64, vehicle_ids=[vid], expires_at=utc_naive_now()+timedelta(days=1))
    db.session.add(share); db.session.commit()
    # Reproduce a pre-GC017 omitted vehicle through maintenance SQL. Normal ORM
    # writes now reject it; deletion must still find this legacy child by entry.
    indirect_id = indirect.id
    db.session.rollback()
    with db.engine.begin() as connection:
        connection.execute(Attachment.__table__.update().where(Attachment.id == indirect_id).values(vehicle_id=None))
    db.session.expire_all()
    return vid, [receipt, indirect_file, photo]


def other_owner():
    other = User(username='survivor', email='survivor@example.invalid', password_hash='fixture', is_active=True)
    db.session.add(other); db.session.flush()
    vehicle = Vehicle(user_id=other.id, name='Keep me')
    db.session.add(vehicle); db.session.commit()
    return other.id, vehicle.id


def test_vehicle_deletes_every_child_with_constraints(app, user, client, auth_headers):
    vid, files = populate_all(app, user)
    oid, ovid = other_owner()
    response = client.delete(f'/api/vehicles/{vid}?hard=true', headers=auth_headers(user.id))
    assert response.status_code == 200, response.json
    assert response.json['cleanup']['state'] == 'completed'
    db.session.expire_all()
    for cls in (Entry, Attachment, Reminder, PredictionAlert, Todo, InsurancePolicy, NotificationLog, DueDismissal):
        assert cls.query.filter_by(user_id=user.id).count() == 0, cls
    assert db.session.get(Vehicle, vid) is None
    assert db.session.get(Vehicle, ovid).user_id == oid
    assert all(not path.exists() for path in files)
    assert ReportShare.query.filter_by(user_id=user.id).one().revoked


def account_fixture(app, user):
    from app.routes.backup import get_uploads_folder
    vid, files = populate_all(app, user)
    oid, ovid = other_owner()
    admin = db.session.get(User, oid); admin.is_admin = True
    unbound = write_file(app.config['UPLOAD_FOLDER'], f'{user.id}/unbound.pdf')
    files.append(unbound)
    db.session.add(Attachment(user_id=user.id, filename=unbound.name, filepath=str(unbound)))
    archive = write_file(app.config['BACKUP_FOLDER'], 'personal.zip')
    files.append(archive)
    db.session.add(Backup(user_id=user.id, backup_type='full', filepath=str(archive)))
    db.session.add(BackupSchedule(user_id=user.id))
    avatar = write_file(get_uploads_folder(), f'avatars/{user.id}/current.jpg')
    history = write_file(get_uploads_folder(), f'avatars/{user.id}/history.jpg')
    abandoned = write_file(get_uploads_folder(), f'avatars/{user.id}/old.jpg')
    files.extend([avatar, history, abandoned])
    user.avatar = f'/uploads/avatars/{user.id}/current.jpg'
    user.preferences = {'avatar_history': [f'/uploads/avatars/{user.id}/history.jpg']}
    sub = PushSubscription(user_id=user.id, endpoint='https://push.invalid', p256dh_key='key', auth_key='key')
    db.session.add(sub); db.session.flush()
    db.session.add(NotificationLog(user_id=user.id, subscription_id=sub.id,
        notification_type='system', title='Private notice', channel='push'))
    db.session.add_all([
        Todo(user_id=user.id, title='Unbound task'),
        Reminder(user_id=user.id, title='Unbound reminder', due_date=date.today()),
        ActivityLog(user_id=user.id, event_type='login', description=user.email, ip_address='192.0.2.1'),
        ActivityLog(user_id=oid, event_type='user_created', event_category='admin',
                    description=f'Created {user.email}', extra_data={'created_user_id': user.id}),
        EmailConsentLog(user_id=user.id, action='grant', email_hash='b'*64),
        UserSession(user_id=user.id, jti='deleted-session', absolute_expires_at=utc_naive_now()+timedelta(days=1)),
        BlockedIP(ip_address='192.0.2.2', target_user_id=user.id, target_email=user.email,
                  blocked_by_id=user.id, unblocked_by_id=user.id, reason=user.email),
        BlockedDevice(device_fingerprint='f'*64, target_user_id=user.id, target_email=user.email,
                      blocked_by_id=user.id, unblocked_by_id=user.id, reason=user.email),
    ])
    db.session.commit()
    return oid, ovid, files


def test_account_deletes_owned_pii_unbound_files_and_every_fk(app, user, client, auth_headers, monkeypatch):
    from app.models import DeletionTask
    uid = user.id
    oid, ovid, files = account_fixture(app, user)
    # No Redis service in this fixture; model a deployment without Redis.
    monkeypatch.setitem(app.config, 'REDIS_URL', 'memory://')
    response = client.delete(f'/api/admin/users/{uid}', headers=auth_headers(oid, is_admin=True))
    assert response.status_code == 200, response.json
    assert response.json['cleanup']['state'] == 'completed'
    db.session.expire_all()
    assert db.session.get(User, uid) is None
    assert db.session.get(Vehicle, ovid).user_id == oid
    for table in db.metadata.tables.values():
        if 'user_id' in table.c:
            assert db.session.execute(select(table.c.id).where(table.c.user_id == uid)).first() is None, table.name
    for cls in (BlockedIP, BlockedDevice):
        row = cls.query.one()
        assert row.target_email is row.target_user_id is row.blocked_by_id is row.unblocked_by_id is row.reason is None
        assert row.is_active  # Retain the instance security block.
    audit = ActivityLog.query.filter_by(event_type='user_deleted').one()
    assert audit.user_id == oid and '@' not in audit.description and not audit.extra_data
    creation = ActivityLog.query.filter_by(event_type='user_created').one()
    assert creation.user_id == oid and '@' not in creation.description and not creation.extra_data
    assert all(not path.exists() for path in files)
    assert DeletionTask.query.count() == 0


@pytest.mark.parametrize('account', [False, True])
def test_cleanup_failure_is_durable_and_retryable(app, user, client, auth_headers, monkeypatch, account):
    from app.models import DeletionTask
    from app.services import deletion
    uid = user.id
    if account:
        oid, _, files = account_fixture(app, user)
        path, headers = f'/api/admin/users/{uid}', auth_headers(oid, is_admin=True)
        monkeypatch.setitem(app.config, 'REDIS_URL', 'memory://')
    else:
        vid, receipt = simple_vehicle(app, user)
        files = [receipt]
        path, headers = f'/api/vehicles/{vid}?hard=true', auth_headers(uid)
    original = deletion._remove_file
    monkeypatch.setattr(deletion, '_remove_file', lambda *a: (_ for _ in ()).throw(PermissionError('read only')))
    response = client.delete(path, headers=headers)
    assert response.status_code == 200 and response.json['cleanup']['state'] == 'pending'
    assert all(p.exists() for p in files)
    db.session.expire_all()
    assert DeletionTask.query.filter_by(kind='file').count() == len(files)
    monkeypatch.setattr(deletion, '_remove_file', original)
    db.session.remove()  # Retry from a new session, as on restart.
    assert deletion.cleanup_pending()['pending'] == 0
    assert deletion.cleanup_pending()['completed'] == 0
    assert all(not p.exists() for p in files)


def test_crash_after_commit_before_cleanup_retries(app, user, monkeypatch):
    from app.services.deletion import delete_owned_data, cleanup_pending
    from app.models import DeletionTask
    vid, receipt = simple_vehicle(app, user)
    delete_owned_data(user.id, vehicle_id=vid)  # Process can die here, before a single unlink.
    assert receipt.exists() and DeletionTask.query.count() == 1
    db.session.remove()
    assert cleanup_pending() == {'completed': 1, 'pending': 0}
    assert not receipt.exists()


def test_uncommitted_tasks_cannot_remove_files(app, user):
    from app.services.deletion import queue_file, cleanup_pending
    from app.models import DeletionTask
    path = write_file(app.config['UPLOAD_FOLDER'], 'not-committed.pdf')
    queue_file('a'*32, 'attachments', str(path), set())
    db.session.flush()
    assert cleanup_pending()['completed'] == 0
    assert path.exists()
    db.session.rollback()
    assert DeletionTask.query.count() == 0


def test_changed_file_is_not_erased(app, user):
    from app.services.deletion import delete_owned_data, cleanup_pending
    vid, receipt = simple_vehicle(app, user)
    delete_owned_data(user.id, vehicle_id=vid)
    receipt.write_bytes(b'replacement file')
    assert cleanup_pending()['pending'] == 1
    assert receipt.read_bytes() == b'replacement file'


def test_shared_file_survives_for_other_owner(app, user):
    from app.services.deletion import delete_owned_data, cleanup_pending
    vid, receipt = simple_vehicle(app, user)
    oid, ovid = other_owner()
    db.session.add(Attachment(user_id=oid, vehicle_id=ovid, filename=receipt.name, filepath=str(receipt)))
    db.session.commit()
    delete_owned_data(user.id, vehicle_id=vid)
    assert cleanup_pending()['pending'] == 0
    assert receipt.exists()


def test_shared_file_survives_overlapping_storage_roots(app, user, monkeypatch):
    from app.routes import backup
    from app.services.deletion import delete_owned_data, cleanup_pending
    vid, receipt = simple_vehicle(app, user)
    _, ovid = other_owner()
    monkeypatch.setattr(backup, 'get_uploads_folder', lambda: app.config['UPLOAD_FOLDER'])
    db.session.get(Vehicle, ovid).photo = '/uploads/' + str(receipt.relative_to(app.config['UPLOAD_FOLDER']))
    db.session.commit()
    delete_owned_data(user.id, vehicle_id=vid)
    assert cleanup_pending()['pending'] == 0
    assert receipt.exists()


@pytest.mark.parametrize('invalid', ['outside', 'symlink', 'cross_owner', 'external_policy'])
def test_conflicting_paths_or_links_fail_without_loss(app, user, client, auth_headers, tmp_path, invalid):
    vid, receipt = simple_vehicle(app, user)
    oid, ovid = other_owner()
    attachment = Attachment.query.filter_by(vehicle_id=vid).one()
    if invalid == 'outside':
        receipt = write_file(tmp_path, 'outside.pdf')
        attachment.filepath = str(receipt)
    elif invalid == 'symlink':
        link = receipt.with_name('link.pdf'); link.symlink_to(receipt)
        attachment.filepath = str(link)
    elif invalid == 'cross_owner':
        db.session.add(Todo(user_id=oid, vehicle_id=vid, title='Other owner'))
    else:
        policy = InsurancePolicy(user_id=oid, vehicle_id=ovid, provider='Keep', premium=1,
            start_date=date.today(), end_date=date.today())
        db.session.add(policy); db.session.commit()
        policy_id, attachment_id = policy.id, attachment.id
        db.session.rollback()
        with db.engine.begin() as connection:
            connection.execute(InsurancePolicy.__table__.update().where(InsurancePolicy.id == policy_id).values(document_attachment_id=attachment_id))
    db.session.commit()
    response = client.delete(f'/api/vehicles/{vid}?hard=true', headers=auth_headers(user.id))
    assert response.status_code == 409, response.json
    db.session.expire_all()
    assert db.session.get(Vehicle, vid) is not None
    assert receipt.exists()


def test_unknown_owner_hard_delete_is_404(app, user, client, auth_headers):
    _, vid = other_owner()
    assert client.delete(f'/api/vehicles/{vid}?hard=true', headers=auth_headers(user.id)).status_code == 404


def test_account_commit_failure_has_no_success_audit_or_file_loss(app, user, client, auth_headers, monkeypatch):
    from app.models import DeletionTask
    from app.routes.admin import delete_user
    uid = user.id
    oid, _, files = account_fixture(app, user)
    admin = db.session.get(User, oid)
    monkeypatch.setattr(db.session, 'commit', lambda: (_ for _ in ()).throw(RuntimeError('commit failure')))
    with app.test_request_context(method='DELETE'):
        response = delete_user.__wrapped__(admin, uid)
    assert response[1] == 500
    db.session.expire_all()
    assert db.session.get(User, uid) is not None
    assert all(p.exists() for p in files)
    assert DeletionTask.query.count() == 0
    assert ActivityLog.query.filter_by(event_type='user_deleted').count() == 0


def test_missing_file_and_cleanup_crash_are_idempotent(app, user, monkeypatch):
    from app.services import deletion
    from app.models import DeletionTask
    vid, receipt = simple_vehicle(app, user)
    deletion.delete_owned_data(user.id, vehicle_id=vid)
    original = deletion.sync_dir
    class Crash(BaseException):
        pass
    monkeypatch.setattr(deletion, 'sync_dir', lambda *a: (_ for _ in ()).throw(Crash()))
    with pytest.raises(Crash):
        deletion.cleanup_pending()
    assert not receipt.exists() and DeletionTask.query.count() == 1
    monkeypatch.setattr(deletion, 'sync_dir', original)
    assert deletion.cleanup_pending()['pending'] == 0


def test_migration_orphan_preflight_refuses_dirty_data(app):
    path = Path(__file__).parents[1] / 'migrations/versions/gc003_deletion_outbox.py'
    spec = importlib.util.spec_from_file_location('deletion_migration', path)
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    # A separate temporary SQLite database models legacy installations that did
    # not enable constraints. Never disable the test application's constraints.
    from sqlalchemy import create_engine
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE parent (id INTEGER PRIMARY KEY)'))
        connection.execute(text('CREATE TABLE child (id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES parent(id))'))
        connection.execute(text('INSERT INTO child VALUES (1, 42)'))
        with pytest.raises(RuntimeError, match='1 orphan rows in child.parent_id'):
            migration.check_orphans(connection)
        connection.execute(text('INSERT INTO parent VALUES (42)'))
        migration.check_orphans(connection)
    engine.dispose()


def test_ambiguous_commit_keeps_durable_cleanup(app, user, monkeypatch):
    from app.routes.vehicles import delete_vehicle
    from app.services.deletion import cleanup_pending
    from app.models import DeletionTask
    vid, receipt = simple_vehicle(app, user)
    real_commit = db.session.commit
    def committed_then_disconnected():
        real_commit()
        raise OperationalError('COMMIT', {}, RuntimeError('lost response'))
    monkeypatch.setattr(db.session, 'commit', committed_then_disconnected)
    with app.test_request_context(f'/api/vehicles/{vid}?hard=true', method='DELETE'):
        response = delete_vehicle.__wrapped__(user, vid)
    assert response[1] == 500 and 'confirm' in response[0].json['error']
    assert receipt.exists() and DeletionTask.query.count() == 1
    assert db.session.get(Vehicle, vid) is None
    assert cleanup_pending()['pending'] == 0
    assert not receipt.exists()


def test_busy_application_defers_delete_and_cleanup(app, user, client, auth_headers):
    from app.services.restore_transaction import activity_guard
    vid, receipt = simple_vehicle(app, user)
    headers = auth_headers(user.id)
    with activity_guard():
        response = client.delete(f'/api/vehicles/{vid}?hard=true', headers=headers)
        assert response.status_code == 503
        cli = app.test_cli_runner().invoke(args=['cleanup-deleted-files'])
        assert cli.exit_code != 0
    assert receipt.exists() and db.session.get(Vehicle, vid) is not None


def test_cleanup_cli_retries_after_storage_failure(app, user, monkeypatch):
    from app.services import deletion
    vid, receipt = simple_vehicle(app, user)
    deletion.delete_owned_data(user.id, vehicle_id=vid)
    original = deletion._remove_file
    monkeypatch.setattr(deletion, '_remove_file', lambda *a: (_ for _ in ()).throw(OSError('disk error')))
    result = app.test_cli_runner().invoke(args=['cleanup-deleted-files'])
    assert result.exit_code != 0 and 'pending: 1' in result.output
    assert receipt.exists()
    monkeypatch.setattr(deletion, '_remove_file', original)
    result = app.test_cli_runner().invoke(args=['cleanup-deleted-files'])
    assert result.exit_code == 0 and 'pending: 0' in result.output
    assert not receipt.exists()


def test_redis_cleanup_retries_without_affecting_other_accounts(app, user, monkeypatch):
    from app.models import DeletionTask
    from app.services import deletion
    import app as app_module
    uid, email = user.id, user.email
    oid, _, _ = account_fixture(app, user)
    deletion.delete_owned_data(uid, actor_id=oid)
    monkeypatch.setattr(app_module, 'redis_client', None)
    assert deletion.cleanup_pending()['pending'] == 1
    assert DeletionTask.query.one().kind == 'redis_user'
    keys = {f'session:{uid}:one', f'known_devices:{uid}', f'known_locations:{uid}', f'2fa_pending:{uid}',
            f'failed_login:{email}', f'lockout:{email}', f'security_answer_attempts:{email}',
            f'session:{oid}:two', f'known_devices:{oid}'}
    class Redis:
        def scan_iter(self, match, count):
            return iter([key for key in keys if key.startswith(match.rstrip('*'))])
        def delete(self, *deleted):
            keys.difference_update(deleted)
    monkeypatch.setattr(app_module, 'redis_client', Redis())
    assert deletion.cleanup_pending()['pending'] == 0
    assert keys == {f'session:{oid}:two', f'known_devices:{oid}'}


def test_missing_storage_retains_cleanup_task(app, user):
    from app.services.deletion import delete_owned_data, cleanup_pending
    vid, receipt = simple_vehicle(app, user)
    delete_owned_data(user.id, vehicle_id=vid)
    root = Path(app.config['UPLOAD_FOLDER'])
    offline = root.with_name('unmounted')
    root.rename(offline)
    assert cleanup_pending()['pending'] == 1
    offline.rename(root)
    assert receipt.exists()
    assert cleanup_pending()['pending'] == 0


def test_complete_inbound_foreign_key_inventory(app):
    """A new child table/link requires an explicit deletion-policy review."""
    expected = {
        'statement_batches': {'user_id'},
        'statement_transactions': {'user_id', 'batch_id'},
        'statement_matches': {'user_id', 'transaction_id', 'entry_id'},
        'tire_sets': {'user_id', 'vehicle_id', 'purchase_entry_id'},
        'tires': {'user_id', 'vehicle_id', 'tire_set_id'},
        'tire_fitments': {'user_id', 'vehicle_id', 'tire_set_id'},
        'tread_readings': {'user_id', 'vehicle_id', 'tire_set_id', 'tire_id'},
        'appointments': {'user_id', 'vehicle_id', 'preparation_reminder_id'},
        'appointment_tasks': {'user_id', 'vehicle_id', 'appointment_id', 'reminder_id', 'todo_id', 'service_id', 'prediction_id'},
        'appointment_expenses': {'user_id', 'vehicle_id', 'appointment_id', 'entry_id'},
        'import_batches': {'user_id'},
        'import_identities': {'user_id', 'first_batch_id', 'last_batch_id'},
        'vehicles': {'user_id'}, 'entries': {'user_id', 'vehicle_id'},
        **{name: {'id'} for name in ('fuel_entries', 'service_entries', 'repair_entries', 'parking_entries', 'consumable_entries')},
        'tax_entries': {'id', 'insurance_policy_id'},
        'attachments': {'entry_id', 'vehicle_id', 'user_id'},
        'insurance_policies': {'user_id', 'vehicle_id', 'document_attachment_id', 'renewed_from_id'},
        'reminders': {'user_id', 'vehicle_id', 'source_service_id', 'completed_from_id'},
        'prediction_alerts': {'user_id', 'vehicle_id'}, 'todos': {'user_id', 'vehicle_id', 'completed_from_id'},
        'notification_logs': {'user_id', 'subscription_id', 'reminder_id', 'prediction_id', 'vehicle_id'},
        **{name: {'user_id'} for name in ('backups', 'backup_schedules', 'push_subscriptions', 'email_consent_logs',
            'activity_logs', 'user_sessions', 'report_shares', 'due_dismissals', 'mutation_operations', 'calendar_outbox', 'scheduled_effects',
            'passkeys')},
        **{name: {'blocked_by_id', 'unblocked_by_id', 'target_user_id'} for name in ('blocked_ips', 'blocked_devices')},
    }
    actual = {table.name: {fk.parent.name for fk in table.foreign_keys}
              for table in db.metadata.tables.values() if table.foreign_keys}
    assert actual == expected

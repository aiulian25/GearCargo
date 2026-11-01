from datetime import date
from io import BytesIO
from pathlib import Path

import pytest
from app import db
from app.models import User, Vehicle, Attachment


def test_file_publish_failure_does_not_commit_records(app, user, tmp_path, monkeypatch):
    from app.routes import backup
    source = tmp_path / 'receipt.jpg'
    source.write_bytes(b'receipt')
    vehicle = Vehicle(user_id=user.id, name='Source')
    db.session.add(vehicle); db.session.flush()
    db.session.add(Attachment(user_id=user.id, vehicle_id=vehicle.id,
                              filename='receipt.jpg', filepath=str(source)))
    db.session.commit()
    archive, _ = backup.create_backup_zip(user)
    target = User(username='restore-target', email='restore@example.invalid')
    target.set_password('DisposableTestPassword123!')
    db.session.add(target); db.session.commit()
    target_id = target.id
    # chmod occurs after the current implementation's database commit.
    def no_space(*args, **kwargs):
        raise OSError(28, 'synthetic disk full')
    monkeypatch.setattr(backup.os, 'chmod', no_space)
    with app.test_request_context():
        try:
            backup.restore_from_zip(target, BytesIO(archive.getvalue()))
        except (OSError, RuntimeError):
            pass
    db.session.rollback(); db.session.expire_all()
    assert Vehicle.query.filter_by(user_id=target_id).count() == 0

import gzip
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import threading

from app.models import AppSetting
from app.services import restore_transaction as tx


class SimulatedCrash(BaseException):
    pass


def personal_fixture(app, user, tmp_path, monkeypatch):
    from app.routes import backup
    monkeypatch.setattr(backup, 'get_uploads_folder', lambda: str(tmp_path / 'photos'))
    source = tmp_path / 'source.jpg'; source.write_bytes(b'new receipt')
    vehicle = Vehicle(user_id=user.id, name='Imported car', vin='SOURCEVIN')
    db.session.add(vehicle); db.session.flush()
    db.session.add(Attachment(user_id=user.id, vehicle_id=vehicle.id,
                              filename='receipt.jpg', filepath=str(source)))
    db.session.commit()
    archive, data = backup.create_backup_zip(user)
    target = User(username='target', email='target@example.invalid', currency='USD')
    target.set_password('DisposableTestPassword123!')
    db.session.add(target); db.session.flush()
    db.session.add(Vehicle(user_id=target.id, name='Prior car', vin='PRIORVIN'))
    folder = Path(backup.get_attachment_folder()) / str(target.id)
    folder.mkdir(parents=True)
    # A pre-existing name collision must never be overwritten, even on success.
    original = folder / (hashlib.sha256(b'new receipt').hexdigest() + '_receipt.jpg')
    original.write_bytes(b'prior bytes')
    db.session.add(Attachment(user_id=target.id, filename='old.jpg', filepath=str(original)))
    db.session.commit()
    return target, archive.getvalue(), data, folder, original


def assert_personal_state(target_id, original, *, committed):
    db.session.rollback(); db.session.expire_all()
    assert Vehicle.query.filter_by(user_id=target_id).count() == (2 if committed else 1)
    assert Attachment.query.filter_by(user_id=target_id).count() == (2 if committed else 1)
    assert original.read_bytes() == b'prior bytes'
    if committed:
        attachment = Attachment.query.filter_by(user_id=target_id, filename='receipt.jpg').one()
        assert Path(attachment.filepath).read_bytes() == b'new receipt'
    else:
        assert db.session.get(User, target_id).currency == 'USD'
        assert [p for p in original.parent.rglob('*') if p.is_file()] == [original]
    assert not (tx.state_root() / 'active.json').exists()


@pytest.mark.parametrize('point', ['before_db_write', 'after_db_write', 'before_file_0',
                                   'after_file_0', 'before_commit', 'after_commit'])
@pytest.mark.parametrize('crash', [False, True], ids=['exception', 'process-interruption'])
def test_personal_faults_recover_old_or_committed_state(app, user, tmp_path, monkeypatch, point, crash):
    from app.routes import backup
    target, archive, _, _, original = personal_fixture(app, user, tmp_path, monkeypatch)
    target_id = target.id
    def fail(name, journal):
        if name == point:
            raise SimulatedCrash() if crash else OSError(28, 'synthetic disk full')
    monkeypatch.setattr(tx, 'checkpoint', fail)
    with app.test_request_context():
        if crash:
            with pytest.raises(SimulatedCrash):
                backup.restore_from_zip(target, BytesIO(archive))
        else:
            result = backup.restore_from_zip(target, BytesIO(archive))
            if point == 'after_commit':
                assert result.status_code == 200
            else:
                response, status = result
                assert status == 500 and response.get_json()['recovery']['state'] == 'rolled_back'
    if crash:
        db.session.rollback()  # Model the disconnected writer's SQL rollback.
        assert (tx.state_root() / 'active.json').exists()
        assert tx.recover_unfinished() == ('completed' if point == 'after_commit' else 'rolled_back')
        assert tx.recover_unfinished() == 'idle'
    assert_personal_state(target_id, original, committed=point == 'after_commit')


def test_ambiguous_personal_commit_uses_database_marker(app, user, tmp_path, monkeypatch):
    from app.routes import backup
    target, archive, _, _, original = personal_fixture(app, user, tmp_path, monkeypatch)
    target_id = target.id
    commit = db.session.commit
    def disconnect_after_commit():
        commit()
        raise OSError('connection lost after commit')
    monkeypatch.setattr(db.session, 'commit', disconnect_after_commit)
    with app.test_request_context():
        response = backup.restore_from_zip(target, BytesIO(archive))
    assert response.status_code == 200
    assert_personal_state(target_id, original, committed=True)


def test_staging_disk_full_leaves_database_and_files_unchanged(app, user, tmp_path, monkeypatch):
    from app.routes import backup
    target, archive, _, _, original = personal_fixture(app, user, tmp_path, monkeypatch)
    target_id = target.id
    monkeypatch.setattr(tx, 'write_bytes', lambda *_: (_ for _ in ()).throw(OSError(28, 'disk full')))
    with app.test_request_context():
        response, status = backup.restore_from_zip(target, BytesIO(archive))
    assert status == 500 and response.get_json()['recovery']['state'] == 'rolled_back'
    assert_personal_state(target_id, original, committed=False)


def test_json_failure_and_internal_helper_leave_commit_to_caller(app, user, tmp_path, monkeypatch):
    from app.routes import backup
    target, _, data, _, original = personal_fixture(app, user, tmp_path, monkeypatch)
    target_id = target.id
    backup.import_backup_data(target, data)
    db.session.rollback()
    assert_personal_state(target_id, original, committed=False)
    def fail(name, journal):
        if name == 'after_db_write':
            raise OSError('failed record transaction')
    monkeypatch.setattr(tx, 'checkpoint', fail)
    with app.test_request_context():
        response, status = backup.restore_from_json(target, BytesIO(json.dumps(data).encode()))
    assert status == 500 and response.get_json()['recovery']['state'] == 'rolled_back'
    assert_personal_state(target_id, original, committed=False)


def test_pending_recovery_blocks_requests_until_startup_recovery(app, user, client, tmp_path, monkeypatch):
    from app import create_app
    from app.routes import backup
    target, archive, _, _, original = personal_fixture(app, user, tmp_path, monkeypatch)
    target_id = target.id
    def fail(name, journal):
        if name == 'after_file_0':
            raise OSError('publish interrupted')
    with monkeypatch.context() as patch:
        patch.setattr(tx, 'checkpoint', fail)
        patch.setattr(tx, '_rollback_media', lambda _: (_ for _ in ()).throw(OSError('volume unavailable')))
        with app.test_request_context():
            response, status = backup.restore_from_zip(target, BytesIO(archive))
        assert status == 500 and response.get_json()['recovery']['state'] == 'recovery_required'
    assert client.get('/api/vehicles').status_code == 503
    status = client.get('/api/backup/recovery-status').get_json()
    assert status['maintenance'] and set(status) == {'maintenance', 'phase'}
    # Same persistent paths/DB, new factory: recovery precedes any startup work.
    configuration = type('RestartConfig', (), dict(app.config))
    restarted = create_app(configuration)
    assert restarted.test_client().get('/api/backup/recovery-status').get_json()['maintenance'] is False
    assert_personal_state(target_id, original, committed=False)


def test_exclusion_spans_processes_and_background_operations(app, tmp_path):
    with app.app_context():
        with tx.activity_guard(exclusive=True):
            lock = str(tx.state_root() / 'lock')
            script = 'import fcntl,os,sys\nf=os.open(sys.argv[1],os.O_RDWR)\ntry: fcntl.flock(f,fcntl.LOCK_SH|fcntl.LOCK_NB)\nexcept BlockingIOError: sys.exit(75)\nsys.exit(0)'
            result = subprocess.run([sys.executable, '-c', script, lock], check=False)
            assert result.returncode == 75
        started, finish = threading.Event(), threading.Event()
        @tx.background_activity
        def job(app):
            started.set(); finish.wait(5)
        thread = threading.Thread(target=job, args=(app,)); thread.start()
        assert started.wait(5)
        try:
            with pytest.raises(tx.RestoreBusy):
                with tx.activity_guard(exclusive=True):
                    pass
        finally:
            finish.set(); thread.join(5)
        with tx.activity_guard(exclusive=True):
            pass


def system_fixture(app, user, tmp_path, monkeypatch, *, invalid_checksum=False):
    from app.routes import backup
    roots = [tmp_path / 'live-attachments', tmp_path / 'live-uploads']
    for root in roots:
        (root / 'nested').mkdir(parents=True)
        (root / 'nested' / 'old.txt').write_bytes(b'old media')
    monkeypatch.setattr(backup, 'get_attachment_folder', lambda: str(roots[0]))
    monkeypatch.setattr(backup, 'get_uploads_folder', lambda: str(roots[1]))
    vehicle = Vehicle(user_id=user.id, name='old database')
    db.session.add(vehicle); db.session.commit(); vehicle_id = vehicle.id
    calls = []
    monkeypatch.setattr(backup, '_create_restore_database', lambda name, **kw: calls.append(('create', name)))
    monkeypatch.setattr(backup, '_drop_restore_database', lambda name: calls.append(('drop', name)))
    monkeypatch.setattr(backup, '_validate_restore_database', lambda name, **kw: calls.append(('validate', name)))
    monkeypatch.setattr(backup, '_write_pg_dump_file', lambda path, budget: path.write_bytes(gzip.compress(b'old database')))
    def apply(path, *, database=None, marker=None, journal=None, budget=None):
        calls.append(('sql', 'stage' if database else 'new' if marker else 'old'))
        if database:
            return
        db.session.get(Vehicle, vehicle_id).name = 'new database' if marker else 'old database'
        if marker:
            db.session.add(AppSetting(key=marker, value='system'))
        db.session.commit()
    monkeypatch.setattr(backup, '_restore_pg_dump_file', apply)
    archive = tmp_path / 'system.tar.gz'
    members = {'database/database.sql.gz': gzip.compress(b'new database'),
               'media/attachments/nested/new.txt': b'new attachments',
               'media/uploads/nested/new.txt': b'new uploads'}
    manifest = {'version': '3.1', 'backup_type': 'system_full', 'database': {'engine': 'postgresql'},
                'sha256': {name: hashlib.sha256(body).hexdigest() for name, body in members.items()}}
    if invalid_checksum:
        manifest['sha256']['database/database.sql.gz'] = '0' * 64
    with tarfile.open(archive, 'w:gz') as output:
        for name, body in {**members, 'manifest.json': json.dumps(manifest).encode()}.items():
            item = tarfile.TarInfo(name); item.size = len(body); output.addfile(item, BytesIO(body))
    return archive, roots, vehicle_id, calls


@pytest.mark.parametrize('point', ['before_directory_0', 'after_old_move_0', 'after_new_move_0',
    'after_directory_0', 'before_directory_1', 'after_old_move_1', 'after_new_move_1',
    'after_directory_1', 'before_db_write', 'after_commit'])
@pytest.mark.parametrize('crash', [False, True], ids=['exception', 'process-interruption'])
def test_system_cutover_and_crash_recovery(app, user, tmp_path, monkeypatch, point, crash):
    from app.routes import backup
    archive, roots, vehicle_id, calls = system_fixture(app, user, tmp_path, monkeypatch)
    root_inodes = [root.stat().st_ino for root in roots]
    def fail(name, journal):
        if name == point:
            raise SimulatedCrash() if crash else OSError(28, 'synthetic disk full')
    monkeypatch.setattr(tx, 'checkpoint', fail)
    if crash:
        with pytest.raises(SimulatedCrash):
            backup.restore_system_backup_archive(archive)
        assert tx.recover_unfinished() == ('completed' if point == 'after_commit' else 'rolled_back')
    elif point == 'after_commit':
        assert backup.restore_system_backup_archive(archive)['recovery']['state'] == 'completed'
    else:
        with pytest.raises(tx.RestoreFailure) as failure:
            backup.restore_system_backup_archive(archive)
        assert failure.value.state == 'rolled_back'
    db.session.expire_all()
    assert db.session.get(Vehicle, vehicle_id).name == ('new database' if point == 'after_commit' else 'old database')
    for root, inode in zip(roots, root_inodes):
        assert root.stat().st_ino == inode  # Mount-point roots were never renamed.
        files = [p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()]
        assert files == ['nested/new.txt' if point == 'after_commit' else 'nested/old.txt']
    assert not (tx.state_root() / 'active.json').exists()
    assert ('sql', 'stage') in calls and any(c[0] == 'validate' for c in calls)
    assert tx.recover_unfinished() == 'idle'


def test_system_checksum_and_schema_rejection_precede_live_changes(app, user, tmp_path, monkeypatch):
    from app.routes import backup
    archive, roots, vehicle_id, calls = system_fixture(app, user, tmp_path, monkeypatch, invalid_checksum=True)
    with pytest.raises(ValueError, match='checksum'):
        backup.restore_system_backup_archive(archive)
    assert not calls
    assert all((r / 'nested' / 'old.txt').read_bytes() == b'old media' for r in roots)


def test_system_sql_failure_restores_previous_database_and_both_directories(app, user, tmp_path, monkeypatch):
    from app.routes import backup
    archive, roots, vehicle_id, calls = system_fixture(app, user, tmp_path, monkeypatch)
    apply = backup._restore_pg_dump_file
    def reject(path, **kwargs):
        if kwargs.get('marker'):
            raise RuntimeError('SQL restore failed')
        return apply(path, **kwargs)
    monkeypatch.setattr(backup, '_restore_pg_dump_file', reject)
    with pytest.raises(tx.RestoreFailure) as failure:
        backup.restore_system_backup_archive(archive)
    assert failure.value.state == 'rolled_back' and ('sql', 'old') in calls
    assert db.session.get(Vehicle, vehicle_id).name == 'old database'
    assert all((r / 'nested' / 'old.txt').read_bytes() == b'old media' for r in roots)


@pytest.mark.skipif(os.environ.get('GC_RESTORE_POSTGRES_TESTS') != '1', reason='requires disposable PostgreSQL and CLI tools')
@pytest.mark.parametrize('fault', [None, 'before_db_write', 'after_commit'])
def test_real_postgres_system_restore(app, user, tmp_path, monkeypatch, fault):
    from app.routes import backup
    assert db.engine.dialect.name == 'postgresql'
    roots = [tmp_path / 'pg-attachments', tmp_path / 'pg-uploads']
    for root in roots:
        root.mkdir(); (root / 'receipt.txt').write_bytes(b'backup media')
    monkeypatch.setattr(backup, 'get_attachment_folder', lambda: str(roots[0]))
    monkeypatch.setattr(backup, 'get_uploads_folder', lambda: str(roots[1]))
    car = Vehicle(user_id=user.id, name='backup database')
    db.session.add(car); db.session.commit(); car_id = car.id
    archive, _, _, _ = backup.create_system_backup_archive(user)
    car.name = 'prior database'; db.session.commit()
    for root in roots:
        (root / 'receipt.txt').write_bytes(b'prior media')
    if fault:
        def fail(name, journal):
            if name == fault:
                raise SimulatedCrash()
        monkeypatch.setattr(tx, 'checkpoint', fail)
        with pytest.raises(SimulatedCrash):
            backup.restore_system_backup_archive(archive)
        assert tx.recover_unfinished() == ('completed' if fault == 'after_commit' else 'rolled_back')
    else:
        assert backup.restore_system_backup_archive(archive)['recovery']['state'] == 'completed'
    db.session.remove()
    restored = fault != 'before_db_write'
    assert db.session.get(Vehicle, car_id).name == ('backup database' if restored else 'prior database')
    assert all((root / 'receipt.txt').read_bytes() == (b'backup media' if restored else b'prior media') for root in roots)
    with db.engine.connect() as connection:
        assert not connection.execute(tx.text("SELECT datname FROM pg_database WHERE datname LIKE 'gc_restore_%'")).all()
    assert not (tx.state_root() / 'active.json').exists()


@pytest.mark.skipif(os.environ.get('GC_RESTORE_POSTGRES_TESTS') != '1', reason='requires disposable PostgreSQL and CLI tools')
def test_real_postgres_sql_error_rolls_back_earlier_statements(app, user, tmp_path):
    from app.routes import backup
    car = Vehicle(user_id=user.id, name='unchanged')
    db.session.add(car); db.session.commit(); car_id = car.id
    invalid = tmp_path / 'invalid.sql.gz'
    invalid.write_bytes(gzip.compress(b"UPDATE vehicles SET name = 'partial'; SELECT definitely_missing_function();"))
    with pytest.raises(RuntimeError, match='rejected'):
        backup._restore_pg_dump_file(invalid)
    assert db.session.get(Vehicle, car_id).name == 'unchanged'


@pytest.mark.skipif(os.environ.get('GC_RESTORE_POSTGRES_TESTS') != '1', reason='requires disposable PostgreSQL and CLI tools')
def test_real_process_death_stops_orphan_sql_and_recovers_old_database(app, user, tmp_path):
    import signal
    import time
    car = Vehicle(user_id=user.id, name='prior database')
    db.session.add(car); db.session.commit(); car_id = car.id
    worker = tmp_path / 'interrupted_worker.py'
    worker.write_text('''
import gzip, json, os
from app import create_app
from app.config import TestingConfig
from app.routes import backup
from app.services import restore_transaction as tx
class Config(TestingConfig):
    SQLALCHEMY_DATABASE_URI = os.environ['TEST_DATABASE_URL']
    BACKUP_FOLDER = os.environ['GC_TEST_BACKUP_FOLDER']
    UPLOAD_FOLDER = os.environ['GC_TEST_UPLOAD_FOLDER']
    VOLUMES_PATH = os.environ['GC_TEST_VOLUMES_PATH']
    SESSION_TYPE = 'filesystem'
    SESSION_FILE_DIR = os.environ['GC_TEST_SESSION_FOLDER']
app = create_app(Config)
with app.app_context(), tx.activity_guard(exclusive=True):
    journal = tx.Journal.create('system')
    previous = journal.directory / 'previous.sql.gz'
    tx.write_bytes(previous, backup._run_pg_dump_bytes())
    journal.data['previous_database_sha256'] = tx.digest(previous)
    journal.data['db_started'] = True
    journal.save('applying_database')
    incoming = journal.directory / 'incoming.sql.gz'
    tx.write_bytes(incoming, gzip.compress(b"UPDATE public.vehicles SET name='partial'; SELECT pg_sleep(60);"))
    backup._restore_pg_dump_file(incoming, marker=journal.marker, journal=journal)
''')
    environment = {**os.environ, 'GC_TEST_BACKUP_FOLDER': app.config['BACKUP_FOLDER'],
        'GC_TEST_UPLOAD_FOLDER': app.config['UPLOAD_FOLDER'],
        'GC_TEST_VOLUMES_PATH': app.config['VOLUMES_PATH'],
        'GC_TEST_SESSION_FOLDER': str(tmp_path / 'child-session')}
    with (tmp_path / 'worker.log').open('wb') as log:
        process = subprocess.Popen([sys.executable, str(worker)], env=environment, stdout=log, stderr=log)
        try:
            waiting = False
            for _ in range(100):
                with db.engine.connect() as connection:
                    waiting = connection.execute(tx.text("SELECT count(*) FROM pg_stat_activity WHERE application_name LIKE 'gearcargo-restore-%' AND wait_event = 'PgSleep'")).scalar() > 0
                if waiting:
                    break
                assert process.poll() is None, (tmp_path / 'worker.log').read_text()
                time.sleep(.1)
            assert waiting, 'restore SQL never reached the injected wait'
            os.kill(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
            assert tx.recover_unfinished() == 'rolled_back'
        finally:
            if process.poll() is None:
                process.kill(); process.wait(timeout=5)
            if (tx.state_root() / 'active.json').exists():
                tx.recover_unfinished()
    db.session.remove()
    assert db.session.get(Vehicle, car_id).name == 'prior database'
    with db.engine.connect() as connection:
        assert connection.execute(tx.text("SELECT count(*) FROM pg_stat_activity WHERE application_name LIKE 'gearcargo-restore-%'")).scalar() == 0


def test_prefork_worker_does_not_inherit_master_activity_lease(app):
    with app.app_context():
        read_fd, write_fd = os.pipe()
        with tx.activity_guard():
            child = os.fork()
            if child == 0:
                os.close(write_fd)
                os.read(read_fd, 1)
                try:
                    with tx.activity_guard(exclusive=True):
                        pass
                except Exception:
                    os._exit(1)
                os._exit(0)
        os.close(read_fd)
        os.write(write_fd, b'1'); os.close(write_fd)
        _, status = os.waitpid(child, 0)
        assert os.waitstatus_to_exitcode(status) == 0


def test_unknown_journal_blocks_cli_and_requests_without_deleting_evidence(app, client):
    with app.app_context():
        path = tx.state_root() / 'active.json'
        tx.atomic_json(path, {'version': 999, 'id': 'a' * 32, 'phase': 'unknown'})
    result = app.test_cli_runner().invoke(args=['recover-restores'])
    assert result.exit_code != 0
    assert path.exists()
    assert client.get('/api/vehicles').status_code == 503


def test_schema_rejection_never_reaches_live_cutover(app, user, tmp_path, monkeypatch):
    from app.routes import backup
    archive, roots, vehicle_id, calls = system_fixture(app, user, tmp_path, monkeypatch)
    monkeypatch.setattr(backup, '_validate_restore_database',
        lambda _, **kw: (_ for _ in ()).throw(ValueError('incompatible schema')))
    with pytest.raises(ValueError, match='incompatible schema'):
        backup.restore_system_backup_archive(archive)
    assert ('sql', 'new') not in calls and ('sql', 'old') not in calls
    assert all((root / 'nested' / 'old.txt').read_bytes() == b'old media' for root in roots)
    assert db.session.get(Vehicle, vehicle_id).name == 'old database'


def test_container_migration_gate_stops_when_recovery_fails(tmp_path):
    import shlex
    source = Path(__file__).resolve().parents[2] / 'docker/rootfs/etc/gearcargo/scripts/migrate.sh'
    bindir = tmp_path / 'bin'; bindir.mkdir()
    envfile = tmp_path / 'env.sh'
    envfile.write_text('GC_DB_HOST=disposable\nGC_DB_PORT=5432\nDATABASE_URL=disposable\n')
    (bindir / 'python3').write_text('#!/bin/sh\nexit 0\n')
    marker = tmp_path / 'migration-attempted'
    (bindir / 's6-setuidgid').write_text('#!/bin/sh\ncase "$*" in\n *recover-restores*) exit 17;;\n *) touch '+shlex.quote(str(marker))+'; exit 0;;\nesac\n')
    for file in bindir.iterdir(): file.chmod(0o755)
    script = tmp_path / 'migrate.sh'
    script.write_text(source.read_text().replace('. /etc/gearcargo/env.sh', '. '+shlex.quote(str(envfile)))
                      .replace('cd /app', 'cd '+shlex.quote(str(tmp_path))))
    result = subprocess.run(['bash', str(script)], env={**os.environ, 'PATH': str(bindir)+':'+os.environ['PATH']},
                            capture_output=True, text=True)
    assert result.returncode == 1
    assert 'refusing schema changes' in result.stderr and not marker.exists()


def test_completed_restore_remains_successful_if_audit_sink_fails(app, user, tmp_path, monkeypatch):
    from app.routes import backup
    target, archive, _, _, original = personal_fixture(app, user, tmp_path, monkeypatch)
    target_id = target.id
    monkeypatch.setattr(backup.security_audit, 'data_import',
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError('audit storage unavailable')))
    with app.test_request_context():
        response = backup.restore_from_zip(target, BytesIO(archive))
    assert response.status_code == 200 and response.get_json()['imported']['recovery']['state'] == 'completed'
    assert_personal_state(target_id, original, committed=True)


def test_corrupt_journal_cannot_delete_unrelated_directory(app, tmp_path):
    unrelated = tmp_path / 'keep'; unrelated.mkdir(); (unrelated / 'record').write_text('preserve')
    with app.app_context():
        with tx.activity_guard(exclusive=True):
            journal = tx.Journal.create('personal')
            journal.data['areas'] = [str(unrelated)]
            journal.data['phase'] = 'completed'
            journal.save()
        with pytest.raises(RuntimeError, match='journal paths'):
            tx.recover_unfinished()
        assert (unrelated / 'record').read_text() == 'preserve'
        assert (tx.state_root() / 'active.json').exists()

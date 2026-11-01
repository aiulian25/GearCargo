"""GC-028: artifact confidentiality, authenticated recovery and truthful metadata."""
from datetime import datetime, timezone
import gzip
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import tarfile
import zipfile

import pytest

from app import db
from app.models import Backup, BackupSchedule, Vehicle
from app.routes import backup

PASSPHRASE = 'independent backup secret 2026!'


@pytest.fixture
def crypto():
    from app.services import backup_encryption
    return backup_encryption


def test_plaintext_export_never_claims_encryption(client, user, auth_headers):
    response = client.post('/api/backup/export', headers=auth_headers(user.id), json={'format': 'zip'})
    assert response.status_code == 200
    assert zipfile.is_zipfile(BytesIO(response.data))
    record = Backup.query.filter_by(user_id=user.id).one()
    assert record.encrypted is False
    assert record.to_dict()['protection'] == 'plaintext'
    assert response.headers['X-Backup-Protection'] == 'plaintext'


@pytest.mark.parametrize('inner_format', ['json', 'zip', 'tar.gz'])
def test_authenticated_roundtrip_and_randomized_output(crypto, inner_format):
    clear = b'private vehicle, expenses, receipts' * 1000
    artifacts = []
    for _ in range(2):
        with crypto.protect_stream(BytesIO(clear), PASSPHRASE, inner_format) as artifact:
            encrypted = artifact.read()
            artifacts.append(encrypted)
            assert clear[:30] not in encrypted and PASSPHRASE.encode() not in encrypted
            assert not zipfile.is_zipfile(BytesIO(encrypted))
            with crypto.open_backup(BytesIO(encrypted), 'renamed.gcb', PASSPHRASE) as (restored, fmt):
                assert fmt == inner_format and restored.read() == clear
    assert artifacts[0] != artifacts[1]


@pytest.mark.parametrize('damage', ['key', 'missing_key', 'magic', 'version', 'format', 'salt', 'nonce', 'ciphertext', 'tag', 'truncated', 'empty'])
def test_rejects_before_plaintext_is_yielded(crypto, damage):
    with crypto.protect_stream(BytesIO(b'private data' * 100), PASSPHRASE) as artifact:
        data = bytearray(artifact.read())
    key = PASSPHRASE
    offsets = {'magic': 0, 'version': len(crypto.MAGIC), 'format': len(crypto.MAGIC) + 1,
               'salt': len(crypto.MAGIC) + 2, 'nonce': crypto.HEADER_SIZE - 1,
               'ciphertext': crypto.HEADER_SIZE + 1, 'tag': len(data) - 1}
    if damage in offsets: data[offsets[damage]] ^= 0xff
    elif damage == 'key': key = 'a different backup passphrase'
    elif damage == 'missing_key': key = None
    elif damage == 'truncated': data = data[:-7]
    elif damage == 'empty': data = bytearray()
    with pytest.raises(crypto.BackupEncryptionError):
        with crypto.open_backup(BytesIO(data), 'backup.zip.gcb', key):
            pytest.fail('Unauthenticated plaintext escaped')


def test_large_stream_has_bounded_reads_and_private_output(crypto, tmp_path):
    class BoundedReader:
        def __init__(self, source): self.source = source
        def __getattr__(self, name): return getattr(self.source, name)
        def read(self, size=-1):
            assert 0 < size <= crypto.CHUNK_SIZE
            return self.source.read(size)
    source = tmp_path / 'large'; encrypted = tmp_path / 'large.gcb'
    block = os.urandom(1024 * 1024)
    with source.open('wb') as f:
        for _ in range(64): f.write(block)
    with source.open('rb') as src, encrypted.open('wb') as target:
        crypto.encrypt_stream(BoundedReader(src), target, PASSPHRASE, 'tar.gz')
    with encrypted.open('rb') as artifact:
        with crypto.open_backup(BoundedReader(artifact), encrypted.name, PASSPHRASE) as (plain, fmt):
            assert fmt == 'tar.gz'
            assert os.fstat(plain.fileno()).st_mode & 0o777 == 0o600
            digest = hashlib.sha256()
            while chunk := plain.read(crypto.CHUNK_SIZE): digest.update(chunk)
            assert digest.hexdigest() == hashlib.sha256(block * 64).hexdigest()
    assert plain.closed


def test_interrupted_publish_preserves_previous_file_and_removes_partial(crypto, tmp_path):
    output = tmp_path / 'backup.gcb'; output.write_bytes(b'previous backup')
    class Interrupted:
        def read(self, size): raise OSError('simulated disk failure')
    with pytest.raises(OSError): crypto.atomic_write(Interrupted(), output)
    assert output.read_bytes() == b'previous backup'
    with pytest.raises(InterruptedError):
        crypto.atomic_write(BytesIO(b'new'), output,
                            lambda: (_ for _ in ()).throw(InterruptedError()))
    assert list(tmp_path.iterdir()) == [output]


def test_interrupted_encryption_closes_input_and_output(crypto, monkeypatch):
    source = BytesIO(b'private'); temporary = crypto.tempfile.TemporaryFile()
    monkeypatch.setattr(crypto.tempfile, 'TemporaryFile', lambda: temporary)
    def fail(*args):
        args[1].write(b'partial')
        raise OSError('simulated write failure')
    monkeypatch.setattr(crypto, 'encrypt_stream', fail)
    with pytest.raises(OSError): crypto.protect_stream(source, PASSPHRASE)
    assert source.closed and temporary.closed


@pytest.mark.parametrize('fmt', ['json', 'zip'])
def test_encrypted_export_and_import_preview_apply(client, user, auth_headers, crypto, fmt, caplog):
    headers = auth_headers(user.id)
    vehicle = Vehicle(user_id=user.id, name='Private family car')
    db.session.add(vehicle); db.session.commit()
    response = client.post('/api/backup/export', headers=headers, json={
        'format': fmt, 'encrypt': True, 'passphrase': PASSPHRASE})
    assert response.status_code == 200, response.json
    assert response.headers['X-Backup-Protection'] == 'encrypted'
    assert '.gcb' in response.headers['Content-Disposition']
    assert b'Private family car' not in response.data
    record = Backup.query.filter_by(user_id=user.id).one()
    assert record.encrypted and record.file_size == len(response.data)
    payload = response.data
    db.session.delete(vehicle); db.session.commit()
    def restore(key, **options):
        return client.post('/api/backup/import', headers=headers, data={
            'file': (BytesIO(payload), f'backup.{fmt}.gcb'), 'passphrase': key, **options})
    rejected = restore('wrong passphrase 123')
    assert rejected.status_code == 400 and Vehicle.query.count() == 0
    preview = restore(PASSPHRASE, preview='true')
    assert preview.status_code == 200, preview.json
    assert Vehicle.query.count() == 0
    applied = restore(PASSPHRASE, preview_token=preview.json['preview']['preview_token'], conflict_policy='reject')
    assert applied.status_code == 200, applied.json
    assert Vehicle.query.one().name == 'Private family car'
    assert PASSPHRASE not in caplog.text
    from flask import current_app
    audit_log = Path(current_app.config['VOLUMES_PATH']) / 'logs/security_audit.log'
    assert PASSPHRASE not in audit_log.read_text()
    assert PASSPHRASE not in json.dumps(record.to_dict())


@pytest.mark.parametrize('payload', [{'encrypt': True}, {'encrypt': True, 'passphrase': 'short'},
                                    {'encrypt': 'true'}, {'passphrase': PASSPHRASE}])
def test_invalid_policy_never_falls_back_to_plaintext(client, user, auth_headers, payload):
    response = client.post('/api/backup/run-now', headers=auth_headers(user.id), json=payload)
    assert response.status_code == 400
    assert Backup.query.count() == 0


def test_schedule_policy_sealed_retained_cleared_and_fails_closed(client, user, auth_headers, crypto):
    headers = auth_headers(user.id)
    response = client.put('/api/backup/schedule', headers=headers, json={'encryption_enabled': True, 'passphrase': PASSPHRASE})
    assert response.status_code == 200, response.json
    schedule = BackupSchedule.query.one()
    sealed = schedule.backup_passphrase_encrypted
    assert PASSPHRASE not in sealed and PASSPHRASE not in response.text and sealed not in response.text
    assert response.json['schedule']['has_backup_passphrase'] is True
    assert client.put('/api/backup/schedule', headers=headers, json={'hour': 4}).status_code == 200
    assert schedule.backup_passphrase_encrypted == sealed
    schedule.backup_passphrase_encrypted = 'unreadable'; db.session.commit()
    response = client.post('/api/backup/run-now', headers=headers, json={})
    assert response.status_code == 400 and Backup.query.count() == 0
    assert client.put('/api/backup/schedule', headers=headers, json={'encryption_enabled': False}).status_code == 200
    assert schedule.backup_passphrase_encrypted is None


def test_manual_storage_and_external_copy_use_identical_ciphertext(client, user, auth_headers, monkeypatch, crypto):
    schedule = BackupSchedule(user_id=user.id, external_enabled=True,
                              external_url='https://backup.invalid', external_api_key='user:password')
    db.session.add(schedule); db.session.commit()
    sent = []
    monkeypatch.setattr(backup, 'send_to_all_external_destinations', lambda data, *a, **kw: (sent.append((data, kw['filename'])) or ['test'], []))
    headers = auth_headers(user.id)
    response = client.post('/api/backup/run-now', headers=headers, json={
        'encrypt': True, 'passphrase': PASSPHRASE, 'send_external': True})
    assert response.status_code == 200, response.json
    record = Backup.query.one(); data = Path(record.filepath).read_bytes()
    assert record.encrypted and sent == [(data, record.filename)]
    assert os.stat(record.filepath).st_mode & 0o777 == 0o600
    listing = client.get('/api/backup/status', headers=headers).json['available_backups']
    assert listing[0]['encrypted'] and listing[0]['filename'].endswith('.zip.gcb')
    download = client.get('/api/backup/download/' + record.filename, headers=headers)
    assert download.data == data and download.headers['X-Backup-Protection'] == 'encrypted'
    wrong = client.post('/api/backup/restore/' + record.filename, headers=headers, json={'passphrase': 'wrong passphrase 123'})
    assert wrong.status_code == 400
    restored = client.post('/api/backup/restore/' + record.filename, headers=headers, json={'passphrase': PASSPHRASE, 'preview': True})
    assert restored.status_code == 200, restored.json
    response = client.post('/api/backup/send-external', headers=headers, json={})
    assert response.status_code == 200 and sent[-1][0] == data


def test_scheduled_policy_and_external_copy_are_encrypted(app, user, crypto, monkeypatch):
    import app.services as services
    now = datetime.now(timezone.utc)
    schedule = BackupSchedule(user_id=user.id, enabled=True, frequency='weekly', day_of_week=now.weekday(), hour=now.hour)
    crypto.update_schedule_protection(schedule, {'encryption_enabled': True, 'passphrase': PASSPHRASE})
    db.session.add(schedule); db.session.commit()
    sent = []
    monkeypatch.setattr(backup, 'send_to_all_external_destinations', lambda data, *a, **kw: (sent.append(data) or [], []))
    services.process_scheduled_backups(app)
    record = Backup.query.one()
    assert record.status == 'completed' and record.encrypted
    data = Path(record.filepath).read_bytes()
    assert sent == [data]
    with crypto.open_backup(BytesIO(data), record.filename, PASSPHRASE) as (plain, fmt):
        assert fmt == 'zip' and zipfile.is_zipfile(plain)
    # A lost runtime key must fail the next run, never publish plaintext.
    schedule.last_run_at = None; schedule.backup_passphrase_encrypted = 'bad'; db.session.commit()
    services.process_scheduled_backups(app)
    assert schedule.last_status == 'failed' and len(sent) == 1
    assert len(list(Path(record.filepath).parent.glob('*.zip*'))) == 1


def test_remote_restore_authenticates_before_saving_or_parsing(client, user, auth_headers, monkeypatch, crypto, app):
    archive, _ = backup.create_backup_zip(user)
    with crypto.protect_stream(archive, PASSPHRASE) as encrypted: data = encrypted.read()
    monkeypatch.setattr(backup, '_is_allowed_webdav_url', lambda url: True)
    monkeypatch.setattr(backup, '_resolve_webdav_auth', lambda *a: (('user', 'password'), None))
    class Response: status_code = 200; content = data
    monkeypatch.setattr(backup, '_safe_webdav_request', lambda *a, **kw: Response())
    headers = auth_headers(user.id)
    payload = {'filename': 'remote.zip.gcb', 'url': 'https://backup.invalid', 'passphrase': 'wrong passphrase 123'}
    response = client.post('/api/backup/external/restore', headers=headers, json=payload)
    assert response.status_code == 400
    path = Path(app.config['BACKUP_FOLDER']) / str(user.id) / payload['filename']
    assert not path.exists()
    response = client.post('/api/backup/external/restore', headers=headers, json={**payload, 'passphrase': PASSPHRASE})
    assert response.status_code == 200, response.json
    assert path.read_bytes() == data


@pytest.mark.parametrize('filename', ['saved.zip.gcb', 'SAVED.ZIP.GCB', 'saved.gcb', 'renamed.ZIP'])
def test_uploaded_encrypted_backup_is_verified_and_stored_as_ciphertext(client, user, auth_headers, crypto, app, filename):
    archive, _ = backup.create_backup_zip(user)
    with crypto.protect_stream(archive, PASSPHRASE) as artifact: data = artifact.read()
    headers = auth_headers(user.id)
    def upload(key):
        return client.post('/api/backup/upload', headers=headers, data={
            'file': (BytesIO(data), filename), 'passphrase': key})
    assert upload('wrong passphrase 123').status_code == 400
    response = upload(PASSPHRASE)
    assert response.status_code == 200 and response.json['encrypted']
    assert (Path(app.config['BACKUP_FOLDER']) / str(user.id) / response.json['filename']).read_bytes() == data
    repeated = upload(PASSPHRASE)
    assert repeated.status_code == 200 and repeated.json['filename'] != response.json['filename']
    names = {b['filename'] for b in client.get('/api/backup/status', headers=headers).json['available_backups']}
    assert names == {response.json['filename'], repeated.json['filename']}


def test_system_export_and_authentication_boundary(client, user, auth_headers, monkeypatch, crypto, app, tmp_path):
    user.is_admin = True; db.session.commit()
    headers = auth_headers(user.id, is_admin=True)
    monkeypatch.setattr(backup, '_run_pg_dump_bytes', lambda: gzip.compress(b'SELECT 1;'))
    monkeypatch.setattr(backup, 'get_uploads_folder', lambda: str(tmp_path / 'photos'))
    response = client.post('/api/backup/system/export', headers=headers, json={'encrypt': True, 'passphrase': PASSPHRASE})
    assert response.status_code == 200, response.json
    data = response.data
    with crypto.open_backup(BytesIO(data), 'system.tar.gz.gcb', PASSPHRASE) as (plaintext, fmt):
        assert fmt == 'tar.gz'
        with tarfile.open(fileobj=plaintext, mode='r:gz') as archive:
            manifest = json.load(archive.extractfile('manifest.json'))
            assert manifest['artifact_protection'] == 'encrypted'
            assert PASSPHRASE not in json.dumps(manifest)
    called = []
    def restore(path, *, budget):
        assert budget.remaining() > 0
        assert tarfile.is_tarfile(path)
        called.append(path)
        return manifest
    monkeypatch.setattr(backup, 'restore_system_backup_archive', restore)
    def upload(key):
        return client.post('/api/backup/system/import', headers=headers, data={
            'file': (BytesIO(data), 'system.tar.gz.gcb'), 'passphrase': key})
    assert upload('wrong passphrase 123').status_code == 400 and not called
    assert upload(PASSPHRASE).status_code == 200 and len(called) == 1
    assert not Path(called[0]).exists()


def test_shell_encryption_policy_retries_recovery_and_bad_key(tmp_path, crypto):
    repo = Path(__file__).resolve().parents[2]
    binary = tmp_path / 'bin'; binary.mkdir()
    dump = binary / 'pg_dump'; dump.write_text('#!/bin/sh\nprintf "SELECT 1;"\n'); dump.chmod(0o700)
    key = tmp_path / 'key'; key.write_text(PASSPHRASE + '\n'); key.chmod(0o600)
    root = tmp_path / 'archives'
    env = {**os.environ, 'PATH': str(binary) + ':' + os.environ['PATH'], 'BACKUP_ROOT': str(root),
           'ATTACHMENTS_DIR': str(tmp_path / 'none'), 'UPLOADS_DIR': str(tmp_path / 'none'),
           'BACKUP_PASSPHRASE_FILE': str(key), 'BACKUP_OCCURRENCE': '20261101_030000'}
    command = ['sh', str(repo / 'scripts/docker-backup.sh'), 'daily']
    run = subprocess.run(command, env=env, text=True, capture_output=True)
    assert run.returncode == 0, run.stderr
    artifact = next(root.rglob('*.gcb')); content = artifact.read_bytes()
    assert not list(root.rglob('*.tar.gz')) and not list(root.rglob('*.partial*'))
    assert PASSPHRASE not in run.stdout + run.stderr
    retry = subprocess.run(command, env=env, text=True, capture_output=True)
    assert retry.returncode == 0 and artifact.read_bytes() == content
    assert 'already archived' in retry.stdout
    recovery = tmp_path / 'recovered.tar.gz'
    run = subprocess.run(['python3', str(repo / 'backend/backup_crypto.py'), 'decrypt',
        '--input', str(artifact), '--output', str(recovery), '--passphrase-file', str(key)],
        env=env, text=True, capture_output=True)
    assert run.returncode == 0 and tarfile.is_tarfile(recovery)
    key.write_text('wrong independent secret')
    assert subprocess.run(command, env=env, capture_output=True).returncode != 0
    assert artifact.read_bytes() == content
    key.unlink()
    env['BACKUP_OCCURRENCE'] = '20261102_030000'
    assert subprocess.run(command, env=env, capture_output=True).returncode != 0
    assert len(list(root.rglob('*.gcb'))) == 1
    env['BACKUP_PASSPHRASE_FILE'] = ''
    run = subprocess.run(command, env=env, text=True, capture_output=True)
    assert run.returncode == 0 and 'Artifact protection: plaintext' in run.stdout
    assert tarfile.is_tarfile(next(root.rglob('*.tar.gz')))


def test_unknown_envelope_version_rejected_without_running_kdf(crypto, monkeypatch):
    header = crypto.MAGIC + bytes([255, 1]) + bytes(28)
    monkeypatch.setattr(crypto, '_key', lambda *a: pytest.fail('Untrusted version reached the KDF'))
    with pytest.raises(crypto.BackupEncryptionError):
        with crypto.open_backup(BytesIO(header + bytes(16)), 'archive.gcb', PASSPHRASE):
            pytest.fail('Unknown envelope opened')


def test_migration_corrects_legacy_claim_and_preserves_schedule(tmp_path):
    import importlib.util
    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    path = Path(__file__).resolve().parents[1] / 'migrations/versions/gc028_backup_protection.py'
    spec = importlib.util.spec_from_file_location('gc028', path)
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    engine = sa.create_engine('sqlite:///' + str(tmp_path / 'migration.sqlite'))
    with engine.begin() as connection:
        connection.execute(sa.text('CREATE TABLE backups (id INTEGER PRIMARY KEY, encrypted BOOLEAN)'))
        connection.execute(sa.text('CREATE TABLE backup_schedules (id INTEGER PRIMARY KEY, hour INTEGER)'))
        connection.execute(sa.text('INSERT INTO backups VALUES (1, true), (2, false), (3, NULL)'))
        connection.execute(sa.text('INSERT INTO backup_schedules VALUES (1, 7)'))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        assert connection.execute(sa.text('SELECT encrypted FROM backups')).scalars().all() == [0, 0, 0]
        assert connection.execute(sa.text('SELECT hour, encryption_enabled, backup_passphrase_encrypted FROM backup_schedules')).one() == (7, 0, None)
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
        assert connection.execute(sa.text('SELECT hour FROM backup_schedules')).scalar_one() == 7
    engine.dispose()


@pytest.mark.skipif(os.environ.get('GC_RESTORE_POSTGRES_TESTS') != '1', reason='requires disposable PostgreSQL')
def test_real_encrypted_system_restore_preserves_database_and_media(client, app, user, auth_headers, monkeypatch, tmp_path):
    user.is_admin = True
    car = Vehicle(user_id=user.id, name='encrypted system snapshot')
    db.session.add(car); db.session.commit(); car_id = car.id
    media = tmp_path / 'system-media'; photos = tmp_path / 'system-photos'
    media.mkdir(); photos.mkdir()
    receipt = media / 'receipt.txt'; receipt.write_bytes(b'original media')
    monkeypatch.setattr(backup, 'get_attachment_folder', lambda: str(media))
    monkeypatch.setattr(backup, 'get_uploads_folder', lambda: str(photos))
    headers = auth_headers(user.id, is_admin=True)
    response = client.post('/api/backup/system/export', headers=headers, json={'encrypt': True, 'passphrase': PASSPHRASE})
    assert response.status_code == 200, response.json
    data = response.data
    car.name = 'changed live database'; db.session.commit(); receipt.write_bytes(b'changed media')
    response = client.post('/api/backup/system/import', headers=headers, data={
        'file': (BytesIO(data), 'system.tar.gz.gcb'), 'passphrase': PASSPHRASE})
    assert response.status_code == 200, response.json
    db.session.remove()
    assert db.session.get(Vehicle, car_id).name == 'encrypted system snapshot'
    assert receipt.read_bytes() == b'original media'


@pytest.mark.parametrize('damaged_header', [False, True])
def test_encrypted_files_with_equal_sizes_are_not_deleted_as_duplicates(client, app, user, auth_headers, crypto, damaged_header):
    folder = Path(app.config['BACKUP_FOLDER']) / str(user.id); folder.mkdir()
    for name in ['one.zip.gcb', 'two.gcb']:
        with crypto.protect_stream(BytesIO(b'private file'), PASSPHRASE) as encrypted:
            if damaged_header:
                encrypted.write(b'!')
                encrypted.seek(0)
            crypto.atomic_write(encrypted, folder / name)
    response = client.get('/api/backup/status', headers=auth_headers(user.id))
    assert {b['filename'] for b in response.json['available_backups']} == {'one.zip.gcb', 'two.gcb'}
    assert len(list(folder.iterdir())) == 2


def test_external_directory_includes_encrypted_format_hints(client, user, auth_headers, monkeypatch):
    monkeypatch.setattr(backup, '_is_allowed_webdav_url', lambda url: True)
    monkeypatch.setattr(backup, '_resolve_webdav_auth', lambda *a: (('user', 'password'), None))
    class Response:
        status_code = 207
        content = b'''<d:multistatus xmlns:d="DAV:"><d:response><d:href>/GearCargo/</d:href></d:response>
        <d:response><d:href>/GearCargo/plain.zip</d:href><d:propstat><d:prop><d:getcontentlength>25</d:getcontentlength></d:prop></d:propstat></d:response>
        <d:response><d:href>/GearCargo/private.zip.gcb</d:href><d:propstat><d:prop><d:getcontentlength>25</d:getcontentlength></d:prop></d:propstat></d:response></d:multistatus>'''
        text = content.decode()
    monkeypatch.setattr(backup, '_safe_webdav_request', lambda *a, **kw: Response())
    response = client.post('/api/backup/external/files', headers=auth_headers(user.id), json={'url': 'https://backup.invalid', 'path': '/GearCargo'})
    assert response.status_code == 200, response.json
    assert {f['name']: f['protection'] for f in response.json['files']} == {
        'plain.zip': 'plaintext', 'private.zip.gcb': 'encrypted_unverified'}


def test_explicit_key_never_downgrades_to_plaintext(crypto):
    with pytest.raises(crypto.BackupEncryptionError):
        with crypto.open_backup(BytesIO(b'{}'), 'backup.json', PASSPHRASE):
            pytest.fail('An explicit key bypassed authentication')
    with crypto.open_backup(BytesIO(b'{}'), 'backup.json') as (plain, fmt):
        assert fmt == 'json' and plain.read() == b'{}'


def test_runtime_key_rotation_includes_schedule_without_changing_artifact_key(app, user, crypto, monkeypatch, capsys):
    import importlib.util
    import sys
    import app as app_module
    schedule = BackupSchedule(user_id=user.id)
    crypto.update_schedule_protection(schedule, {'encryption_enabled': True, 'passphrase': PASSPHRASE})
    db.session.add(schedule); db.session.commit()
    sealed = schedule.backup_passphrase_encrypted
    with crypto.protect_stream(BytesIO(b'independent archive'), PASSPHRASE) as artifact:
        data = artifact.read()
    old_seed = app.config.get('ENCRYPTION_KEY') or app.config['SECRET_KEY']
    monkeypatch.setitem(app.config, 'ENCRYPTION_KEY', 'new-runtime-key-for-gc028-rotation-1234')
    monkeypatch.setitem(app.config, 'ENCRYPTION_KEYS_OLD', old_seed)
    monkeypatch.setattr(app_module, 'create_app', lambda: app)
    monkeypatch.setattr(sys, 'argv', ['reencrypt_pii.py', '--execute'])
    path = Path(__file__).resolve().parents[2] / 'scripts/reencrypt_pii.py'
    spec = importlib.util.spec_from_file_location('rotate_gc028', path)
    rotation = importlib.util.module_from_spec(spec)
    previous_path = sys.path[:]
    try:
        spec.loader.exec_module(rotation)
        rotation.main()
    finally:
        sys.path[:] = previous_path
    db.session.refresh(schedule)
    assert schedule.backup_passphrase_encrypted != sealed
    monkeypatch.setitem(app.config, 'ENCRYPTION_KEYS_OLD', '')
    assert crypto.schedule_passphrase(schedule) == PASSPHRASE
    with crypto.open_backup(BytesIO(data), 'backup.gcb', PASSPHRASE) as (plain, _):
        assert plain.read() == b'independent archive'
    assert PASSPHRASE not in capsys.readouterr().out


def test_shell_failure_after_dump_removes_plaintext_and_partial_artifacts(tmp_path):
    import shlex
    repo = Path(__file__).resolve().parents[2]
    binary = tmp_path / 'bin'; binary.mkdir()
    key = tmp_path / 'key'; key.write_text(PASSPHRASE)
    # Configuration is valid at startup, but becomes unavailable during the job.
    dump = binary / 'pg_dump'
    dump.write_text('#!/bin/sh\nrm '+shlex.quote(str(key))+'\nprintf "SELECT 1;"\n')
    dump.chmod(0o700)
    root = tmp_path / 'archives'
    env = {**os.environ, 'PATH': str(binary) + ':' + os.environ['PATH'], 'BACKUP_ROOT': str(root),
           'ATTACHMENTS_DIR': str(tmp_path / 'none'), 'UPLOADS_DIR': str(tmp_path / 'none'),
           'BACKUP_PASSPHRASE_FILE': str(key)}
    before = set(Path('/tmp').glob('gc-backup.*'))
    run = subprocess.run(['sh', str(repo / 'scripts/docker-backup.sh'), 'manual'], env=env, text=True, capture_output=True)
    assert run.returncode != 0
    assert not [p for p in root.rglob('*') if p.is_file()]
    assert set(Path('/tmp').glob('gc-backup.*')) == before
    assert PASSPHRASE not in run.stdout + run.stderr

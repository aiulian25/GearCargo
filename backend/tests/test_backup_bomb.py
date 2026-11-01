"""Regression tests for M6: reject ZIP decompression bombs before any member is
read into memory. Uses a monkeypatched tiny per-member ceiling so the tests
allocate only a few KB (never GBs). Covers the helper and all three ZIP entry
points: /backup/import (restore_from_zip — also guards the delegated external &
stored restores), /backup/upload, and /backup/import/lubelog.
"""

import io
import zipfile

import pytest


def _zip(members):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    buf.seek(0)
    return buf


def test_check_zip_budget_passes_and_rejects(monkeypatch):
    from app.routes import backup as b

    # A normal small archive passes.
    with zipfile.ZipFile(_zip({"a.txt": b"hello"})) as zf:
        b._check_zip_budget(zf)  # no raise

    # A single oversized member is rejected.
    monkeypatch.setattr(b, "_MAX_MEMBER_BYTES", 3)
    with zipfile.ZipFile(_zip({"a.txt": b"hello"})) as zf:  # 5 > 3
        with pytest.raises(ValueError, match="too large"):
            b._check_zip_budget(zf)

    # The running total is rejected even when each member is small.
    monkeypatch.setattr(b, "_MAX_MEMBER_BYTES", 1000)
    monkeypatch.setattr(b, "_MAX_TOTAL_UNCOMPRESSED", 6)
    with zipfile.ZipFile(_zip({"a.txt": b"aaaa", "b.txt": b"bbbb"})) as zf:  # 8 > 6
        with pytest.raises(ValueError, match="expands"):
            b._check_zip_budget(zf)


def test_import_rejects_zip_bomb(app, client, user, auth_headers, monkeypatch):
    monkeypatch.setattr("app.routes.backup._MAX_MEMBER_BYTES", 1000)
    z = _zip({"backup_data.json": '{"vehicles":[]}', "attachments/1/big.bin": b"x" * 5000})
    resp = client.post(
        "/api/backup/import",
        data={"file": (z, "backup.zip"), "merge_mode": "merge"},
        headers=auth_headers(user.id),
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400, resp.get_json()
    msg = (resp.get_json() or {}).get("error", "").lower()
    assert "too large" in msg or "expands" in msg


def test_upload_rejects_zip_bomb(app, client, user, auth_headers, monkeypatch):
    monkeypatch.setattr("app.routes.backup._MAX_MEMBER_BYTES", 1000)
    z = _zip({"backup_data.json": '{"vehicles":[]}', "attachments/1/big.bin": b"x" * 5000})
    resp = client.post(
        "/api/backup/upload",
        data={"file": (z, "backup.zip")},
        headers=auth_headers(user.id),
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400, resp.get_json()
    msg = (resp.get_json() or {}).get("error", "").lower()
    assert "too large" in msg or "expands" in msg


def test_lubelog_rejects_zip_bomb(app, client, user, auth_headers, monkeypatch):
    """The budget check runs at the ZIP entry, before any LiteDB parsing, so a
    bomb is rejected (400) even without a valid LubeLogger structure."""
    monkeypatch.setattr("app.routes.backup._MAX_MEMBER_BYTES", 1000)
    z = _zip({"data.db": b"x" * 5000})
    resp = client.post(
        "/api/backup/import/lubelog",
        data={"file": (z, "lube.zip")},
        headers=auth_headers(user.id),
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400, resp.get_json()

# GC-035: system archives share one bounded restore path for uploads, stored
# backups and authenticated envelopes. Fixtures are KB/MB sized, never bombs.
import gzip
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path

from app import db
from app.models import Vehicle
from app.services import restore_transaction as tx


def _system_tar(path, members=None, sql=b'SELECT 1;', extra_headers=()):
    bodies = {'manifest.json': json.dumps({'version': '3.0', 'backup_type': 'system_full',
              'database': {'engine': 'postgresql'}}).encode(),
              'database/database.sql.gz': gzip.compress(sql), **(members or {})}
    with tarfile.open(path, 'w:gz') as archive:
        for name, body in bodies.items():
            info = tarfile.TarInfo(name); info.size = len(body)
            archive.addfile(info, io.BytesIO(body))
        for info in extra_headers:
            archive.addfile(info)
    return path


@pytest.mark.parametrize('key,value', [
    ('MAX_MEMBERS', 2), ('MAX_MEMBER_BYTES', 100),
    ('MAX_ARCHIVE_BYTES', 700), ('MAX_SQL_BYTES', 128),
    ('MAX_MANIFEST_BYTES', 32),
])
def test_system_budget_rejection_leaves_live_state_and_no_staging(app, user, tmp_path, monkeypatch, key, value):
    from app.routes import backup
    from test_restore_fault_recovery import system_fixture
    archive, roots, vehicle_id, calls = system_fixture(app, user, tmp_path, monkeypatch)
    # High ratio in BOTH layers, with only a few KB actually allocated.
    _system_tar(archive, {'media/attachments/new.txt': b'x' * 5000}, sql=b' ' * 5000)
    app.config['SYSTEM_RESTORE_' + key] = value
    with pytest.raises(ValueError, match='SYSTEM_RESTORE_' + key):
        backup.restore_system_backup_archive(archive)
    assert calls == []  # No validation DB, live SQL or publication.
    assert db.session.get(Vehicle, vehicle_id).name == 'old database'
    assert all((root / 'nested/old.txt').read_bytes() == b'old media' for root in roots)
    assert not (tx.state_root() / 'active.json').exists()
    assert not [p for p in tx.state_root().iterdir() if p.is_dir()]
    assert all(not list(root.rglob('.gc-restore-*')) for root in roots)


@pytest.mark.parametrize('damage', ['declared', 'pax', 'truncated_sql', 'truncated_tar', 'link', 'special', 'traversal'])
def test_system_malformed_archives_are_bounded(app, tmp_path, damage):
    from app.routes import backup
    with app.app_context():
        archive = tmp_path / 'bad.tar.gz'; stage = tmp_path / 'stage'; stage.mkdir()
        if damage in ('declared', 'pax'):
            # Header declares huge data, without allocating or writing its body.
            info = tarfile.TarInfo('media/attachments/huge')
            info.size = 2**40
            if damage == 'pax':
                info.type = tarfile.XHDTYPE
            archive.write_bytes(gzip.compress(info.tobuf(format=tarfile.GNU_FORMAT)))
        elif damage in ('link', 'special'):
            info = tarfile.TarInfo('media/attachments/evil')
            info.type = tarfile.SYMTYPE if damage == 'link' else tarfile.FIFOTYPE
            info.linkname = '/tmp/escape'
            _system_tar(archive, extra_headers=[info])
        elif damage == 'traversal':
            _system_tar(archive, {'media/attachments/../../escape': b'bad'})
        elif damage == 'truncated_sql':
            _system_tar(archive, {'database/database.sql.gz': gzip.compress(b' ' * 100000)[:-6]})
        else:
            _system_tar(archive)
            archive.write_bytes(archive.read_bytes()[:-6])
        with pytest.raises((ValueError, tarfile.TarError)):
            backup._stage_system_archive(archive, stage)
        assert not (tmp_path / 'escape').exists()


def test_system_low_disk_and_deadline_cleanup(app, user, tmp_path, monkeypatch):
    from app.routes import backup
    from app.services import system_restore_budget as limits
    from test_restore_fault_recovery import system_fixture
    archive, roots, vehicle_id, calls = system_fixture(app, user, tmp_path, monkeypatch)
    real_usage = limits.shutil.disk_usage
    monkeypatch.setattr(limits.shutil, 'disk_usage', lambda path: real_usage(path)._replace(free=1))
    with pytest.raises(ValueError, match='free staging/media space'):
        backup.restore_system_backup_archive(archive)
    assert not calls and not (tx.state_root() / 'active.json').exists()
    monkeypatch.setattr(limits.shutil, 'disk_usage', real_usage)
    clock = iter([0, 2000, 2001, 2002])
    monkeypatch.setattr(limits.time, 'monotonic', lambda: next(clock, 2003))
    with pytest.raises(ValueError, match='TIMEOUT_SECONDS'):
        backup.restore_system_backup_archive(archive)
    assert not calls and not (tx.state_root() / 'active.json').exists()
    assert db.session.get(Vehicle, vehicle_id).name == 'old database'
    assert all((r / 'nested/old.txt').read_bytes() == b'old media' for r in roots)


def test_large_system_archive_uses_bounded_reads(app, user, tmp_path, monkeypatch):
    from app.routes import backup
    from app.services import system_restore_budget as limits
    from test_restore_fault_recovery import system_fixture
    archive, roots, vehicle_id, calls = system_fixture(app, user, tmp_path, monkeypatch)
    # 16 MiB expansion across many chunks, including a legal long PAX path.
    name = 'media/attachments/' + 'long/' * 30 + 'receipt.txt'
    _system_tar(archive, {name: b'm' * (4 * 1024**2)}, sql=b' ' * (12 * 1024**2))
    real_read = gzip.GzipFile.read
    sizes = []
    def bounded_read(self, size=-1):
        assert 0 <= size <= limits.CHUNK
        sizes.append(size)
        return real_read(self, size)
    monkeypatch.setattr(gzip.GzipFile, 'read', bounded_read)
    assert backup.restore_system_backup_archive(archive)['recovery']['state'] == 'completed'
    assert len(sizes) > 200
    assert db.session.get(Vehicle, vehicle_id).name == 'new database'
    assert (roots[0] / name.removeprefix('media/attachments/')).stat().st_size == 4 * 1024**2
    assert not (tx.state_root() / 'active.json').exists()


@pytest.mark.parametrize('value', [0, -1, 'unlimited', None])
def test_system_restore_limits_cannot_be_disabled(app, value):
    from app.services.system_restore_budget import Budget
    with app.app_context():
        app.config['SYSTEM_RESTORE_MAX_SQL_BYTES'] = value
        with pytest.raises(ValueError, match='positive integer'):
            Budget()


@pytest.mark.parametrize('direction', ['input', 'output'])
def test_stalled_sql_pipe_has_a_deadline(app, direction):
    from app.services.system_restore_budget import Budget
    with app.app_context():
        app.config['SYSTEM_RESTORE_TIMEOUT_SECONDS'] = 1
        budget = Budget()
        process = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        try:
            with pytest.raises(ValueError, match='TIMEOUT_SECONDS'):
                if direction == 'input':
                    budget.send(process, [b'x' * 65536] * 4)
                else:
                    list(budget.output(process))
        finally:
            process.kill(); process.wait(timeout=5); process.stdin.close(); process.stdout.close()


@pytest.mark.skipif(os.environ.get('GC_RESTORE_POSTGRES_TESTS') != '1', reason='disposable PostgreSQL required')
@pytest.mark.parametrize('failure', ['timeout', 'truncated', 'limit', None])
def test_real_sql_stream_is_bounded_and_atomic(app, user, tmp_path, failure):
    from app.routes import backup
    car = Vehicle(user_id=user.id, name='unchanged')
    db.session.add(car); db.session.commit(); car_id = car.id
    sql = b"UPDATE vehicles SET name='restored';\n" + b'-- padding\n' * 400000
    if failure == 'timeout':
        sql += b'SELECT pg_sleep(30);'
        app.config['SYSTEM_RESTORE_TIMEOUT_SECONDS'] = 1
    if failure == 'limit':
        app.config['SYSTEM_RESTORE_MAX_SQL_BYTES'] = 128 * 1024
    compressed = gzip.compress(sql)
    path = tmp_path / 'incoming.sql.gz'
    path.write_bytes(compressed[:-6] if failure == 'truncated' else compressed)
    if failure:
        with pytest.raises((ValueError, RuntimeError)):
            backup._restore_pg_dump_file(path)
    else:
        backup._restore_pg_dump_file(path)
    assert db.session.get(Vehicle, car_id).name == ('unchanged' if failure else 'restored')


@pytest.mark.parametrize('where', ['during_extraction', 'destination'])
def test_disk_reserve_is_rechecked_and_staging_removed(app, user, tmp_path, monkeypatch, where):
    from app.routes import backup
    from app.services import system_restore_budget as limits
    from test_restore_fault_recovery import system_fixture
    archive, roots, vehicle_id, calls = system_fixture(app, user, tmp_path, monkeypatch)
    usage = limits.shutil.disk_usage
    checks = 0
    def disk(path):
        nonlocal checks
        checks += 1
        full = checks > 3 if where == 'during_extraction' else Path(path) in roots
        return usage(path)._replace(free=1) if full else usage(path)
    monkeypatch.setattr(limits.shutil, 'disk_usage', disk)
    with pytest.raises(ValueError, match='free staging/media space'):
        backup.restore_system_backup_archive(archive)
    assert ('sql', 'new') not in calls
    assert db.session.get(Vehicle, vehicle_id).name == 'old database'
    assert all((r / 'nested/old.txt').read_bytes() == b'old media' for r in roots)
    assert not (tx.state_root() / 'active.json').exists()
    assert not [p for p in tx.state_root().iterdir() if p.is_dir()]


@pytest.mark.parametrize('encrypted', [False, True])
def test_system_upload_budget_error_cleans_temporary_files(app, client, user, auth_headers, tmp_path, monkeypatch, encrypted):
    from app.routes import backup
    from app.services import backup_encryption
    user.is_admin = True; db.session.commit()
    app.config['SYSTEM_RESTORE_MAX_SQL_BYTES'] = 100
    monkeypatch.setattr(backup.tempfile, 'tempdir', str(tmp_path))
    archive = _system_tar(tmp_path / 'backup.tar.gz', sql=b' ' * 10000)
    body = io.BytesIO(archive.read_bytes()); filename = 'backup.tar.gz'
    if encrypted:
        output = io.BytesIO()
        backup_encryption.encrypt_stream(body, output, 'synthetic-test-passphrase', 'tar.gz')
        output.seek(0); body = output; filename += '.gcb'
    response = client.post('/api/backup/system/import', headers=auth_headers(user.id, is_admin=True),
        data={'file': (body, filename), 'passphrase': 'synthetic-test-passphrase' if encrypted else ''},
        content_type='multipart/form-data')
    assert response.status_code == 400, response.get_json()
    assert 'SYSTEM_RESTORE_MAX_SQL_BYTES' in response.get_json()['error']
    assert not list(tmp_path.glob('gearcargo-system-import-*'))
    assert not list(tmp_path.glob('gearcargo-authenticated-*'))
    assert not (tx.state_root() / 'active.json').exists()


def test_sql_child_memory_is_limited_before_input(app):
    from app.services.system_restore_budget import Budget
    with app.app_context():
        app.config['SYSTEM_RESTORE_MAX_PROCESS_BYTES'] = 64 * 1024**2
        process = subprocess.Popen([sys.executable, '-c',
            'import sys; sys.stdin.read(1); bytearray(128 * 1024**2)'],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            Budget().limit_process(process)
            process.communicate(b'x', timeout=5)
            assert process.returncode != 0
        finally:
            if process.poll() is None:
                process.kill(); process.wait(timeout=5)
            process.stdin.close()


@pytest.mark.parametrize('kind', ['metadata', 'global', 'chained', 'trailing', 'concatenated_sql'])
def test_nested_metadata_and_trailing_streams_cannot_bypass_budgets(app, tmp_path, kind):
    from app.routes import backup
    with app.app_context():
        path = tmp_path / 'archive.tar.gz'; stage = tmp_path / 'stage'; stage.mkdir()
        if kind == 'trailing':
            _system_tar(path)
            app.config['SYSTEM_RESTORE_MAX_ARCHIVE_BYTES'] = 20000
            with path.open('ab') as out:
                out.write(gzip.compress(b'\0' * 20000))
        elif kind == 'concatenated_sql':
            app.config['SYSTEM_RESTORE_MAX_SQL_BYTES'] = 100
            _system_tar(path, {'database/database.sql.gz': gzip.compress(b'a' * 60) + gzip.compress(b'b' * 60)})
        else:
            info = tarfile.TarInfo('extension'); info.type = tarfile.XHDTYPE
            if kind == 'metadata':
                app.config['SYSTEM_RESTORE_MAX_MANIFEST_BYTES'] = 100
                info.size = 1024
                content = info.tobuf()
            elif kind == 'global':
                info.type = tarfile.XGLTYPE
                content = info.tobuf()
            else:
                # Empty local PAX followed recursively by another PAX header.
                content = info.tobuf() * 2
            path.write_bytes(gzip.compress(content))
        with pytest.raises(ValueError):
            backup._stage_system_archive(path, stage)

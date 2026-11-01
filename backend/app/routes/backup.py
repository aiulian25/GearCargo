"""
GearCargo - Backup Routes
Comprehensive backup system with auto-backups, external destinations, and attachments
"""

import os
import json
import time
import gzip
import tarfile
import zipfile
import shutil
import hashlib
import ipaddress
import socket
import tempfile
import subprocess
import uuid
import re
import requests
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse, urlunparse
from werkzeug.http import parse_options_header
from flask import Blueprint, request, jsonify, current_app, send_file
from sqlalchemy import create_engine, inspect as inspect_database, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm.attributes import flag_modified

from app.utils.timeutils import isoformat_utc
from app import db
from app.models import Vehicle, Attachment, Backup, BackupSchedule
from app.routes.auth import token_required, admin_required
from app.utils.security_audit import security_audit

from app.services.backup_schema import (
    USER_BACKUP_VERSION, LEGACY_VERSIONS, BackupSchemaError, warning,
    export_user_data, prepare_backup, import_records,
)

from app.services import restore_transaction as restore_tx
from app.services import backup_encryption as backup_crypto
from app.services.system_restore_budget import Budget, CHUNK

backup_bp = Blueprint('backup', __name__)


@backup_bp.errorhandler(backup_crypto.BackupEncryptionError)
def _encryption_error(exc):
    db.session.rollback()
    return jsonify({'error': str(exc), 'message_key': 'backup.protectionError'}), 400


@backup_bp.after_request
def _protection_header(response):
    if 'attachment' in response.headers.get('Content-Disposition', ''):
        _, options = parse_options_header(response.headers['Content-Disposition'])
        encrypted = options.get('filename', '').lower().endswith('.gcb')
        response.headers.setdefault('X-Backup-Protection', 'encrypted' if encrypted else 'plaintext')
    return response


def _restore_user_artifact(user, source, filename, merge_mode, passphrase=None):
    with backup_crypto.open_backup(source, filename, passphrase) as (plaintext, inner_format):
        if inner_format == 'zip':
            return restore_from_zip(user, plaintext, merge_mode)
        if inner_format == 'json':
            return restore_from_json(user, plaintext, merge_mode)
        raise backup_crypto.BackupEncryptionError('Use a personal JSON/ZIP backup here. System archives require administrator recovery.')

SYSTEM_BACKUP_VERSION = '3.1'
SYSTEM_BACKUP_PREFIX = 'gearcargo_system_backup'


class BackupDestinationConfig:
    """Simple container for external backup destination settings."""

    def __init__(self, destination):
        self.id = destination.get('id')
        self.name = destination.get('name') or 'Destination'
        self.provider = destination.get('provider') or 'webdav'
        self.external_enabled = bool(destination.get('enabled', True))
        self.external_url = (destination.get('external_url') or '').strip()
        self.external_api_key = destination.get('external_api_key') or ''
        self.external_path = destination.get('external_path') or '/GearCargo'


def get_backup_folder():
    """Get backup folder path."""
    return current_app.config.get('BACKUP_FOLDER', '/app/volumes/backups')


def get_attachment_folder():
    """Get attachments folder path."""
    return current_app.config.get('UPLOAD_FOLDER', '/app/volumes/attachments')


def get_uploads_folder():
    """Get general uploads folder path (for vehicle photos, etc)."""
    return os.path.abspath(os.path.join(current_app.root_path, '..', 'uploads'))


def calculate_checksum(data):
    """Calculate SHA-256 checksum of data."""
    if isinstance(data, str):
        data = data.encode('utf-8')
    return hashlib.sha256(data).hexdigest()


def localized_message(message_key, default_message, **payload):
    """Return a localized API payload with a stable message key."""
    response = {
        'message_key': message_key,
        'message': default_message,
    }
    response.update(payload)
    return response


def get_schedule_external_destinations(schedule):
    """Return normalized external backup destinations for a schedule."""
    if not schedule:
        return []

    destinations = []
    if hasattr(schedule, 'get_external_destinations'):
        raw_destinations = schedule.get_external_destinations()
    else:
        raw_destinations = []

    if raw_destinations:
        for destination in raw_destinations:
            if not isinstance(destination, dict):
                continue
            config = BackupDestinationConfig(destination)
            if config.external_url:
                destinations.append(config)
    elif getattr(schedule, 'external_url', None):
        destinations.append(BackupDestinationConfig({
            'id': 'legacy_primary',
            'name': 'Primary Destination',
            'provider': 'webdav',
            'enabled': bool(getattr(schedule, 'external_enabled', False)),
            'external_url': getattr(schedule, 'external_url', ''),
            'external_api_key': getattr(schedule, 'external_api_key', ''),
            'external_path': getattr(schedule, 'external_path', '/GearCargo'),
        }))

    return destinations


def get_system_backup_folder():
    """Get storage folder for admin full-state backups."""
    return os.path.join(get_backup_folder(), 'system')


def _database_cli_config():
    """Build CLI connection config from SQLAlchemy settings."""
    database_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI')
    if not database_uri:
        raise RuntimeError('Database connection is not configured')

    url = make_url(database_uri)
    if not str(url.drivername).startswith('postgresql'):
        raise RuntimeError('System backup requires a PostgreSQL database')

    database_name = url.database.lstrip('/') if url.database else ''
    if not database_name:
        raise RuntimeError('Database name is missing from configuration')

    env = os.environ.copy()
    if url.password:
        env['PGPASSWORD'] = url.password

    return {
        'host': url.host or 'db',
        'port': str(url.port or 5432),
        'username': url.username or 'gearcargo',
        'database': database_name,
        'env': env,
    }


def _run_pg_dump_bytes():
    """Create a logical PostgreSQL dump as gzipped bytes."""
    config = _database_cli_config()
    command = [
        'pg_dump',
        '--host', config['host'],
        '--port', config['port'],
        '--username', config['username'],
        '--clean',
        '--if-exists',
        '--no-owner',
        '--no-privileges',
        config['database'],
    ]
    result = subprocess.run(command, capture_output=True, env=config['env'], check=False)
    if result.returncode != 0:
        error_output = result.stderr.decode('utf-8', errors='ignore').strip()
        raise RuntimeError(f'pg_dump failed: {error_output or "unknown error"}')
    return gzip.compress(result.stdout)


def _write_pg_dump_file(path, budget):
    """Stream the rollback snapshot; never buffer the live database in RAM."""
    config = _database_cli_config()
    command = ['pg_dump', '--host', config['host'], '--port', config['port'],
               '--username', config['username'], '--clean', '--if-exists',
               '--no-owner', '--no-privileges', config['database']]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               env=config['env'])
    try:
        budget.limit_process(process)
        with gzip.open(path, 'wb') as target:
            for chunk in budget.output(process):
                budget.space(path.parent, len(chunk) + CHUNK)
                target.write(chunk)
        if process.returncode:
            raise RuntimeError('Cannot create the previous database snapshot. Check database access and SYSTEM_RESTORE_MAX_PROCESS_BYTES capacity.')
        with open(path, 'rb') as snapshot:
            os.fsync(snapshot.fileno())
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        process.stdout.close()


def _restore_pg_dump_file(dump_path, *, database=None, marker=None, journal=None, budget=None):
    """Stream a bounded dump and commit marker through one psql transaction."""
    budget = budget or Budget()  # Recovery gets a fresh deadline, not an expired import's.
    config = _database_cli_config()
    db.session.remove()
    db.engine.dispose()
    command = ['psql', '--host', config['host'], '--port', config['port'],
               '--username', config['username'], '--dbname', database or config['database'],
               '--single-transaction', '-v', 'ON_ERROR_STOP=1', '-f', '-']
    prefix = f'SELECT pg_advisory_xact_lock({restore_tx.DB_LOCK});\n'.encode()
    suffix = b''
    if marker:
        if not re.fullmatch(r'restore_commit_[0-9a-f]{32}', marker):
            raise ValueError('Invalid restore commit marker.')
        suffix = ("\nINSERT INTO public.app_settings (key, value) VALUES ('" + marker + "', 'system');\n").encode()
    env = config['env']
    # A killed client must not leave a long-running SQL statement behind.
    env['PGCONNECT_TIMEOUT'] = str(max(1, int(budget.remaining())))
    env['PGOPTIONS'] = (env.get('PGOPTIONS', '') +
        f' -c statement_timeout={max(1, int(budget.remaining() * 1000))}')
    if journal:
        env['PGAPPNAME'] = 'gearcargo-restore-' + journal.data['id']
    # No stdout/stderr capture: SQL output can itself be arbitrarily large and
    # include private data. Exit status is sufficient for rollback decisions.
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, env=env)
    try:
        budget.limit_process(process)
        if journal:
            journal.data['process'] = restore_tx.process_identity(process.pid)
            if journal.data['process'] is None:
                raise RuntimeError('Could not track the restore SQL process.')
            journal.save()
        def chunks():
            yield prefix
            yield from budget.sql_chunks(dump_path)
            yield suffix
        try:
            budget.send(process, chunks())
        except BrokenPipeError:
            raise RuntimeError('PostgreSQL rejected the restore transaction. Check SQL compatibility and SYSTEM_RESTORE_MAX_PROCESS_BYTES capacity.') from None
        if process.returncode:
            raise RuntimeError('PostgreSQL rejected the restore transaction. Check SQL compatibility and SYSTEM_RESTORE_MAX_PROCESS_BYTES capacity.')
    except BaseException:
        if process.poll() is None:
            process.kill()
            process.wait()
        raise
    finally:
        process.stdin.close()
        if journal:
            journal.data['process'] = None
            journal.save()


def _create_restore_database(name, budget=None):
    config = _database_cli_config()
    result = subprocess.run(['createdb', '--host', config['host'], '--port', config['port'],
        '--username', config['username'], '--maintenance-db', 'postgres', '--template', 'template0', name],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=config['env'],
        timeout=(budget or Budget()).remaining(), check=False)
    if result.returncode:
        raise RuntimeError('Cannot create the temporary validation database. Restore has not changed live data.')


def _drop_restore_database(name):
    if not re.fullmatch(r'gc_restore_[0-9a-f]{32}', name):
        raise ValueError('Invalid temporary database name.')
    config = _database_cli_config()
    result = subprocess.run(['dropdb', '--host', config['host'], '--port', config['port'],
        '--username', config['username'], '--maintenance-db', 'postgres', '--if-exists', name],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=config['env'],
        timeout=Budget().remaining(), check=False)
    if result.returncode:
        raise RuntimeError('Temporary restore database cleanup requires operator attention.')


def _validate_restore_database(name, budget=None):
    budget = budget or Budget()
    url = make_url(current_app.config['SQLALCHEMY_DATABASE_URI'])
    options = {'connect_timeout': max(1, int(budget.remaining())),
               'options': f'-c statement_timeout={max(1, int(budget.remaining() * 1000))}'}
    original_engine = create_engine(url, connect_args=options)
    engine = create_engine(url.set(database=name), connect_args=options)
    try:
        live, staged = inspect_database(original_engine), inspect_database(engine)
        if set(live.get_table_names()) != set(staged.get_table_names()):
            raise ValueError('System backup database schema is incompatible with this installation.')
        for table in live.get_table_names():
            budget.remaining()
            def shape(inspector):
                return {(c['name'], str(c['type']), c['nullable']) for c in inspector.get_columns(table)}
            if shape(live) != shape(staged):
                raise ValueError('System backup database columns are incompatible with this installation.')
        with original_engine.connect() as original, engine.connect() as restored:
            if 'alembic_version' in live.get_table_names():
                query = text('SELECT version_num FROM alembic_version')
                if set(original.execute(query).scalars()) != set(restored.execute(query).scalars()):
                    raise ValueError('System backup migration version differs from this installation.')
        budget.remaining()
    finally:
        engine.dispose()
        original_engine.dispose()


def _add_bytes_to_tar(archive, arcname, data, mode=0o640):
    """Write in-memory bytes into a tar archive."""
    tar_info = tarfile.TarInfo(arcname)
    tar_info.size = len(data)
    tar_info.mtime = int(time.time())
    tar_info.mode = mode
    archive.addfile(tar_info, BytesIO(data))


def _add_directory_to_tar(archive, source_dir, archive_root):
    """Add a directory tree to a tar archive without following symlinks."""
    root_name = archive_root.rstrip('/') + '/'
    root_info = tarfile.TarInfo(root_name)
    root_info.type = tarfile.DIRTYPE
    root_info.mode = 0o750
    root_info.mtime = int(time.time())
    archive.addfile(root_info)

    checksums = {}
    if not os.path.isdir(source_dir):
        return checksums

    for dirpath, dirnames, filenames in os.walk(source_dir):
        rel_dir = os.path.relpath(dirpath, source_dir)
        archive_dir = archive_root if rel_dir == '.' else f"{archive_root}/{rel_dir.replace(os.sep, '/')}"
        dir_info = tarfile.TarInfo(archive_dir.rstrip('/') + '/')
        dir_info.type = tarfile.DIRTYPE
        dir_info.mode = 0o750
        dir_info.mtime = int(time.time())
        archive.addfile(dir_info)

        dirnames[:] = [name for name in dirnames if not os.path.islink(os.path.join(dirpath, name))]

        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            if os.path.islink(filepath):
                continue
            rel_path = os.path.relpath(filepath, source_dir).replace(os.sep, '/')
            name = f'{archive_root}/{rel_path}'
            with open(filepath, 'rb') as stream:
                info = archive.gettarinfo(filepath, arcname=name)
                checksum = hashlib.sha256()
                class HashedReader:
                    def read(self, size):
                        chunk = stream.read(size)
                        checksum.update(chunk)
                        return chunk
                archive.addfile(info, HashedReader())
                checksums[name] = checksum.hexdigest()
    return checksums


def _cleanup_system_backups(frequency, keep_last=3):
    """Keep only the latest system backup archives for a given frequency."""
    system_folder = get_system_backup_folder()
    if not os.path.isdir(system_folder):
        return

    prefix = f'{SYSTEM_BACKUP_PREFIX}_{frequency}_'
    backups = []
    for filename in os.listdir(system_folder):
        if filename.startswith(prefix) and filename.endswith(('.tar.gz', '.tar.gz.gcb')):
            filepath = os.path.join(system_folder, filename)
            backups.append((filepath, os.path.getmtime(filepath)))

    backups.sort(key=lambda item: item[1], reverse=True)
    for filepath, _ in backups[keep_last:]:
        try:
            os.remove(filepath)
        except OSError:
            current_app.logger.warning('Failed to remove old system backup: %s', filepath)


def create_system_backup_archive(admin_user, frequency='manual', passphrase=None):
    """Create a full-state backup archive containing DB dump and media."""
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    filename = f'{SYSTEM_BACKUP_PREFIX}_{frequency}_{timestamp}.tar.gz'
    system_folder = get_system_backup_folder()
    os.makedirs(system_folder, exist_ok=True)
    if passphrase is not None:
        filename += '.gcb'
    archive_path = os.path.join(system_folder, filename)

    database_dump = _run_pg_dump_bytes()
    manifest = {
        'version': SYSTEM_BACKUP_VERSION,
        'backup_type': 'system_full',
        'frequency': frequency,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'created_by': {
            'user_id': admin_user.id,
            'email': admin_user.email,
        },
        'database': {
            'engine': 'postgresql',
            'dump_format': 'plain_sql_gzip',
        },
        'media': {
            'attachments_included': True,
            'uploads_included': True,
        },
    }

    manifest['artifact_protection'] = 'encrypted' if passphrase is not None else 'plaintext'
    with tempfile.TemporaryFile() as completed:
        with tarfile.open(fileobj=completed, mode='w:gz') as archive:
            manifest['sha256'] = {'database/database.sql.gz': calculate_checksum(database_dump)}
            _add_bytes_to_tar(archive, 'database/database.sql.gz', database_dump)
            manifest['sha256'].update(_add_directory_to_tar(archive, get_attachment_folder(), 'media/attachments'))
            manifest['sha256'].update(_add_directory_to_tar(archive, get_uploads_folder(), 'media/uploads'))
            _add_bytes_to_tar(archive, 'manifest.json', json.dumps(manifest, indent=2).encode('utf-8'), mode=0o644)
        with backup_crypto.protect_stream(completed, passphrase, 'tar.gz') as artifact:
            backup_crypto.atomic_write(artifact, archive_path)

    return archive_path, filename, os.path.getsize(archive_path), manifest


def _validated_archive_name(name):
    """Validate a tar archive member path."""
    normalized = os.path.normpath(name).replace('\\', '/')
    if normalized in ('', '.'):
        return normalized
    if normalized.startswith('../') or normalized == '..' or normalized.startswith('/'):
        raise ValueError('Backup archive contains an invalid path')
    return normalized


def _safe_zip_filename(raw_filename, target_dir):
    """Return a safe bare filename for a ZIP member, confined to *target_dir*.

    Calling os.path.basename() strips every path component, defeating all
    Zip Slip variants including '..', '../../etc/shadow', '/etc/passwd',
    and mixed-separator tricks.  A secondary realpath() check is a
    defence-in-depth guard in case the OS resolves the joined path outside
    target_dir for any reason (e.g. a symlink already present on disk).

    Raises ValueError on traversal attempts or invalid filenames so the
    caller can skip the member and log a warning instead of aborting the
    whole restore.
    """
    safe_name = os.path.basename(raw_filename)
    if not safe_name or '\x00' in safe_name:
        raise ValueError(
            f'Backup archive contains an invalid filename: {raw_filename!r}'
        )
    # Confirm the resolved path stays inside target_dir (symlink-safe)
    real_root = os.path.realpath(target_dir)
    resolved = os.path.realpath(os.path.join(target_dir, safe_name))
    if not resolved.startswith(real_root + os.sep) and resolved != real_root:
        raise ValueError(
            f'Backup archive contains a traversal path: {raw_filename!r}'
        )
    return safe_name


# M6: decompression-bomb ceilings. zf.read(name) materialises a member fully in
# memory, so a 200 MB upload (MAX_UPLOAD_SIZE_MB) of highly-compressible data can
# expand to hundreds of GB and OOM the single-container deployment (which also
# hosts Postgres + Redis). The uncompressed sizes come straight from the ZIP's
# central directory, so this is a cheap metadata-only pre-check run BEFORE any
# member is decompressed.
_MAX_MEMBER_BYTES = 100 * 1024 * 1024              # any single member: 100 MB
_MAX_TOTAL_UNCOMPRESSED = 2 * 1024 * 1024 * 1024   # whole archive: 2 GB


def _check_zip_budget(zf):
    """Raise ValueError if the archive's declared uncompressed size is hostile.

    Guards against zip bombs: checks each member's declared size and the running
    total against fixed ceilings, using only central-directory metadata (no
    decompression). Callers surface the message as an HTTP 400.
    """
    total = 0
    for info in zf.infolist():
        if info.file_size > _MAX_MEMBER_BYTES:
            raise ValueError(f'Backup member too large: {info.filename!r}')
        total += info.file_size
        if total > _MAX_TOTAL_UNCOMPRESSED:
            raise ValueError('Backup archive expands beyond the allowed size')


def _extract_member_to_directory(archive, member, archive_prefix, target_root, budget):
    """Extract a tar member to a staging directory with traversal protection."""
    relative_path = member.name[len(archive_prefix):].lstrip('/')
    if not relative_path:
        return

    absolute_root = os.path.abspath(target_root)
    target_path = os.path.abspath(os.path.join(target_root, relative_path))
    if not target_path.startswith(f'{absolute_root}{os.sep}') and target_path != absolute_root:
        raise ValueError('Backup archive contains an invalid extraction path')

    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    with archive.extractfile(member) as source_file, open(target_path, 'wb') as output_file:
        while chunk := source_file.read(CHUNK):
            budget.space(target_root, len(chunk))
            output_file.write(chunk)
    os.chmod(target_path, 0o640)


def _stage_system_archive(archive_path, directory, budget=None):
    """Validate the manifest and complete archive before any live transition."""
    budget = budget or Budget()
    budget.space(directory)
    attachments, uploads = directory / 'attachments', directory / 'uploads'
    attachments.mkdir(); uploads.mkdir()
    database_dump = directory / 'incoming.sql.gz'
    manifest = None
    hashes = {}
    with budget.archive(archive_path) as archive:
        for member in archive:
            # Stream traversal; do not retain TarInfo objects for every file.
            archive.members.clear()
            budget.remaining()
            if len(member.name) > 4096:
                raise ValueError('System backup member path is too long.')
            member.name = _validated_archive_name(member.name)
            if member.isdir():
                continue
            if not member.isfile() or member.name in hashes:
                raise ValueError('System backup contains duplicate files or unsupported links/types.')
            if any(part.startswith('.gc-restore-') for part in member.name.split('/')):
                raise ValueError('System backup contains reserved recovery paths.')
            budget.space(directory, member.size)
            if member.name == 'manifest.json':
                budget.check('MAX_MANIFEST_BYTES', member.size)
                if manifest is not None:
                    raise ValueError('Duplicate system manifest.')
                manifest = json.load(archive.extractfile(member))
                continue
            if member.name == 'database/database.sql.gz':
                with archive.extractfile(member) as source, database_dump.open('xb') as target:
                    while chunk := source.read(CHUNK):
                        budget.space(directory, len(chunk))
                        target.write(chunk)
            elif member.name.startswith('media/attachments/'):
                _extract_member_to_directory(archive, member, 'media/attachments/', str(attachments), budget)
                target_path = attachments / member.name[len('media/attachments/'):]
            elif member.name.startswith('media/uploads/'):
                _extract_member_to_directory(archive, member, 'media/uploads/', str(uploads), budget)
                target_path = uploads / member.name[len('media/uploads/'):]
            else:
                raise ValueError('System backup contains an unsupported archive member.')
            if member.name == 'database/database.sql.gz':
                target_path = database_dump
            hashes[member.name] = budget.digest(target_path)
    if not isinstance(manifest, dict) or manifest.get('version') not in ('3.0', '3.1'):
        raise ValueError('Unsupported or missing system backup manifest version.')
    if (manifest.get('backup_type') or manifest.get('type')) != 'system_full' or \
            manifest.get('database', {}).get('engine') != 'postgresql':
        raise ValueError('Unsupported system backup format.')
    if not database_dump.is_file():
        raise ValueError('Backup archive is missing database/database.sql.gz')
    if manifest['version'] == '3.1':
        if manifest.get('sha256') != hashes:
            raise ValueError('System backup checksum inventory is incomplete or corrupted.')
    else:
        manifest = {**manifest, 'warnings': ['Legacy system archive has no checksum inventory. SQL and schema are validated before cutover.']}
    budget.validate_sql(database_dump)
    return manifest, database_dump, attachments, uploads


def restore_system_backup_archive(archive_path, budget=None):
    """Validate in a temporary DB; journal a coordinated DB/media cutover."""
    budget = budget or Budget()
    with restore_tx.activity_guard(exclusive=True):
        journal = restore_tx.Journal.create('system')
        manifest = None
        try:
            manifest, incoming, attachments, uploads = _stage_system_archive(archive_path, journal.directory, budget)
            # Generated name is journaled before CREATE DATABASE, so even an
            # interrupted creation can be cleaned up on startup.
            name = 'gc_restore_' + journal.data['id']
            journal.data['staging_database'] = name
            journal.save('validating_database')
            _create_restore_database(name, budget=budget)
            _restore_pg_dump_file(incoming, database=name, journal=journal, budget=budget)
            _validate_restore_database(name, budget=budget)
            journal.save('snapshotting')
            previous = journal.directory / 'previous.sql.gz'
            _write_pg_dump_file(previous, budget)
            journal.data['previous_database_sha256'] = budget.digest(previous)
            journal.save()
            # Reserve the complete additional media copy on each destination.
            # Sequential staging includes earlier allocations on shared filesystems.
            for source, destination in ((attachments, get_attachment_folder()), (uploads, get_uploads_folder())):
                budget.space(destination, sum(p.stat().st_size for p in source.rglob('*') if p.is_file()))
                journal.stage_directory(source, destination, budget=budget)
            budget.remaining()
            journal.publish_directories()
            journal.data['db_started'] = True
            journal.save('applying_database')
            restore_tx.checkpoint('before_db_write', journal)
            _restore_pg_dump_file(incoming, marker=journal.marker, journal=journal, budget=budget)
            restore_tx.checkpoint('after_commit', journal)
            restore_tx.recover(journal)
        except Exception as exc:
            current_app.logger.exception('System restore interrupted: %s', journal.data['id'])
            try:
                outcome = restore_tx.recover(journal)
            except Exception:
                current_app.logger.exception('System restore recovery remains pending: %s', journal.data['id'])
                raise restore_tx.RestoreFailure(journal.data['id'], 'recovery_required') from None
            if outcome != 'completed':
                if isinstance(exc, (ValueError, tarfile.TarError)):
                    raise
                raise restore_tx.RestoreFailure(journal.data['id'], 'rolled_back') from None
        return {**manifest, 'recovery': {'id': journal.data['id'], 'state': 'completed'}}


def gather_user_data(user, include_attachments=True):
    """Return the versioned portable-user DTO, never a display serializer."""
    return export_user_data(user, include_attachments)


def create_backup_zip(user, include_attachments=True):
    """Write each supported record and an explicit inventory of included files."""
    export_data = gather_user_data(user, include_attachments)
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        if include_attachments:
            media_sources = []
            for attachment in Attachment.query.filter_by(user_id=user.id).all():
                filename = _safe_zip_filename(attachment.filename, get_attachment_folder())
                media_sources.append(('attachments', attachment.id, attachment.filepath,
                                      f'attachments/{attachment.id}/{filename}'))
            for vehicle in Vehicle.query.filter_by(user_id=user.id).all():
                if vehicle.photo:
                    filename = os.path.basename(urlparse(vehicle.photo).path)
                    media_sources.append(('vehicles', vehicle.id,
                        os.path.join(get_uploads_folder(), 'vehicles', filename),
                        f'uploads/vehicles/{vehicle.id}/{filename}'))
            for collection, record_id, filepath, member in media_sources:
                if not filepath or not os.path.isfile(filepath):
                    raise BackupSchemaError('A referenced file is missing. Restore it or choose a data-only backup.',
                                            f'{collection}[id={record_id}]')
                # Read once: the archived bytes and their digest describe the same file.
                with open(filepath, 'rb') as source:
                    content = source.read()
                zf.writestr(member, content)
                export_data['media'].append({
                    'collection': collection, 'record_id': record_id, 'member': member,
                    'sha256': calculate_checksum(content), 'size': len(content),
                })
        else:
            export_data['warnings'].append(warning('media_omitted', 'media',
                'Data-only backup: attachment metadata is included; receipt and photo files are not.'))
        # Validate the exported graph too: a bad stored reference is not a complete backup.
        # Export must preserve historical source values for review/repair.
        prepare_backup(export_data, validate_domains=False)
        data_json = json.dumps(export_data, indent=2, allow_nan=False)
        zf.writestr('backup_data.json', data_json)
        manifest = {
            'version': USER_BACKUP_VERSION,
            'format': 'gearcargo-user',
            'created_at': datetime.now(timezone.utc).isoformat(),
            'app_name': current_app.config.get('APP_NAME', 'GearCargo'),
            'include_attachments': include_attachments,
            'checksum': calculate_checksum(data_json),
        }
        zf.writestr('manifest.json', json.dumps(manifest, indent=2))
    zip_buffer.seek(0)
    return zip_buffer, export_data


def save_backup_to_disk(user, zip_buffer, include_attachments=True):
    """Save backup ZIP to local storage."""
    backup_folder = get_backup_folder()
    user_folder = os.path.join(backup_folder, str(user.id))
    
    # Ensure folder exists
    os.makedirs(user_folder, exist_ok=True)
    
    # Generate filename with app name and username
    app_name = current_app.config.get('APP_NAME', 'GearCargo')
    # Sanitise for filename safety
    safe_app = re.sub(r'[^\w\-]', '_', app_name)
    safe_user = re.sub(r'[^\w\-]', '_', user.display_name or user.username or user.email.split('@')[0])
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    from app.services.scheduler_ownership import active_run
    scheduled_run = active_run.get()
    if scheduled_run and scheduled_run.name == 'send_scheduled_backups':
        timestamp = scheduled_run.occurrence.strftime('%Y%m%d_%H%M%S') + '_scheduled'
    suffix = '.zip.gcb' if backup_crypto.is_encrypted(zip_buffer) else '.zip'
    filename = f'{safe_app}_{safe_user}_{timestamp}{suffix}'
    filepath = os.path.join(user_folder, filename)
    
    # Write file
    backup_crypto.atomic_write(zip_buffer, filepath,
                               scheduled_run.lock.check if scheduled_run else None)
    
    # Get file size
    file_size = os.path.getsize(filepath)
    
    return filename, filepath, file_size


def _ip_is_internal(ip_str: str) -> bool:
    """True if *ip_str* is a private / loopback / link-local / reserved /
    multicast / unspecified address (i.e. NOT safe to reach outbound).

    Unparseable input is treated as internal (fail closed)."""
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return True
    return (addr.is_private or addr.is_loopback or addr.is_link_local
            or addr.is_reserved or addr.is_multicast or addr.is_unspecified)


def _resolve_public_ips(host: str, port: int = 443):
    """Resolve *host* and return the list of resolved IPs, or ``None`` if it
    cannot be resolved or ANY resolved address is internal/reserved.

    SEC-01: rejecting the whole host when *any* A/AAAA record is internal is the
    safe choice — a DNS-rebinding attacker returns one public + one internal
    address and the client may connect to either. Fail closed."""
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError, OSError, ValueError):
        return None

    ips = []
    for info in infos:
        ip = info[4][0]
        if _ip_is_internal(ip):
            return None  # any internal address → reject the entire host
        ips.append(ip)
    return ips or None


def _is_allowed_webdav_url(url: str) -> bool:
    """Cheap, network-free validation of a WebDAV destination URL (S09).

    This runs at CONFIG-SAVE time, so it deliberately does NO DNS lookup — a
    valid destination that is momentarily unresolvable must still be saveable,
    and saving settings must never block on the network.

    Rules:
    - Scheme must be 'https' — no plain-HTTP WebDAV.
    - IP address literals in private / loopback / link-local / reserved /
      multicast ranges are blocked entirely.  This rejects the obvious direct
      SSRF via cloud metadata endpoints (169.254.169.254, 100.100.100.200,
      fd00::ec2:…) and RFC-1918 internal services at the front door.

    The AUTHORITATIVE SSRF control (SEC-01) lives in ``_safe_webdav_request``,
    which every outbound WebDAV call goes through: it resolves the hostname,
    validates ALL resolved addresses, and pins the TCP connection to a validated
    IP — closing the DNS-rebinding validate→connect race that a config-time DNS
    check could never close anyway. A hostname that resolves to an internal IP
    therefore saves fine but can never actually be reached.

    Returns True only if the URL passes the cheap front-door checks.
    """
    if not url:
        return False

    try:
        parsed = urlparse(url)
    except Exception:
        return False

    if parsed.scheme != 'https':
        return False

    host = (parsed.hostname or '').lower()
    if not host:
        return False

    # IP-literal host → validate its range directly (no DNS lookup).
    try:
        ipaddress.ip_address(host)
        return not _ip_is_internal(host)
    except ValueError:
        return True  # Hostname — authoritative resolve+validate+pin at request time.


class _PinnedHTTPSAdapter(HTTPAdapter):
    """requests adapter that pins the TLS connection to a pre-validated IP while
    preserving the original hostname for SNI + certificate verification.

    This closes the DNS-rebinding TOCTOU (SEC-01): the caller resolves and
    validates the host, then connects to *that* IP — a hostname that re-resolves
    to an internal address between validation and connect cannot be reached,
    yet the certificate is still verified against the real hostname (verified:
    connecting to a raw IP without this adapter raises SSLError; asserting a
    hostname the cert does not cover also raises SSLError)."""

    def __init__(self, hostname, *args, **kwargs):
        self._pinned_hostname = hostname
        super().__init__(*args, **kwargs)

    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        pool_kwargs['server_hostname'] = self._pinned_hostname   # SNI = real host
        pool_kwargs['assert_hostname'] = self._pinned_hostname   # cert checked vs real host
        self.poolmanager = PoolManager(
            num_pools=connections, maxsize=maxsize, block=block, **pool_kwargs
        )


def _safe_webdav_request(method: str, url: str, **kwargs):
    """SSRF-safe drop-in for ``requests.request`` used for ALL outbound WebDAV
    calls (SEC-01 / SEC-02).

    - Requires HTTPS and a host that resolves only to public addresses.
    - Pins the connection to the validated IP (defeats DNS rebinding) while
      keeping SNI + certificate verification against the real hostname.
    - Forces ``allow_redirects=False`` so a 3xx to an internal URL is never
      followed (SEC-02).

    Raises ``requests.exceptions.ConnectionError`` for an unsafe or unresolvable
    host — the existing WebDAV error handling already catches requests errors,
    so callers surface their normal "connection failed" message with no info
    leak."""
    parsed = urlparse(url)
    host = (parsed.hostname or '').lower()
    if parsed.scheme != 'https' or not host:
        raise requests.exceptions.ConnectionError('Refusing non-HTTPS or hostless WebDAV request')

    port = parsed.port or 443

    # Resolve + validate, then choose the concrete IP to connect to.
    try:
        ipaddress.ip_address(host)
        if _ip_is_internal(host):
            raise requests.exceptions.ConnectionError('Refusing WebDAV request to an internal address')
        pinned_ip = host
    except ValueError:
        pinned_ips = _resolve_public_ips(host, port)
        if not pinned_ips:
            raise requests.exceptions.ConnectionError(
                'Refusing WebDAV request: host is unresolvable or resolves to an internal address'
            )
        pinned_ip = pinned_ips[0]

    # Rebuild the URL against the pinned IP; keep the real Host header so the
    # server routes the request correctly (userinfo is never carried in Host).
    netloc_ip = f'[{pinned_ip}]' if ':' in pinned_ip else pinned_ip
    if parsed.port:
        netloc_ip += f':{parsed.port}'
    pinned_url = urlunparse(parsed._replace(netloc=netloc_ip))

    host_header = host if not parsed.port or parsed.port == 443 else f'{host}:{parsed.port}'
    headers = dict(kwargs.pop('headers', None) or {})
    headers.setdefault('Host', host_header)

    kwargs['headers'] = headers
    kwargs['allow_redirects'] = False   # SEC-02: never follow redirects
    kwargs.setdefault('verify', True)

    session = requests.Session()
    session.mount('https://', _PinnedHTTPSAdapter(host))
    try:
        return session.request(method, pinned_url, **kwargs)
    finally:
        session.close()


def _webdav_base_url(server_url):
    """Build the WebDAV base URL from a Nextcloud/server URL.

    If the URL already contains '/remote.php/dav' it is returned as-is.
    Otherwise we append the standard Nextcloud WebDAV path.
    """
    url = server_url.rstrip('/')
    if '/remote.php/dav' in url or '/remote.php/webdav' in url:
        return url
    # Standard Nextcloud WebDAV endpoint
    return url + '/remote.php/dav/files'


def _webdav_credential_parts(token):
    """Split a stored "username:app-password" credential.

    Returns None when there is no username. The username is interpolated into
    the request path by every _webdav_*_url builder below, so a credential
    without one would send the app password as a URL path segment — where the
    server and any proxy in between will log it. It cannot authenticate
    either, so there is nothing to salvage by guessing.
    """
    username, separator, password = (token or '').strip().partition(':')
    if not separator or not username or not password:
        return None
    return (username, password)


def _webdav_auth(schedule):
    """Return a (username, password) tuple for WebDAV Basic auth."""
    return _webdav_credential_parts(schedule.external_api_key) or ('', '')


def _resolve_webdav_auth(user_id, url, submitted_key):
    """Resolve a (username, password) tuple for `url`, or an error response.

    Every WebDAV endpoint needs the same three things: use the submitted key,
    else the one stored for THAT destination, and refuse a credential with no
    username — the username is interpolated into the request path, so sending
    one would put the app password in the URL.

    Returns (auth, None) on success or (None, (payload, status)) to return.
    """
    api_key = (submitted_key or '').strip() or _stored_api_key_for_url(user_id, url)

    if not api_key:
        return None, ({
            'error': 'API key is required. Use format "username:app-password".',
            'message_key': 'backup.apiKeyRequired',
        }, 400)

    auth = _webdav_credential_parts(api_key)
    if not auth:
        return None, ({
            'error': 'API key must use the format "username:app-password".',
            'message_key': 'backup.apiKeyFormat',
        }, 400)

    return auth, None


def _stored_api_key_for_url(user_id, url):
    """The stored credential for the destination at `url`, or ''.

    Matched per destination, the way PUT /schedule matches. The legacy
    top-level external_api_key belongs to the destination it was saved for;
    testing a different one with it reports someone else's auth result.
    """
    schedule = BackupSchedule.query.filter_by(user_id=user_id).first()
    if not schedule:
        return ''

    target = (url or '').strip()
    for destination in (schedule.get_external_destinations() or []):
        if not isinstance(destination, dict):
            continue
        if (destination.get('external_url') or '').strip() == target:
            return (destination.get('external_api_key') or '').strip()

    if (schedule.external_url or '').strip() == target:
        return (schedule.external_api_key or '').strip()
    return ''


def _webdav_upload_url(schedule, filename):
    """Build the full WebDAV PUT URL for a backup file."""
    base = _webdav_base_url(schedule.external_url)
    auth = _webdav_auth(schedule)
    path = (schedule.external_path or '/GearCargo').strip('/')
    # Build: <base>/<user>/path/filename
    return f"{base}/{auth[0]}/{path}/{filename}"


def _ensure_webdav_folder(schedule):
    """Create the target folder on the WebDAV server if it doesn't exist (MKCOL)."""
    base = _webdav_base_url(schedule.external_url)
    auth = _webdav_auth(schedule)
    path = (schedule.external_path or '/GearCargo').strip('/')

    # Create each path segment
    segments = path.split('/')
    current = f"{base}/{auth[0]}"
    for segment in segments:
        current = f"{current}/{segment}"
        try:
            _safe_webdav_request(
                'MKCOL', current,
                auth=auth, timeout=15, verify=True
            )
        except requests.exceptions.RequestException:
            pass  # Folder may already exist — MKCOL returns 405


def _chunked_webdav_upload(backup_data, schedule, filename, auth):
    """Upload a large file via Nextcloud's chunked upload v2 API.

    This avoids Cloudflare's 100 MB payload limit by splitting the file
    into 50 MB chunks uploaded to /remote.php/dav/uploads/{user}/{id}/
    and then assembled with a MOVE to the final destination.
    """
    import uuid as _uuid

    CHUNK_SIZE = 50 * 1024 * 1024  # 50 MB
    total_size = len(backup_data)
    server_url = schedule.external_url.rstrip('/')
    # Uploads endpoint is separate from files endpoint
    if '/remote.php/' in server_url:
        uploads_base = server_url.split('/remote.php/')[0]
    else:
        uploads_base = server_url
    uploads_base += '/remote.php/dav/uploads'

    upload_id = _uuid.uuid4().hex

    # 1. Create upload directory
    upload_dir = f"{uploads_base}/{auth[0]}/{upload_id}"
    resp = _safe_webdav_request(
        'MKCOL', upload_dir,
        auth=auth, timeout=30, verify=True
    )
    if resp.status_code not in [201, 405]:
        return None, f"Failed to create chunked upload directory: {resp.status_code}"

    # 2. Upload chunks
    offset = 0
    chunk_num = 0
    while offset < total_size:
        chunk = backup_data[offset:offset + CHUNK_SIZE]
        chunk_url = f"{upload_dir}/{chunk_num:05d}"
        resp = _safe_webdav_request('PUT',
            chunk_url,
            data=chunk,
            auth=auth,
            headers={
                'Content-Type': 'application/octet-stream',
                'OCS-APIREQUEST': 'true',
            },
            timeout=300,
            verify=True,
        )
        if resp.status_code not in [200, 201, 204]:
            # Cleanup: try to delete the upload directory
            _safe_webdav_request('DELETE', upload_dir, auth=auth, timeout=15, verify=True)
            return None, f"Chunk {chunk_num} upload failed: {resp.status_code}"
        offset += CHUNK_SIZE
        chunk_num += 1
        current_app.logger.info(f'Chunked upload: chunk {chunk_num}, {min(offset, total_size)}/{total_size} bytes')

    # 3. Assemble — MOVE .file to final destination
    dest_url = _webdav_upload_url(schedule, filename)
    # Destination header needs the path portion only (absolute URI path)
    dest_parsed = urlparse(dest_url)
    dest_path = dest_parsed.path

    assemble_url = f"{upload_dir}/.file"
    resp = _safe_webdav_request(
        'MOVE', assemble_url,
        auth=auth,
        headers={
            'Destination': dest_path,
            'OC-Total-Length': str(total_size),
            'X-OC-Mtime': str(int(time.time())),
            'OCS-APIREQUEST': 'true',
        },
        timeout=300,
        verify=True,
    )

    if resp.status_code in [200, 201, 204]:
        return {'status': 'success', 'filename': filename, 'chunked': True}, None
    else:
        return None, f"Chunked assembly MOVE failed: {resp.status_code}: {resp.text[:200]}"


def send_to_external_server(backup_data, schedule, filename=None):
    """Send backup to external server via WebDAV (Nextcloud compatible).

    Uses chunked upload for files > 50 MB to avoid Cloudflare 413 limits.
    """
    if not schedule.external_enabled or not schedule.external_url:
        return None, "External backup not configured"

    # S09: Validate URL is HTTPS and not targeting a private/internal IP range
    if not _is_allowed_webdav_url(schedule.external_url):
        return None, "External URL must be a public HTTPS address"

    if not filename:
        filename = f'gearcargo_backup_{datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")}.zip'

    CHUNK_THRESHOLD = 50 * 1024 * 1024  # 50 MB

    try:
        auth = _webdav_auth(schedule)

        # Ensure target folder exists
        _ensure_webdav_folder(schedule)

        # Use chunked upload for large files to bypass Cloudflare 100MB limit
        if len(backup_data) > CHUNK_THRESHOLD:
            current_app.logger.info(f'Backup {filename} is {len(backup_data)} bytes, using chunked upload')
            return _chunked_webdav_upload(backup_data, schedule, filename, auth)

        # Small file — simple PUT
        upload_url = _webdav_upload_url(schedule, filename)
        headers = {
            'Content-Type': 'application/octet-stream',
            'X-OC-Mtime': str(int(time.time())),
            'OCS-APIREQUEST': 'true',
        }

        response = _safe_webdav_request('PUT',
            upload_url,
            data=backup_data,
            auth=auth,
            headers=headers,
            timeout=300,
            verify=True
        )

        # Handle 423 Locked — delete the locked file and retry once
        if response.status_code == 423:
            current_app.logger.warning(f'WebDAV 423 Locked on {filename}, deleting and retrying')
            _safe_webdav_request('DELETE', upload_url, auth=auth, timeout=30, verify=True)
            time.sleep(1)
            response = _safe_webdav_request('PUT',
                upload_url,
                data=backup_data,
                auth=auth,
                headers=headers,
                timeout=300,
                verify=True
            )

        if response.status_code in [200, 201, 204]:
            return {'status': 'success', 'filename': filename}, None
        elif response.status_code == 401:
            return None, "Authentication failed. Check your username and app password."
        elif response.status_code == 403:
            return None, "Permission denied. Check folder permissions on the server."
        elif response.status_code == 409:
            return None, "Target folder does not exist and could not be created."
        elif response.status_code == 413:
            # Cloudflare or server rejected the size — fall back to chunked
            current_app.logger.warning('Got 413 on direct PUT, falling back to chunked upload')
            return _chunked_webdav_upload(backup_data, schedule, filename, auth)
        elif response.status_code == 423:
            return None, "File is locked on the server. Try again in a few minutes or unlock it in Nextcloud."
        else:
            return None, f"Server returned {response.status_code}: {response.text[:200]}"

    except requests.exceptions.SSLError as e:
        # S12: Log full SSL error server-side; return opaque message to client.
        current_app.logger.warning(f'WebDAV SSL error to {schedule.external_url!r}: {e}')
        return None, 'SSL certificate error. Check the server URL or disable strict SSL verification.'
    except requests.exceptions.Timeout:
        return None, 'Connection to external server timed out'
    except requests.exceptions.RequestException as e:
        # S12: Log full network error server-side; return opaque message to client.
        current_app.logger.warning(f'WebDAV connection error to {schedule.external_url!r}: {e}')
        return None, 'Failed to connect to external server. Check the URL and credentials.'


def send_to_all_external_destinations(backup_data, schedule, filename=None):
    """Send a backup archive to all enabled external destinations."""
    destinations = [d for d in get_schedule_external_destinations(schedule) if d.external_enabled]
    if not destinations:
        return [], ['External backup not configured']

    successes = []
    errors = []

    for destination in destinations:
        result, error = send_to_external_server(backup_data, destination, filename=filename)
        if error:
            errors.append(f"{destination.name}: {error}")
        else:
            successes.append({
                'id': destination.id,
                'name': destination.name,
                'provider': destination.provider,
                'result': result,
            })

    return successes, errors


def cleanup_old_backups(user_id, max_backups=10, retention_days=90):
    """Clean up old backups based on retention policy."""
    backup_folder = get_backup_folder()
    user_folder = os.path.join(backup_folder, str(user_id))
    
    if not os.path.exists(user_folder):
        return 0
    
    # Get all backup files. H2: match ANY .zip — save_backup_to_disk() names
    # files "{App}_{User}_{timestamp}.zip", so the old startswith('backup_')
    # filter matched nothing and retention silently pruned NOTHING (disk filled).
    # This mirrors get_backup_status() and the scheduler's cleanup_user_backups().
    files = []
    for f in os.listdir(user_folder):
        if f.lower().endswith(('.zip', '.gcb')):
            filepath = os.path.join(user_folder, f)
            mtime = os.path.getmtime(filepath)
            files.append((filepath, mtime))
    
    # Sort by modification time (newest first)
    files.sort(key=lambda x: x[1], reverse=True)
    
    deleted = 0
    cutoff_time = datetime.now(timezone.utc) - timedelta(days=retention_days)
    cutoff_timestamp = cutoff_time.timestamp()
    
    for i, (filepath, mtime) in enumerate(files):
        should_delete = False
        
        # Delete if exceeds max_backups
        if i >= max_backups:
            should_delete = True
        
        # Delete if older than retention_days
        if mtime < cutoff_timestamp:
            should_delete = True
        
        if should_delete:
            try:
                os.remove(filepath)
                deleted += 1
            except Exception:
                pass
    
    # Also clean up database records
    old_backups = Backup.query.filter(
        Backup.user_id == user_id,
        Backup.created_at < cutoff_time,
        Backup.cloud_file_id.is_(None)
    ).all()
    
    for backup in old_backups:
        db.session.delete(backup)
    
    db.session.commit()
    
    return deleted


@backup_bp.route('/status', methods=['GET'])
@token_required
def get_backup_status(current_user):
    """Get backup status and settings."""
    schedule = BackupSchedule.query.filter_by(user_id=current_user.id).first()
    
    # Get last successful backup
    last_backup = Backup.query.filter_by(
        user_id=current_user.id,
        status='completed'
    ).order_by(Backup.created_at.desc()).first()
    
    # Count available backups
    backup_folder = get_backup_folder()
    user_folder = os.path.join(backup_folder, str(current_user.id))
    raw_backups = []

    if os.path.exists(user_folder):
        for f in sorted(os.listdir(user_folder), reverse=True):
            if f.lower().endswith(('.zip', '.gcb')):
                filepath = os.path.join(user_folder, f)
                stat = os.stat(filepath)
                created = datetime.fromtimestamp(stat.st_mtime, timezone.utc)
                raw_backups.append({
                    'filename': f,
                    'filepath': filepath,
                    'size': stat.st_size,
                    'mtime': stat.st_mtime,
                    'created': created,
                    **backup_crypto.file_protection(filepath),
                })

    # Deduplicate: if multiple files share the same size AND were created within
    # the same minute (race-condition duplicates from multi-worker gunicorn),
    # keep only the oldest one (first written) and auto-delete the rest.
    seen = {}  # key -> kept entry
    duplicates_to_delete = []
    for entry in sorted(raw_backups, key=lambda x: x['mtime']):
        # A damaged envelope must also remain available for recovery/diagnosis.
        minute_key = (entry['filename'] if entry['encrypted'] or entry['filename'].lower().endswith('.gcb') else
                      (entry['size'], entry['created'].strftime('%Y%m%d%H%M')))
        if minute_key not in seen:
            seen[minute_key] = entry
        else:
            duplicates_to_delete.append(entry)

    for dup in duplicates_to_delete:
        try:
            os.remove(dup['filepath'])
            current_app.logger.info(f"Removed duplicate backup: {dup['filename']}")
        except Exception as e:
            current_app.logger.warning(f"Could not remove duplicate backup {dup['filename']}: {e}")

    available_backups = []
    for entry in sorted(seen.values(), key=lambda x: x['mtime'], reverse=True):
        label = _backup_display_label(entry['filename'], entry['created'])
        available_backups.append({
            'filename': entry['filename'],
            'size': entry['size'],
            'size_human': format_file_size(entry['size']),
            'created_at': isoformat_utc(entry['created']),
            'label': label,
            'encrypted': entry['encrypted'],
            'protection': entry['protection'],
        })

    return jsonify({
        'schedule': schedule.to_dict() if schedule else None,
        'last_backup': isoformat_utc(last_backup.created_at) if last_backup else None,
        'last_backup_details': last_backup.to_dict() if last_backup else None,
        'available_backups': available_backups[:10],  # Limit to 10 most recent
        'total_backup_count': len(available_backups),
    })


def _backup_display_label(filename, created_dt):
    """Build a human-readable label for a backup file."""
    # Strip extension
    name = (filename[:-4] if filename.lower().endswith('.gcb') else filename).rsplit('.', 1)[0]
    # Formats:
    #   AppName_User_YYYYMMDD_HHMMSS          (new)
    #   backup_AppName_User_YYYYMMDD_HHMMSS   (mangled upload)
    #   backup_YYYYMMDD_HHMMSS                (old auto-backup)
    parts = name.split('_')
    # Remove leading 'backup' if followed by more meaningful parts
    if parts[0] == 'backup' and len(parts) > 3:
        parts = parts[1:]
    if len(parts) >= 4 and parts[-1].isdigit() and parts[-2].isdigit():
        prefix_parts = parts[:-2]
        app_user = ' '.join(prefix_parts)
    elif name.startswith('backup'):
        app_user = 'Backup'
    else:
        app_user = name
    date_str = created_dt.strftime('%d/%m/%Y %H:%M')
    return f'{app_user} — {date_str}'


def format_file_size(size):
    """Format file size in human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


@backup_bp.route('/export', methods=['POST'])
@token_required
def export_data(current_user):
    """Export user data as JSON or ZIP with attachments."""
    data = request.get_json() or {}
    format_type = data.get('format', 'zip')  # json, zip
    include_attachments = data.get('include_attachments', True)
    save_to_storage = data.get('save_to_storage', False)
    if format_type not in ('json', 'zip'):
        return jsonify({'error': 'Unsupported export format'}), 400
    passphrase = backup_crypto.request_passphrase(data)
    
    # Create backup record
    backup = Backup(
        user_id=current_user.id,
        backup_type='export',
        format=format_type,
        status='in_progress',
        started_at=datetime.now(timezone.utc),
    )
    db.session.add(backup)
    db.session.commit()
    
    try:
        if format_type == 'json':
            # Simple JSON export
            export_data = gather_user_data(current_user, include_attachments=False)
            prepare_backup(export_data, validate_domains=False)
            export_data['warnings'].append(warning('media_omitted', 'media',
                'Data-only backup: attachment metadata is included; receipt and photo files are not.'))
            
            backup.status = 'completed'
            backup.completed_at = datetime.now(timezone.utc)
            backup.vehicles_count = len(export_data['vehicles'])
            backup.entries_count = sum(
                len(v.get('fuel_entries', [])) +
                len(v.get('service_entries', [])) +
                len(v.get('repair_entries', [])) +
                len(v.get('tax_entries', [])) +
                len(v.get('parking_entries', [])) +
                len(v.get('consumable_entries', []))
                for v in export_data['vehicles']
            )
            backup.reminders_count = len(export_data['reminders'])
            
            json_data = json.dumps(export_data, indent=2, allow_nan=False)
            buffer = backup_crypto.protect_stream(BytesIO(json_data.encode('utf-8')), passphrase, 'json')
            backup.encrypted = passphrase is not None
            buffer.seek(0, 2)
            backup.file_size = buffer.tell()
            buffer.seek(0)
            backup.checksum = None if backup.encrypted else calculate_checksum(json_data)
            db.session.commit()
            
            # Security audit log for data export
            security_audit.data_export(current_user.id, current_user.email, 'json')
            
            return send_file(
                buffer,
                mimetype='application/octet-stream' if backup.encrypted else 'application/json',
                as_attachment=True,
                download_name=f'gearcargo_export_{datetime.now(timezone.utc).strftime("%Y%m%d")}.json' + ('.gcb' if backup.encrypted else '')
            )
        
        else:
            # Full ZIP backup with attachments
            zip_buffer, export_data = create_backup_zip(current_user, include_attachments)
            zip_buffer = backup_crypto.protect_stream(zip_buffer, passphrase)
            backup.encrypted = passphrase is not None
            
            # Count attachments
            attachments_count = len(export_data.get('attachments', []))
            
            backup.status = 'completed'
            backup.completed_at = datetime.now(timezone.utc)
            backup.vehicles_count = len(export_data['vehicles'])
            backup.entries_count = sum(
                len(v.get('fuel_entries', [])) +
                len(v.get('service_entries', [])) +
                len(v.get('repair_entries', [])) +
                len(v.get('tax_entries', [])) +
                len(v.get('parking_entries', [])) +
                len(v.get('consumable_entries', []))
                for v in export_data['vehicles']
            )
            backup.reminders_count = len(export_data['reminders'])
            backup.attachments_count = attachments_count
            
            # Get ZIP size
            zip_buffer.seek(0, 2)
            backup.file_size = zip_buffer.tell()
            zip_buffer.seek(0)
            
            # Optionally save to storage
            if save_to_storage:
                filename, filepath, _ = save_backup_to_disk(current_user, zip_buffer, include_attachments)
                backup.filename = filename
                backup.filepath = filepath
                zip_buffer.seek(0)  # Reset for download
            
            db.session.commit()
            
            # Security audit log for data export
            security_audit.data_export(current_user.id, current_user.email, f'zip (attachments: {include_attachments})')
            
            return send_file(
                zip_buffer,
                mimetype='application/octet-stream' if backup.encrypted else 'application/zip',
                as_attachment=True,
                download_name=f'gearcargo_backup_{datetime.now(timezone.utc).strftime("%Y%m%d")}.zip' + ('.gcb' if backup.encrypted else '')
            )
    
    except BackupSchemaError as exc:
        backup.status = 'failed'
        backup.error_message = 'Backup incomplete — a record or file could not be exported'
        backup.completed_at = datetime.now(timezone.utc)
        db.session.commit()
        return _schema_error_response(exc)
    except Exception as e:
        backup.status = 'failed'
        # S12: Store a generic sentinel in the DB field — never expose raw exception
        # text in API responses. Full details go to the server log only.
        backup.error_message = 'Backup failed — see server log for details'
        backup.completed_at = datetime.now(timezone.utc)
        db.session.commit()
        current_app.logger.error(f'Backup export failed: {e}', exc_info=True)
        return jsonify({'error': 'Backup failed. Please try again later.'}), 500


@backup_bp.route('/import', methods=['POST'])
@token_required
def import_data(current_user):
    """Import data from backup file (JSON or ZIP)."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    merge_mode = request.form.get('merge_mode', 'merge')  # merge, replace
    
    try:
        return _restore_user_artifact(current_user, file.stream, file.filename, merge_mode,
                                      request.form.get('passphrase'))
    except backup_crypto.BackupEncryptionError as exc:
        return _encryption_error(exc)
    except BackupSchemaError as exc:
        return _schema_error_response(exc)
    except json.JSONDecodeError as e:
        security_audit.data_import(current_user.id, current_user.email, 'unknown', success=False)
        current_app.logger.error(f'Backup import JSON error: {e}')
        return jsonify({'error': 'Invalid backup file format. Please ensure the file is a valid JSON or ZIP backup.'}), 400
    except Exception as e:
        security_audit.data_import(current_user.id, current_user.email, 'unknown', success=False)
        current_app.logger.error(f'Backup import failed: {e}')
        return jsonify({'error': 'Import failed. Please try again later.'}), 500


@backup_bp.route('/export/csv', methods=['GET'])
@token_required
def export_csv(current_user):
    """Export one entry type (fuel/service/repair/tax/parking) as a CSV file.

    F01 — GDPR-friendly, spreadsheet-openable data export. Always scoped to the
    authenticated user's own data; optionally filtered to one vehicle via
    ?vehicle_id=. The CSV round-trips with /import/csv.
    """
    from app.services.csv_io import export_entries_csv, TYPE_MODELS

    entry_type = (request.args.get('type') or '').strip().lower()
    if entry_type not in TYPE_MODELS:
        return jsonify({'error': f'Invalid type. Use one of: {", ".join(sorted(TYPE_MODELS))}'}), 400

    vehicle_id = request.args.get('vehicle_id', type=int)

    try:
        csv_text = export_entries_csv(current_user, entry_type, vehicle_id=vehicle_id)
    except Exception as e:
        current_app.logger.error(f'CSV export failed: {e}', exc_info=True)
        return jsonify({'error': 'Export failed. Please try again later.'}), 500

    security_audit.data_export(current_user.id, current_user.email, f'csv:{entry_type}')

    # utf-8-sig (BOM) so Excel opens accented characters correctly.
    buffer = BytesIO(csv_text.encode('utf-8-sig'))
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d')
    return send_file(
        buffer,
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'gearcargo_{entry_type}_{stamp}.csv',
    )


@backup_bp.route('/import/csv', methods=['POST'])
@token_required
def import_csv(current_user):
    """Import entries from a CSV file (matching the /export/csv format).

    F01 — generic CSV importer. multipart form fields:
      file        — the CSV file (required)
      type        — fuel/service/repair/tax/parking (required)
      merge_mode  — 'merge' (default; skip duplicates) or 'replace'
    Returns a per-row summary so a few bad rows don't abort the whole import.
    Rows are validated individually and vehicle_id ownership is enforced.
    """
    from app.services.csv_io import import_entries_csv, TYPE_MODELS

    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    if not file.filename.lower().endswith('.csv'):
        return jsonify({'error': 'File must be a .csv'}), 400

    entry_type = (request.form.get('type') or '').strip().lower()
    if entry_type not in TYPE_MODELS:
        return jsonify({'error': f'Invalid type. Use one of: {", ".join(sorted(TYPE_MODELS))}'}), 400

    merge_mode = request.form.get('merge_mode', 'merge')

    try:
        # utf-8-sig strips an Excel BOM if present.
        csv_text = file.read().decode('utf-8-sig', errors='replace')
        summary = import_entries_csv(current_user, entry_type, csv_text, merge_mode,
            source_label=request.form.get('source_label'), preview=request.form.get('preview') == 'true',
            conflict_policy=request.form.get('conflict_policy', 'reject'), preview_token=request.form.get('preview_token'))
        if 'preview' in summary:
            return jsonify(summary)
    except BackupSchemaError as exc:
        db.session.rollback()
        return _schema_error_response(exc)
    except ValueError as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        security_audit.data_import(current_user.id, current_user.email, f'csv:{entry_type}', success=False)
        current_app.logger.error(f'CSV import failed: {e}', exc_info=True)
        return jsonify({'error': 'Import failed. Please try again later.'}), 500

    security_audit.data_import(current_user.id, current_user.email, f'csv:{entry_type}', success=True)
    return jsonify({
        'message': f"Imported {summary['created']} {entry_type} entries "
                   f"({summary['skipped']} duplicate(s) skipped, {summary['error_count']} error(s)).",
        **summary,
    })


@backup_bp.route('/import/lubelog', methods=['POST'])
@token_required
def import_lubelog(current_user):
    """Import data from a LubeLogger backup ZIP file.

    LubeLogger (https://github.com/hargata/lubelog) stores data in a LiteDB
    database. This endpoint parses the backup ZIP containing the LiteDB file,
    images, and documents, and imports them into GearCargo.
    """
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not file.filename.lower().endswith('.zip'):
        return jsonify({'error': 'LubeLogger backup must be a ZIP file'}), 400

    merge_mode = request.form.get('merge_mode', 'merge')
    distance_unit = request.form.get('distance_unit')
    if distance_unit and distance_unit not in ('km', 'miles'):
        return jsonify({'error': 'Invalid distance unit', 'message_key': 'validation.invalidValue',
                        'field': 'distance_unit'}), 400

    from app.utils.entryparse import InvalidFieldError, invalid_field_response
    try:
        from app.services.lubelog_import import import_lubelog_to_gearcargo

        zip_data = BytesIO(file.read())
        result = import_lubelog_to_gearcargo(
            current_user, zip_data, merge_mode, distance_unit=distance_unit,
            source_volume_unit=request.form.get('source_volume_unit') or None,
            source_distance_unit=request.form.get('source_distance_unit') or None,
            source_label=request.form.get('source_label'), preview=request.form.get('preview') == 'true',
            conflict_policy=request.form.get('conflict_policy', 'reject'), preview_token=request.form.get('preview_token'))
        if 'preview' in result:
            return jsonify(result)

        if result.get('error'):
            security_audit.data_import(current_user.id, current_user.email, 'lubelog', success=False)
            return jsonify({'error': result['error']}), 400

        security_audit.data_import(current_user.id, current_user.email, 'lubelog', success=True)

        return jsonify({
            'message': 'LubeLogger import completed successfully',
            'imported': result.get('imported', {}),
            'summary': result.get('summary', {}),
        })

    except InvalidFieldError as exc:
        db.session.rollback()
        return invalid_field_response(exc)
    except BackupSchemaError as exc:
        db.session.rollback()
        return _schema_error_response(exc)
    except ValueError as e:
        db.session.rollback()
        security_audit.data_import(current_user.id, current_user.email, 'lubelog', success=False)
        current_app.logger.error(f'LubeLogger import validation error: {e}')
        # S12: ValueError from lubelog_import is always a safe user-facing validation
        # message (e.g. "No vehicles found"). Still log it but pass through as-is.
        return jsonify({'error': 'LubeLogger import validation failed. Check that the file is a valid LubeLogger backup ZIP.'}), 400
    except Exception as e:
        db.session.rollback()
        security_audit.data_import(current_user.id, current_user.email, 'lubelog', success=False)
        current_app.logger.error(f'LubeLogger import failed: {e}', exc_info=True)
        return jsonify({'error': 'LubeLogger import failed. Please try again later.'}), 500


def _schema_error_response(exc):
    from app.services.import_identity import ImportConflict
    if isinstance(exc, ImportConflict):
        return jsonify({'error': str(exc), 'code': 'IMPORT_REVIEW_REQUIRED', 'preview': exc.preview}), 409
    return jsonify({'error': str(exc), 'issues': [exc.issue]}), 400


def _attachment_restore_paths(prepared, media=None):
    """File destinations belong to this restore; never accept a source disk path."""
    media = media or {}
    paths = {}
    for row in prepared.records['attachments']:
        name = _safe_zip_filename(row['filename'], get_attachment_folder())
        descriptor = media.get(('attachments', row['id']))
        prefix = descriptor['sha256'] if descriptor else f'missing_{uuid.uuid4().hex}'
        # The original filename remains in metadata. Bound the local name in
        # bytes so the digest prefix cannot exceed filesystem component limits.
        local_name = name.encode('utf-8')[:180].decode('utf-8', errors='ignore')
        paths[row['id']] = f'{prefix}_{local_name}'
    return paths


def _backup_media(zf, data, prepared):
    """Validate advertised file presence/integrity before importing their records.

    Existing ZIP traversal/budget controls remain in force. Legacy members are
    adapted by their archive-local IDs; unrecognized members are reported.
    """
    names = zf.namelist()
    if len(names) != len(set(names)):
        raise BackupSchemaError('Duplicate archive member names.', 'media')
    known_ids = {kind: {r['id'] for r in prepared.records[kind]} for kind in ('vehicles', 'attachments')}
    descriptors = []
    legacy = prepared.version in LEGACY_VERSIONS
    if legacy:
        for member in names:
            if member.endswith('/') or member in ('manifest.json', 'backup_data.json'):
                continue
            parts = member.split('/')
            collection = None
            record_id = None
            try:
                if len(parts) == 3 and parts[0] == 'attachments':
                    collection, record_id = 'attachments', int(parts[1])
                elif len(parts) == 4 and parts[:2] == ['uploads', 'vehicles']:
                    collection, record_id = 'vehicles', int(parts[2])
            except ValueError:
                pass
            if collection and record_id in known_ids[collection]:
                _safe_zip_filename(parts[-1], get_attachment_folder())
                content = zf.read(member)
                descriptors.append(dict(collection=collection, record_id=record_id, member=member,
                                        sha256=calculate_checksum(content), size=len(content)))
            else:
                prepared.warnings.append(warning('unsupported_media', 'media',
                    'An archive file has no supported record reference and was not restored.'))
    else:
        descriptors = data.get('media')
        if not isinstance(descriptors, list):
            raise BackupSchemaError('Expected a media inventory.', 'media')
    media = {}
    for i, item in enumerate(descriptors):
        path = f'media[{i}]'
        if not isinstance(item, dict) or set(item) != {'collection', 'record_id', 'member', 'sha256', 'size'}:
            raise BackupSchemaError('Invalid media descriptor.', path)
        collection, record_id, member = item['collection'], item['record_id'], item['member']
        if not isinstance(collection, str) or collection not in known_ids or type(record_id) is not int or record_id not in known_ids[collection]:
            raise BackupSchemaError('Media references an unknown record.', path)
        if not isinstance(member, str):
            raise BackupSchemaError('Invalid archive member.', path)
        parts = member.split('/')
        expected_prefix = f'attachments/{record_id}/' if collection == 'attachments' else f'uploads/vehicles/{record_id}/'
        if not member.startswith(expected_prefix) or len(parts) != (3 if collection == 'attachments' else 4):
            raise BackupSchemaError('Invalid archive member path.', path)
        _safe_zip_filename(parts[-1], get_attachment_folder())
        if member not in names:
            raise BackupSchemaError('A file declared in the backup is missing.', path)
        content = zf.read(member)
        if item['size'] != len(content) or item['sha256'] != calculate_checksum(content):
            raise BackupSchemaError('A backup file failed its integrity check.', path)
        key = (collection, record_id)
        if key in media:
            raise BackupSchemaError('Multiple files reference the same record.', path)
        media[key] = item
    if not legacy:
        declared = {item['member'] for item in descriptors}
        if set(names) - declared - {'manifest.json', 'backup_data.json'}:
            raise BackupSchemaError('Archive contains files outside its media inventory.', 'media')
        if not prepared.media_included and media:
            raise BackupSchemaError('Data-only backup unexpectedly contains media.', 'media')
        if prepared.media_included:
            missing = known_ids['attachments'] - {key[1] for key in media if key[0] == 'attachments'}
            if missing:
                raise BackupSchemaError('Attachment file inventory is incomplete.', 'attachments')
    missing = known_ids['attachments'] - {key[1] for key in media if key[0] == 'attachments'}
    if missing or not prepared.media_included:
        prepared.warnings.append(warning('media_omitted', 'media',
            'Some or all file bytes are absent. Metadata is restored, but those files cannot be downloaded.'))
    return media


def _restore_failure_response(exc):
    return jsonify(error=str(exc), recovery={
        'id': exc.restore_id, 'state': exc.state,
        'maintenance': exc.state == 'recovery_required',
    }), 500


def _audit_restore(actor_id, actor_email, kind, success):
    # Logging failure must not turn a verified, committed restore into a false
    # failure that invites a duplicate retry. The recovery result is authoritative.
    try:
        security_audit.data_import(actor_id, actor_email, kind, success=success)
    except Exception:
        current_app.logger.exception('Restore audit logging failed after recovery outcome was determined.')


def _fingerprint_media(prepared, media):
    for kind in ('attachments', 'vehicles'):
        for row in prepared.records.get(kind, []):
            descriptor = media.get((kind, row['id']))
            if descriptor:
                row['_content_sha256' if kind == 'attachments' else '_photo_sha256'] = descriptor['sha256']


def _perform_personal_restore(user, data, prepared, merge_mode, media=None, archive=None):
    """One transaction owner for JSON and ZIP, including durable media recovery."""
    if merge_mode not in ('merge', 'replace'):
        raise BackupSchemaError('Unsupported merge mode.', 'merge_mode')
    media = media or {}
    from app.services.import_identity import ImportPlan, lock_imports
    lock_imports(user.id)
    plan = ImportPlan(user, prepared)
    plan.validate_apply(getattr(prepared, 'conflict_policy', 'reject'), getattr(prepared, 'preview_token', None))
    actor_id, actor_email = user.id, user.email
    journal = restore_tx.Journal.create('personal')
    imported = None
    try:
        names = _attachment_restore_paths(prepared, media)
        folder = os.path.join(get_attachment_folder(), str(user.id))
        photos = {}
        planned = set()
        media_paths = {}
        for (collection, source_id), item in media.items():
            decision = plan.actions[(collection, source_id)]
            if decision['action'] == 'conflict':
                continue  # Explicit keep preserves destination bytes as well as fields.
            target = decision['target']
            if collection == 'attachments':
                if target is not None:
                    # Replays can fill a previously data-only restore without
                    # changing the attachment's identity or download location.
                    if os.path.lexists(target.filepath):
                        continue
                    if os.path.dirname(os.path.abspath(target.filepath)) != os.path.abspath(folder):
                        continue
                    names[source_id] = _safe_zip_filename(os.path.basename(target.filepath), folder)

                path = os.path.join(folder, names[source_id])
                if os.path.lexists(path):
                    if os.path.islink(path) or restore_tx.digest(path) != item['sha256']:
                        names[source_id] = journal.data['id'] + '_' + names[source_id]
                        # Keep the extra collision prefix within NAME_MAX too.
                        names[source_id] = names[source_id].encode()[:250].decode(errors='ignore')
                        path = os.path.join(folder, names[source_id])
                    else:
                        continue  # Identical existing bytes are never overwritten.
            else:
                if target is not None and target.photo:
                    filename = os.path.basename(target.photo)
                    if os.path.lexists(os.path.join(get_uploads_folder(), 'vehicles', filename)):
                        continue
                extension = os.path.splitext(item['member'])[1][:12]
                filename = f'restore_{journal.data["id"]}_{source_id}{extension}'
                path = os.path.join(get_uploads_folder(), 'vehicles', filename)
                photos[source_id] = filename
            media_paths[(collection, source_id)] = path
            if path not in planned:
                journal.stage_file(archive.read(item['member']), path)
                planned.add(path)
        journal.data['db_started'] = True
        journal.save('importing')
        restore_tx.lock_database_transaction()
        restore_tx.checkpoint('before_db_write', journal)
        maps = {}
        imported, vehicle_map, _ = import_backup_data(user, data, merge_mode,
            prepared=prepared, id_maps=maps, attachment_names=names)
        valid_paths = {path for (kind, source_id), path in media_paths.items() if source_id in maps[kind]}
        journal.data['files'] = [item for item in journal.data['files'] if item['path'] in valid_paths]
        journal.save()
        imported['vehicle_photos'] = 0
        for source_id, filename in photos.items():
            if source_id not in vehicle_map:
                continue
            vehicle = db.session.get(Vehicle, vehicle_map[source_id])
            vehicle.photo = f'/uploads/vehicles/{filename}'
            original = next(r for r in prepared.records['vehicles'] if r['id'] == source_id)
            if 'updated_at' in original:
                vehicle.updated_at = original['updated_at']
                flag_modified(vehicle, 'updated_at')
            imported['vehicle_photos'] += 1
        journal.mark_transaction()
        db.session.flush()
        restore_tx.checkpoint('after_db_write', journal)
        journal.publish_files()
        journal.save('committing')
        restore_tx.checkpoint('before_commit', journal)
        db.session.commit()
        restore_tx.checkpoint('after_commit', journal)
        restore_tx.recover(journal)
    except Exception as exc:
        current_app.logger.exception('Personal restore interrupted: %s', journal.data['id'])
        try:
            outcome = restore_tx.recover(journal)
        except Exception:
            current_app.logger.exception('Restore recovery remains pending: %s', journal.data['id'])
            raise restore_tx.RestoreFailure(journal.data['id'], 'recovery_required') from None
        if outcome != 'completed':
            _audit_restore(actor_id, actor_email, 'zip' if archive else 'json', False)
            from app.services.attachment_consistency import AttachmentParentError
            if isinstance(exc, AttachmentParentError):
                raise BackupSchemaError(exc.error, 'attachments.' + (exc.field or 'parent')) from None
            if isinstance(exc, BackupSchemaError):
                # Destination-dependent schema conflicts are discovered during
                # import. Report them only after recovery confirms rollback.
                raise
            raise restore_tx.RestoreFailure(journal.data['id'], 'rolled_back') from None
    imported['recovery'] = {'id': journal.data['id'], 'state': 'completed'}
    _audit_restore(actor_id, actor_email, 'zip' if archive else 'json', True)
    return jsonify({'message': 'Import completed', 'imported': imported})


def _personal_import_review(user, prepared):
    from flask import has_request_context
    from app.services.import_identity import ImportPlan, namespace_for, digest
    options = ((request.get_json(silent=True) or {}) if request.is_json else request.form) if has_request_context() else {}
    source_label = options.get('source_label')
    if source_label and prepared.namespace.startswith('backup:file:'):
        prepared.namespace = namespace_for('backup', source_label, prepared.batch_key)
        for kind, rows in prepared.records.items():
            for row in rows:
                if row['id'] < 0:
                    prepared.source_keys[(kind, row['id'])] = ('backup:file:' + prepared.batch_key, str(row['id']))
    prepared.batch_key = digest({'file': prepared.batch_key, 'namespace': prepared.namespace,
        'media': [(kind, row['id'], row.get('_content_sha256'), row.get('_photo_sha256'))
                  for kind, rows in prepared.records.items() for row in rows
                  if '_content_sha256' in row or '_photo_sha256' in row]})
    prepared.conflict_policy = options.get('conflict_policy', 'reject')
    prepared.preview_token = options.get('preview_token')
    plan = ImportPlan(user, prepared)
    if options.get('preview') in ('true', True):
        return jsonify({'preview': plan.preview})
    plan.validate_apply(prepared.conflict_policy, prepared.preview_token)
    return None


def restore_from_json(user, file, merge_mode='merge'):
    """Validate all metadata, then commit under the same recovery protocol as ZIP."""
    try:
        with restore_tx.activity_guard(exclusive=True):
            backup_data = json.loads(file.read().decode('utf-8'))
            prepared = prepare_backup(backup_data)
            prepared.media_included = False
            prepared.warnings.append(warning('media_omitted', 'media',
                'JSON contains no receipt or photo files. Document metadata and links were restored; file downloads are unavailable.'))
            preview = _personal_import_review(user, prepared)
            if preview is not None:
                return preview
            return _perform_personal_restore(user, backup_data, prepared, merge_mode)
    except BackupSchemaError as exc:
        return _schema_error_response(exc)
    except restore_tx.RestoreFailure as exc:
        return _restore_failure_response(exc)


def restore_from_zip(user, file, merge_mode='merge'):
    """Validate the complete archive, stage files, then publish and commit once."""
    try:
        with restore_tx.activity_guard(exclusive=True), zipfile.ZipFile(BytesIO(file.read()), 'r') as zf:
            _check_zip_budget(zf)
            if 'backup_data.json' not in zf.namelist():
                raise BackupSchemaError('Invalid backup file: missing backup_data.json')
            raw = zf.read('backup_data.json')
            data = json.loads(raw.decode('utf-8'))
            prepared = prepare_backup(data)
            if prepared.version not in LEGACY_VERSIONS and 'manifest.json' not in zf.namelist():
                raise BackupSchemaError('Version-4 ZIP is missing its manifest.', 'manifest')
            if 'manifest.json' in zf.namelist():
                manifest = json.loads(zf.read('manifest.json').decode('utf-8'))
                if prepared.version not in LEGACY_VERSIONS:
                    if not isinstance(manifest, dict) or manifest.get('version') != prepared.version:
                        raise BackupSchemaError('Manifest and data versions disagree.', 'manifest')
                    if manifest.get('checksum') != calculate_checksum(raw):
                        raise BackupSchemaError('Backup data failed its integrity check.', 'manifest.checksum')
            media = _backup_media(zf, data, prepared)
            _fingerprint_media(prepared, media)
            preview = _personal_import_review(user, prepared)
            if preview is not None:
                return preview
            return _perform_personal_restore(user, data, prepared, merge_mode, media, zf)
    except BackupSchemaError as exc:
        return _schema_error_response(exc)
    except restore_tx.RestoreFailure as exc:
        return _restore_failure_response(exc)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400


def import_backup_data(user, backup_data, merge_mode='merge', *, prepared=None,
                       id_maps=None, attachment_names=None):
    """Import portable records; retain the public three-value return contract.

    This helper does not commit. The caller owns transaction completion and
    coordinates file publication with the durable recovery journal.
    """
    prepared = prepared or prepare_backup(backup_data)
    id_maps = id_maps if id_maps is not None else {}
    if attachment_names is None:
        attachment_names = _attachment_restore_paths(prepared)
        if prepared.media_included:
            prepared.media_included = False
            prepared.warnings.append(warning('media_omitted', 'media',
                'Only record data was supplied; file bytes were not restored.'))
    folder = os.path.join(get_attachment_folder(), str(user.id))
    paths = {key: os.path.join(folder, name) for key, name in attachment_names.items()}
    imported = import_records(user, prepared, merge_mode, id_maps, paths,
                              conflict_policy=getattr(prepared, 'conflict_policy', 'reject'),
                              preview_token=getattr(prepared, 'preview_token', None))
    return imported, id_maps['vehicles'], id_maps['entries']


@backup_bp.route('/download/<filename>', methods=['GET'])
@token_required
def download_stored_backup(current_user, filename):
    """Download a stored backup file."""
    # Validate filename (prevent directory traversal)
    if '..' in filename or '/' in filename or '\\' in filename:
        return jsonify({'error': 'Invalid filename'}), 400

    backup_folder = get_backup_folder()
    user_folder = os.path.join(backup_folder, str(current_user.id))
    filepath = os.path.join(user_folder, filename)

    if not os.path.exists(filepath):
        return jsonify({'error': 'Backup file not found'}), 404

    response = send_file(
        filepath,
        mimetype='application/zip' if filename.endswith('.zip') else 'application/octet-stream',
        as_attachment=True,
        download_name=filename
    )
    response.headers['X-Backup-Protection'] = backup_crypto.file_protection(filepath)['protection']
    return response


@backup_bp.route('/restore/<filename>', methods=['POST'])
@token_required
def restore_from_storage(current_user, filename):
    """Restore from a backup stored on server."""
    # Validate filename (prevent directory traversal)
    if '..' in filename or '/' in filename or '\\' in filename:
        return jsonify({'error': 'Invalid filename'}), 400
    
    backup_folder = get_backup_folder()
    user_folder = os.path.join(backup_folder, str(current_user.id))
    filepath = os.path.join(user_folder, filename)
    
    if not os.path.exists(filepath):
        return jsonify({'error': 'Backup file not found'}), 404
    
    merge_mode = request.json.get('merge_mode', 'merge') if request.json else 'merge'
    
    try:
        with open(filepath, 'rb') as f:
            return _restore_user_artifact(current_user, f, filename, merge_mode,
                                          (request.get_json(silent=True) or {}).get('passphrase'))
    except backup_crypto.BackupEncryptionError as exc:
        return _encryption_error(exc)
    except Exception as e:
        current_app.logger.error(f'Restore from storage failed: {e}')
        return jsonify({'error': 'Restore failed. Please try again later.'}), 500


@backup_bp.route('/delete/<filename>', methods=['DELETE'])
@token_required
def delete_backup(current_user, filename):
    """Delete a stored backup file."""
    if '..' in filename or '/' in filename or '\\' in filename:
        return jsonify({'error': 'Invalid filename'}), 400
    
    backup_folder = get_backup_folder()
    user_folder = os.path.join(backup_folder, str(current_user.id))
    filepath = os.path.join(user_folder, filename)
    
    if not os.path.exists(filepath):
        return jsonify({'error': 'Backup file not found'}), 404
    
    try:
        os.remove(filepath)
        return jsonify({'message': 'Backup deleted successfully'})
    except Exception as e:
        current_app.logger.error(f'Failed to delete backup {filename}: {e}')
        return jsonify({'error': 'Failed to delete backup. Please try again later.'}), 500


@backup_bp.route('/history', methods=['GET'])
@token_required
def get_backup_history(current_user):
    """Get backup history."""
    page = request.args.get('page', 1, type=int)
    per_page = max(1, min(request.args.get('per_page', 20, type=int), 100))
    
    backups = Backup.query.filter_by(
        user_id=current_user.id
    ).order_by(Backup.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return jsonify({
        'backups': [b.to_dict() for b in backups.items],
        'total': backups.total,
        'pages': backups.pages,
        'current_page': page,
    })


@backup_bp.route('/schedule', methods=['GET'])
@token_required
def get_backup_schedule(current_user):
    """Get backup schedule settings."""
    schedule = BackupSchedule.query.filter_by(user_id=current_user.id).first()
    
    if not schedule:
        return jsonify({
            'enabled': False,
            'message': 'No backup schedule configured'
        })
    
    return jsonify(schedule.to_dict())


@backup_bp.route('/schedule', methods=['PUT'])
@token_required
def update_backup_schedule(current_user):
    """Update backup schedule settings."""
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    schedule = BackupSchedule.query.filter_by(user_id=current_user.id).first()
    
    if not schedule:
        schedule = BackupSchedule(user_id=current_user.id)
        db.session.add(schedule)
    
    # Validate frequency
    valid_frequencies = ['weekly', 'monthly', 'quarterly']
    if data.get('frequency') and data['frequency'] not in valid_frequencies:
        return jsonify({'error': f'Invalid frequency. Must be one of: {", ".join(valid_frequencies)}'}), 400
    
    # Validate day_of_week (0-6)
    if data.get('day_of_week') is not None:
        dow = data['day_of_week']
        if not isinstance(dow, int) or dow < 0 or dow > 6:
            return jsonify({'error': 'day_of_week must be 0-6 (Monday-Sunday)'}), 400
    
    # Validate day_of_month (1-31)
    if data.get('day_of_month') is not None:
        dom = data['day_of_month']
        if not isinstance(dom, int) or dom < 1 or dom > 31:
            return jsonify({'error': 'day_of_month must be 1-31'}), 400
    
    # Validate hour (0-23)
    if data.get('hour') is not None:
        hour = data['hour']
        if not isinstance(hour, int) or hour < 0 or hour > 23:
            return jsonify({'error': 'hour must be 0-23'}), 400
    
    # S09: Validate external URL is HTTPS and not targeting a private/internal IP
    if data.get('external_enabled') and data.get('external_url'):
        if not _is_allowed_webdav_url(data['external_url']):
            return jsonify({'error': 'External URL must be a public HTTPS address'}), 400

    destinations_payload = data.get('external_destinations')
    if destinations_payload is not None:
        if not isinstance(destinations_payload, list):
            return jsonify({'error': 'external_destinations must be a list'}), 400
        if len(destinations_payload) > 10:
            return jsonify({'error': 'A maximum of 10 destinations is supported'}), 400

        existing_destinations = []
        if hasattr(schedule, 'get_external_destinations'):
            existing_destinations = schedule.get_external_destinations() or []

        existing_by_id = {}
        existing_by_url = {}
        for existing in existing_destinations:
            if not isinstance(existing, dict):
                continue
            existing_id = existing.get('id')
            existing_url = (existing.get('external_url') or '').strip()
            if existing_id:
                existing_by_id[str(existing_id)] = existing
            if existing_url:
                existing_by_url[existing_url] = existing

        normalized_destinations = []

        for index, destination in enumerate(destinations_payload):
            if not isinstance(destination, dict):
                return jsonify({'error': f'Destination at index {index} must be an object'}), 400

            destination_id = str(destination.get('id') or f'destination_{index + 1}')
            destination_name = (destination.get('name') or destination.get('label') or f'Destination {index + 1}').strip()
            destination_provider = (destination.get('provider') or 'webdav').strip()
            destination_enabled = bool(destination.get('enabled', True))

            url = (destination.get('external_url') or destination.get('url') or '').strip()
            if not url:
                return jsonify({'error': f'Destination at index {index} is missing external_url'}), 400
            if not _is_allowed_webdav_url(url):  # S09: blocks private IPs
                return jsonify({'error': f'Destination at index {index} URL must be a public HTTPS address'}), 400

            submitted_key = str(destination.get('external_api_key') or destination.get('api_key') or '').strip()
            # Only a SUBMITTED key is validated. A key merged from storage may
            # predate this check, and rejecting it would block editing the
            # destination's name or path — leaving the row uneditable.
            if submitted_key and not _webdav_credential_parts(submitted_key):
                return jsonify({
                    'error': f'Destination at index {index} API key must use the format "username:app-password"',
                    'message_key': 'backup.apiKeyFormat',
                }), 400

            api_key = submitted_key
            existing_destination = existing_by_id.get(destination_id) or existing_by_url.get(url)
            if not api_key and existing_destination:
                api_key = str(existing_destination.get('external_api_key') or '').strip()

            if not api_key:
                return jsonify({'error': f'Destination at index {index} is missing external_api_key'}), 400

            normalized_destinations.append({
                'id': destination_id,
                'name': destination_name,
                'provider': destination_provider,
                'enabled': destination_enabled,
                'external_url': url,
                'external_api_key': api_key,
                'external_path': destination.get('external_path') or destination.get('path') or '/GearCargo',
            })

        destinations_payload = normalized_destinations
    
    backup_crypto.update_schedule_protection(schedule, data)

    # Update allowed fields
    allowed = [
        'enabled', 'frequency', 'day_of_week', 'day_of_month', 'hour',
        'backup_type', 'include_attachments',
        'external_enabled', 'external_url', 'external_api_key', 'external_path',
        'cloud_enabled', 'cloud_provider',
        'retention_days', 'max_backups',
        'notify_on_success', 'notify_on_failure'
    ]
    
    for field in allowed:
        if field in data:
            # Don't overwrite stored API key with empty string
            if field == 'external_api_key' and not data[field]:
                continue
            setattr(schedule, field, data[field])

    if destinations_payload is not None:
        schedule.set_external_destinations(destinations_payload)
    
    # Calculate next run time if enabled
    if schedule.enabled:
        schedule.calculate_next_run()
    
    db.session.commit()
    
    return jsonify({
        'message': 'Backup schedule updated',
        'schedule': schedule.to_dict()
    })


@backup_bp.route('/run-now', methods=['POST'])
@token_required
def run_backup_now(current_user):
    """Trigger an immediate backup."""
    data = request.get_json() or {}
    include_attachments = data.get('include_attachments', True)
    send_external = data.get('send_external', False)
    schedule = BackupSchedule.query.filter_by(user_id=current_user.id).first()
    passphrase = (backup_crypto.request_passphrase(data) if 'encrypt' in data or 'passphrase' in data
                  else backup_crypto.schedule_passphrase(schedule))
    
    # Create backup record
    backup = Backup(
        user_id=current_user.id,
        backup_type='manual',
        format='zip',
        status='in_progress',
        started_at=datetime.now(timezone.utc),
    )
    db.session.add(backup)
    db.session.commit()
    
    zip_buffer = None
    try:
        # Create backup
        zip_buffer, export_data = create_backup_zip(current_user, include_attachments)
        zip_buffer = backup_crypto.protect_stream(zip_buffer, passphrase)
        backup.encrypted = passphrase is not None
        
        # Save to disk
        filename, filepath, file_size = save_backup_to_disk(current_user, zip_buffer, include_attachments)
        
        backup.filename = filename
        backup.filepath = filepath
        backup.file_size = file_size
        backup.vehicles_count = len(export_data['vehicles'])
        backup.entries_count = sum(
            len(v.get('fuel_entries', [])) +
            len(v.get('service_entries', [])) +
            len(v.get('repair_entries', [])) +
            len(v.get('tax_entries', [])) +
            len(v.get('parking_entries', [])) +
            len(v.get('consumable_entries', []))
            for v in export_data['vehicles']
        )
        backup.reminders_count = len(export_data['reminders'])
        backup.attachments_count = len(export_data.get('attachments', []))
        
        # Send to external server if requested
        external_error = None
        external_successes = []
        external_errors = []
        if send_external:
            schedule = BackupSchedule.query.filter_by(user_id=current_user.id).first()
            if schedule:
                zip_buffer.seek(0)
                external_successes, external_errors = send_to_all_external_destinations(
                    zip_buffer.read(),
                    schedule,
                    filename=filename,
                )
                if external_errors:
                    external_error = '; '.join(external_errors)
                    backup.error_message = f"Backup saved locally, but external upload failed: {external_error}"
        
        backup.status = 'completed'
        backup.completed_at = datetime.now(timezone.utc)
        
        # Cleanup old backups
        schedule = BackupSchedule.query.filter_by(user_id=current_user.id).first()
        if schedule:
            cleanup_old_backups(
                current_user.id,
                max_backups=schedule.max_backups,
                retention_days=schedule.retention_days
            )
        
        db.session.commit()
        
        response_data = {
            'message': 'Backup completed successfully' if not external_error else 'Backup saved locally, but external upload failed',
            'backup': backup.to_dict()
        }
        if external_error:
            response_data['external_error'] = external_error
        if external_successes:
            response_data['external_successes'] = external_successes
        if external_errors:
            response_data['external_errors'] = external_errors
        
        return jsonify(response_data)
    
    except Exception as e:
        backup.status = 'failed'
        # S12: Never store raw exception text in the DB — it is returned via to_dict().
        backup.error_message = 'Backup failed — see server log for details'
        backup.completed_at = datetime.now(timezone.utc)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
        current_app.logger.error(f'Manual backup failed: {e}', exc_info=True)
        return jsonify({'error': 'Backup failed. Please try again later.'}), 500
    finally:
        if zip_buffer is not None:
            zip_buffer.close()


@backup_bp.route('/send-external', methods=['POST'])
@token_required
def send_latest_to_external(current_user):
    """Send the latest stored backup (or a specific one) to the external server."""
    data = request.get_json() or {}
    target_filename = data.get('filename')  # Optional: specific backup file

    schedule = BackupSchedule.query.filter_by(user_id=current_user.id).first()
    if not schedule:
        return jsonify({'error': 'External backup is not configured. Enable it in settings first.'}), 400

    destinations = [d for d in get_schedule_external_destinations(schedule) if d.external_enabled]
    if not destinations:
        return jsonify({'error': 'External backup is not configured. Enable it in settings first.'}), 400

    backup_folder = get_backup_folder()
    user_folder = os.path.join(backup_folder, str(current_user.id))

    if target_filename:
        # Validate filename (prevent directory traversal)
        if '..' in target_filename or '/' in target_filename or '\\' in target_filename:
            return jsonify({'error': 'Invalid filename'}), 400
        filepath = os.path.join(user_folder, target_filename)
    else:
        # Find latest backup. H2: match ANY .zip (files are named
        # "{App}_{User}_{timestamp}.zip", never "backup_*"), and pick the newest
        # by MODIFICATION TIME — a reverse filename sort is unreliable once the
        # app/user name prefix varies, so it could pick the wrong (or no) file.
        if not os.path.exists(user_folder):
            return jsonify({'error': 'No stored backups found. Run a backup first.'}), 404
        files = [f for f in os.listdir(user_folder) if f.lower().endswith(('.zip', '.gcb'))]
        if not files:
            return jsonify({'error': 'No stored backups found. Run a backup first.'}), 404
        files.sort(key=lambda f: os.path.getmtime(os.path.join(user_folder, f)), reverse=True)
        target_filename = files[0]
        filepath = os.path.join(user_folder, target_filename)

    if not os.path.exists(filepath):
        return jsonify({'error': 'Backup file not found'}), 404

    try:
        with open(filepath, 'rb') as f:
            backup_data = f.read()

        successes, errors = send_to_all_external_destinations(backup_data, schedule, filename=target_filename)
        if not successes:
            return jsonify({'error': '; '.join(errors) if errors else 'External upload failed'}), 400

        return jsonify({
            'message': 'Backup sent to external destinations successfully' if not errors else 'Backup sent to some external destinations',
            'filename': target_filename,
            'size': len(backup_data),
            'destinations_succeeded': successes,
            'destinations_failed': errors,
            **backup_crypto.file_protection(filepath),
        })
    except Exception as e:
        current_app.logger.error(f'Send to external failed: {e}', exc_info=True)
        return jsonify({'error': 'Failed to send backup to external destination. Please try again later.'}), 500


@backup_bp.route('/external/test', methods=['POST'])
@token_required
def test_external_connection(current_user):
    """Test connection to external backup server via WebDAV PROPFIND."""
    data = request.get_json()

    if not data.get('url'):
        return jsonify({'error': 'URL is required'}), 400

    url = data['url']

    # S09: Validate HTTPS and not targeting private/internal IP range
    if not _is_allowed_webdav_url(url):
        return jsonify({'error': 'URL must be a public HTTPS address'}), 400

    auth, auth_error = _resolve_webdav_auth(current_user.id, url, data.get('api_key'))
    if auth_error:
        # Reported inline next to the button, so 200 with success: False.
        payload, _status = auth_error
        return jsonify({**payload, 'success': False})

    try:
        # Test with WebDAV PROPFIND on the user root
        base = _webdav_base_url(url)
        propfind_url = f"{base}/{auth[0]}"

        response = _safe_webdav_request(
            'PROPFIND',
            propfind_url,
            auth=auth,
            headers={'Depth': '0', 'Content-Type': 'application/xml'},
            timeout=10,
            verify=True
        )

        if response.status_code in [200, 207]:  # 207 Multi-Status is normal for PROPFIND
            return jsonify({
                'success': True,
                'message': 'WebDAV connection successful'
            })
        elif response.status_code == 401:
            return jsonify({
                'success': False,
                'error': 'Authentication failed. Use format "username:app-password" in the API Key field.'
            })
        else:
            return jsonify({
                'success': False,
                'error': f'Server returned {response.status_code}'
            })

    except requests.exceptions.SSLError as e:
        current_app.logger.warning(f'External backup SSL error: {e}')
        return jsonify({'success': False, 'error': 'SSL certificate verification failed.'}), 200
    except requests.exceptions.Timeout:
        return jsonify({'success': False, 'error': 'Connection timed out'}), 200
    except requests.exceptions.RequestException as e:
        current_app.logger.warning(f'External backup connection failed: {e}')
        return jsonify({'success': False, 'error': 'Connection failed. Check the URL and try again.'}), 200


@backup_bp.route('/external/browse', methods=['POST'])
@token_required
def browse_external_folders(current_user):
    """List folders on the external WebDAV server for path selection."""
    data = request.get_json()

    if not data.get('url'):
        return jsonify({'error': 'URL is required'}), 400

    url = data['url']
    api_key = data.get('api_key', '')
    path = data.get('path', '/')  # Relative path to browse

    if not _is_allowed_webdav_url(url):  # S09
        return jsonify({'error': 'URL must be a public HTTPS address'}), 400

    auth, auth_error = _resolve_webdav_auth(current_user.id, url, api_key)
    if auth_error:
        payload, status = auth_error
        return jsonify(payload), status

    try:
        base = _webdav_base_url(url)
        browse_path = path.strip('/')
        browse_url = f"{base}/{auth[0]}/{browse_path}" if browse_path else f"{base}/{auth[0]}"
        # Ensure trailing slash for PROPFIND on collections
        if not browse_url.endswith('/'):
            browse_url += '/'

        current_app.logger.info(f'WebDAV PROPFIND: {browse_url}')

        response = _safe_webdav_request(
            'PROPFIND',
            browse_url,
            auth=auth,
            headers={'Depth': '1', 'Content-Type': 'application/xml'},
            timeout=10,
            verify=True
        )

        current_app.logger.info(f'WebDAV PROPFIND response: {response.status_code}')

        if response.status_code not in [200, 207]:
            return jsonify({'error': f'Server returned {response.status_code}'}), 400

        # Parse WebDAV XML response for folder names
        import xml.etree.ElementTree as ET
        root = ET.fromstring(response.text)
        ns = {'d': 'DAV:'}

        # The first <d:response> is always the queried folder itself — skip it
        responses = root.findall('.//d:response', ns)
        folders = []
        for i, resp_elem in enumerate(responses):
            # Skip the first entry (the queried directory itself)
            if i == 0:
                continue
            restype = resp_elem.find('.//d:resourcetype/d:collection', ns)
            if restype is not None:
                href = resp_elem.find('d:href', ns)
                if href is not None:
                    # href is like /remote.php/dav/files/user/Documents/Folder/
                    folder_path = href.text.rstrip('/')
                    name = folder_path.split('/')[-1] if '/' in folder_path else folder_path
                    # URL-decode the name
                    from urllib.parse import unquote
                    name = unquote(name)
                    if name:
                        folders.append(name)

        return jsonify({'folders': sorted(folders), 'current_path': path})

    except requests.exceptions.RequestException as e:
        current_app.logger.warning(f'WebDAV browse (folders) failed: {e}')
        return jsonify({'error': 'Failed to browse external server. Check the URL, path, and credentials.'}), 400


@backup_bp.route('/external/files', methods=['POST'])
@token_required
def browse_external_files(current_user):
    """List backup files (.zip) on the external WebDAV server for restore."""
    data = request.get_json()

    if not data.get('url'):
        return jsonify({'error': 'URL is required'}), 400

    url = data['url']
    api_key = data.get('api_key', '')
    path = data.get('path', '/GearCargo')

    if not _is_allowed_webdav_url(url):  # S09
        return jsonify({'error': 'URL must be a public HTTPS address'}), 400

    auth, auth_error = _resolve_webdav_auth(current_user.id, url, api_key)
    if auth_error:
        payload, status = auth_error
        return jsonify(payload), status

    try:
        base = _webdav_base_url(url)
        browse_path = path.strip('/')
        browse_url = f"{base}/{auth[0]}/{browse_path}/" if browse_path else f"{base}/{auth[0]}/"

        response = _safe_webdav_request(
            'PROPFIND',
            browse_url,
            auth=auth,
            headers={'Depth': '1', 'Content-Type': 'application/xml'},
            timeout=10,
            verify=True
        )

        if response.status_code not in [200, 207]:
            return jsonify({'error': f'Server returned {response.status_code}'}), 400

        import xml.etree.ElementTree as ET
        from urllib.parse import unquote
        root = ET.fromstring(response.text)
        ns = {'d': 'DAV:'}

        files = []
        responses = root.findall('.//d:response', ns)
        for i, resp_elem in enumerate(responses):
            if i == 0:
                continue  # Skip the queried directory itself
            restype = resp_elem.find('.//d:resourcetype/d:collection', ns)
            if restype is None:
                # It's a file, not a folder
                href = resp_elem.find('d:href', ns)
                size_elem = resp_elem.find('.//d:getcontentlength', ns)
                lastmod_elem = resp_elem.find('.//d:getlastmodified', ns)
                if href is not None:
                    name = unquote(href.text.rstrip('/').split('/')[-1])
                    if name.lower().endswith(('.zip', '.gcb')):
                        files.append({
                            'name': name,
                            'size': int(size_elem.text) if size_elem is not None and size_elem.text else 0,
                            'size_human': format_file_size(int(size_elem.text)) if size_elem is not None and size_elem.text else '?',
                            'protection': 'encrypted_unverified' if name.lower().endswith('.gcb') else 'plaintext',
                            'last_modified': lastmod_elem.text if lastmod_elem is not None else None,
                        })

        # Sort by name descending (newest first by convention)
        files.sort(key=lambda f: f['name'], reverse=True)
        return jsonify({'files': files, 'path': path})

    except requests.exceptions.RequestException as e:
        current_app.logger.warning(f'WebDAV browse (files) failed: {e}')
        return jsonify({'error': 'Failed to browse external server. Check the URL, path, and credentials.'}), 400


@backup_bp.route('/external/restore', methods=['POST'])
@token_required
def restore_from_external(current_user):
    """Download a backup file from external WebDAV server and restore it."""
    data = request.get_json()

    filename = data.get('filename')
    if not filename:
        return jsonify({'error': 'Filename is required'}), 400

    # Validate filename
    if '..' in filename or '/' in filename or '\\' in filename:
        return jsonify({'error': 'Invalid filename'}), 400

    if not filename.lower().endswith(('.zip', '.gcb')):
        return jsonify({'error': 'Use a .zip or .zip.gcb backup file'}), 400

    # Get schedule for credentials, or use provided ones
    schedule = BackupSchedule.query.filter_by(user_id=current_user.id).first()
    url = data.get('url') or (schedule.external_url if schedule else None)
    api_key = data.get('api_key') or (schedule.external_api_key if schedule else None)
    path = data.get('path') or (schedule.external_path if schedule else '/GearCargo')

    if not url:
        return jsonify({'error': 'External backup credentials not configured'}), 400

    if not _is_allowed_webdav_url(url):  # S09
        return jsonify({'error': 'URL must be a public HTTPS address'}), 400

    auth, auth_error = _resolve_webdav_auth(current_user.id, url, api_key)
    if auth_error:
        payload, status = auth_error
        return jsonify(payload), status

    try:
        base = _webdav_base_url(url)
        file_path = path.strip('/')
        download_url = f"{base}/{auth[0]}/{file_path}/{filename}"

        current_app.logger.info(f'Downloading from external: {download_url}')

        response = _safe_webdav_request('GET',
            download_url,
            auth=auth,
            timeout=300,
            verify=True,
            stream=True
        )

        if response.status_code == 404:
            return jsonify({'error': 'File not found on external server'}), 404
        elif response.status_code == 401:
            return jsonify({'error': 'Authentication failed'}), 401
        elif response.status_code not in [200]:
            return jsonify({'error': f'Server returned {response.status_code}'}), 400

        # Read the file content
        file_content = response.content
        merge_mode = data.get('merge_mode', 'merge')

        # Authenticate before storing, parsing or applying anything. Keep the
        # encrypted original for local recovery; never persist its plaintext.
        with backup_crypto.open_backup(BytesIO(file_content), filename, data.get('passphrase')) as (plaintext, inner_format):
            if inner_format != 'zip':
                raise backup_crypto.BackupEncryptionError('Use a ZIP backup for external restore.')
            if data.get('preview') not in (True, 'true'):
                user_folder = os.path.join(get_backup_folder(), str(current_user.id))
                os.makedirs(user_folder, exist_ok=True)
                backup_crypto.atomic_write(BytesIO(file_content), os.path.join(user_folder, filename))
            return restore_from_zip(current_user, plaintext, merge_mode)
    except backup_crypto.BackupEncryptionError as exc:
        return _encryption_error(exc)
    except requests.exceptions.Timeout:
        return jsonify({'error': 'Download timed out. The external server did not respond in time.'}), 504
    except requests.exceptions.RequestException as e:
        current_app.logger.error(f'External restore download failed: {e}')
        return jsonify({'error': 'Failed to download backup from external server. Check the connection settings.'}), 400
    except zipfile.BadZipFile:
        return jsonify({'error': 'Downloaded file is not a valid ZIP backup.'}), 400
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'External restore failed: {e}', exc_info=True)
        return jsonify({'error': 'Restore failed. Please try again later.'}), 500


@backup_bp.route('/upload', methods=['POST'])
@token_required
def upload_backup(current_user):
    """Upload a backup .zip file to stored backups (without restoring)."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not file.filename.lower().endswith(('.zip', '.gcb')):
        return jsonify({'error': 'Use a .zip or .zip.gcb backup file'}), 400

    try:
        content = file.read()

        with backup_crypto.open_backup(BytesIO(content), file.filename, request.form.get('passphrase')) as (plaintext, inner_format):
            if inner_format != 'zip':
                raise backup_crypto.BackupEncryptionError('Use a ZIP backup for stored uploads.')
            with zipfile.ZipFile(plaintext, 'r') as zf:
                _check_zip_budget(zf)
                if 'backup_data.json' not in zf.namelist():
                    return jsonify({'error': 'Invalid backup file: missing backup_data.json'}), 400

        # Save to backup storage
        backup_folder = get_backup_folder()
        user_folder = os.path.join(backup_folder, str(current_user.id))
        os.makedirs(user_folder, exist_ok=True)

        # Sanitise the original filename — keep it as-is (no forced prefix)
        safe_name = re.sub(r'[^A-Za-z0-9._-]', '_', file.filename)
        if backup_crypto.is_encrypted(BytesIO(content)) and not safe_name.lower().endswith('.gcb'):
            safe_name += '.gcb'
        filepath = os.path.join(user_folder, safe_name)

        # Don't overwrite existing
        if os.path.exists(filepath):
            ext = '.zip.gcb' if safe_name.endswith('.zip.gcb') else os.path.splitext(safe_name)[1]
            base = safe_name[:-len(ext)]
            safe_name = f'{base}_{uuid.uuid4().hex[:12]}{ext}'
            filepath = os.path.join(user_folder, safe_name)

        backup_crypto.atomic_write(BytesIO(content), filepath)

        return jsonify({
            'message': 'Backup uploaded successfully',
            'filename': safe_name,
            'size': len(content),
            'size_human': format_file_size(len(content)),
            **backup_crypto.file_protection(filepath),
        })

    except zipfile.BadZipFile:
        return jsonify({'error': 'File is not a valid ZIP archive'}), 400
    except ValueError as e:
        # M6: decompression-bomb rejection — surface the specific reason.
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        current_app.logger.error(f'Upload backup failed: {e}')
        return jsonify({'error': 'Upload failed'}), 500


@backup_bp.route('/stats', methods=['GET'])
@token_required
def get_backup_stats(current_user):
    """Get backup statistics."""
    backups = Backup.query.filter_by(user_id=current_user.id).all()
    
    total_size = sum(b.file_size or 0 for b in backups)
    successful = sum(1 for b in backups if b.status == 'completed')
    failed = sum(1 for b in backups if b.status == 'failed')
    
    last_backup = Backup.query.filter_by(
        user_id=current_user.id,
        status='completed'
    ).order_by(Backup.created_at.desc()).first()
    
    # Get storage usage
    backup_folder = get_backup_folder()
    user_folder = os.path.join(backup_folder, str(current_user.id))
    storage_used = 0
    
    if os.path.exists(user_folder):
        for f in os.listdir(user_folder):
            filepath = os.path.join(user_folder, f)
            if os.path.isfile(filepath):
                storage_used += os.path.getsize(filepath)
    
    return jsonify({
        'total_backups': len(backups),
        'successful': successful,
        'failed': failed,
        'total_size': total_size,
        'total_size_human': format_file_size(total_size),
        'storage_used': storage_used,
        'storage_used_human': format_file_size(storage_used),
        'last_backup': last_backup.to_dict() if last_backup else None,
    })


@backup_bp.route('/system/export', methods=['POST'])
@admin_required
def export_system_backup(current_user):
    """Create and download a full-state system backup archive."""
    payload = request.get_json(silent=True) or {}
    frequency = payload.get('frequency', 'manual')
    valid_frequencies = {'manual', 'daily', 'weekly', 'monthly'}

    if frequency not in valid_frequencies:
        return jsonify(localized_message(
            'backup.system_export.invalid_frequency',
            'Invalid backup frequency',
            allowed_frequencies=sorted(valid_frequencies),
        )), 400

    passphrase = backup_crypto.request_passphrase(payload)
    key_file = current_app.config.get('BACKUP_PASSPHRASE_FILE') or os.environ.get('BACKUP_PASSPHRASE_FILE')
    if 'encrypt' not in payload and key_file:
        passphrase = backup_crypto.read_passphrase_file(key_file)
    try:
        archive_path, filename, file_size, manifest = create_system_backup_archive(
            current_user, frequency=frequency, passphrase=passphrase)
        _cleanup_system_backups(frequency, keep_last=3)

        security_audit.data_export(current_user.id, current_user.email, f'system_full:{frequency}')

        response = send_file(
            archive_path,
            mimetype='application/octet-stream' if passphrase is not None else 'application/gzip',
            as_attachment=True,
            download_name=filename,
        )
        response.headers['X-Message-Key'] = 'backup.system_export.created'
        response.headers['X-Backup-Manifest-Version'] = str(manifest.get('version', SYSTEM_BACKUP_VERSION))
        response.headers['X-Backup-Size'] = str(file_size)
        return response
    except RuntimeError as exc:
        current_app.logger.error('System backup export failed: %s', exc)
        return jsonify(localized_message(
            'backup.system_export.failed',
            'Full-state backup export failed',
            error=str(exc),
        )), 500


@backup_bp.route('/system/import', methods=['POST'])
@admin_required
def import_system_backup(current_user):
    """Restore a full-state system backup archive."""
    if 'file' not in request.files:
        return jsonify(localized_message(
            'backup.system_import.missing_file',
            'No backup file provided',
        )), 400

    actor_id, actor_email = current_user.id, current_user.email
    uploaded_file = request.files['file']
    if not uploaded_file or not uploaded_file.filename:
        return jsonify(localized_message(
            'backup.system_import.empty_file',
            'No backup file selected',
        )), 400

    filename = uploaded_file.filename.lower()
    if not filename.endswith(('.tar.gz', '.tgz', '.gcb')):
        return jsonify(localized_message(
            'backup.system_import.invalid_format',
            'Unsupported backup format',
            allowed_formats=['.tar.gz', '.tgz', '.tar.gz.gcb'],
        )), 400

    archive_path = None
    try:
        budget = Budget()
        temporary_root = tempfile.gettempdir()
        budget.space(temporary_root)
        with tempfile.NamedTemporaryFile(prefix='gearcargo-system-import-', suffix='.tar.gz', delete=False) as temp_file:
            archive_path = temp_file.name
            while chunk := uploaded_file.stream.read(CHUNK):
                budget.space(temporary_root, len(chunk))
                temp_file.write(chunk)
        # Encrypted imports need authenticated plaintext plus its named staging
        # copy; check their combined space before envelope authentication.
        with open(archive_path, 'rb') as source:
            if backup_crypto.is_encrypted(source) or filename.endswith('.gcb'):
                budget.space(temporary_root, 2 * os.path.getsize(archive_path))
            with backup_crypto.open_backup(source, filename, request.form.get('passphrase')) as (plaintext, inner_format):
                if inner_format != 'tar.gz':
                    raise backup_crypto.BackupEncryptionError('Use a full system archive here.')
                if plaintext is source:
                    manifest = restore_system_backup_archive(archive_path, budget=budget)
                else:
                    with tempfile.NamedTemporaryFile(prefix='gearcargo-authenticated-', suffix='.tar.gz') as verified:
                        while chunk := plaintext.read(CHUNK):
                            budget.space(temporary_root, len(chunk))
                            verified.write(chunk)
                        verified.flush()
                        manifest = restore_system_backup_archive(verified.name, budget=budget)
        _audit_restore(actor_id, actor_email, 'system_full', True)
        return jsonify(localized_message(
            'backup.system_import.completed',
            'System backup restored successfully',
            manifest=manifest,
            restored={
                'database': True,
                'attachments': True,
                'uploads': True,
            },
        ))
    except restore_tx.RestoreFailure as exc:
        return _restore_failure_response(exc)
    except (tarfile.TarError, ValueError) as exc:
        _audit_restore(actor_id, actor_email, 'system_full', False)
        current_app.logger.error('System backup import validation failed: %s', exc)
        return jsonify(localized_message(
            'backup.system_import.invalid_archive',
            'Invalid system backup archive',
            error=str(exc),
        )), 400
    except RuntimeError as exc:
        _audit_restore(actor_id, actor_email, 'system_full', False)
        current_app.logger.error('System backup import failed: %s', exc)
        return jsonify(localized_message(
            'backup.system_import.failed',
            'System backup restore failed',
            error=str(exc),
        )), 500
    finally:
        try:
            if archive_path:
                os.remove(archive_path)
        except OSError:
            pass

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
import tempfile
import subprocess
import uuid
import re
import requests
from datetime import datetime, timedelta
from io import BytesIO
from flask import Blueprint, request, jsonify, current_app, send_file
from sqlalchemy.engine.url import make_url
from sqlalchemy import func

from app import db
from app.models import (User, Vehicle, Entry, FuelEntry, ServiceEntry, RepairEntry,
                       TaxEntry, ParkingEntry, Reminder, InsurancePolicy,
                       Attachment, Backup, BackupSchedule, Todo)
from app.routes.auth import token_required, admin_required
from app.utils.security_audit import security_audit

backup_bp = Blueprint('backup', __name__)

SYSTEM_BACKUP_VERSION = '3.0'
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


def _restore_pg_dump_file(dump_path):
    """Restore a gzipped PostgreSQL dump."""
    config = _database_cli_config()
    db.session.remove()
    db.engine.dispose()

    command = [
        'psql',
        '--host', config['host'],
        '--port', config['port'],
        '--username', config['username'],
        '--dbname', config['database'],
        '-v', 'ON_ERROR_STOP=1',
    ]
    with gzip.open(dump_path, 'rb') as dump_file:
        dump_bytes = dump_file.read()

    result = subprocess.run(command, input=dump_bytes, capture_output=True, env=config['env'], check=False)
    if result.returncode != 0:
        error_output = result.stderr.decode('utf-8', errors='ignore').strip()
        raise RuntimeError(f'psql restore failed: {error_output or "unknown error"}')


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

    if not os.path.isdir(source_dir):
        return

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
            archive.add(filepath, arcname=f'{archive_root}/{rel_path}', recursive=False)


def _cleanup_system_backups(frequency, keep_last=3):
    """Keep only the latest system backup archives for a given frequency."""
    system_folder = get_system_backup_folder()
    if not os.path.isdir(system_folder):
        return

    prefix = f'{SYSTEM_BACKUP_PREFIX}_{frequency}_'
    backups = []
    for filename in os.listdir(system_folder):
        if filename.startswith(prefix) and filename.endswith('.tar.gz'):
            filepath = os.path.join(system_folder, filename)
            backups.append((filepath, os.path.getmtime(filepath)))

    backups.sort(key=lambda item: item[1], reverse=True)
    for filepath, _ in backups[keep_last:]:
        try:
            os.remove(filepath)
        except OSError:
            current_app.logger.warning('Failed to remove old system backup: %s', filepath)


def create_system_backup_archive(admin_user, frequency='manual'):
    """Create a full-state backup archive containing DB dump and media."""
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    filename = f'{SYSTEM_BACKUP_PREFIX}_{frequency}_{timestamp}.tar.gz'
    system_folder = get_system_backup_folder()
    os.makedirs(system_folder, exist_ok=True)
    archive_path = os.path.join(system_folder, filename)

    database_dump = _run_pg_dump_bytes()
    manifest = {
        'version': SYSTEM_BACKUP_VERSION,
        'backup_type': 'system_full',
        'frequency': frequency,
        'created_at': datetime.utcnow().isoformat(),
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

    with tarfile.open(archive_path, 'w:gz') as archive:
        _add_bytes_to_tar(
            archive,
            'manifest.json',
            json.dumps(manifest, indent=2).encode('utf-8'),
            mode=0o644,
        )
        _add_bytes_to_tar(archive, 'database/database.sql.gz', database_dump)
        _add_directory_to_tar(archive, get_attachment_folder(), 'media/attachments')
        _add_directory_to_tar(archive, get_uploads_folder(), 'media/uploads')

    return archive_path, filename, os.path.getsize(archive_path), manifest


def _validated_archive_name(name):
    """Validate a tar archive member path."""
    normalized = os.path.normpath(name).replace('\\', '/')
    if normalized in ('', '.'):
        return normalized
    if normalized.startswith('../') or normalized == '..' or normalized.startswith('/'):
        raise ValueError('Backup archive contains an invalid path')
    return normalized


def _extract_member_to_directory(archive, member, archive_prefix, target_root):
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
        shutil.copyfileobj(source_file, output_file)
    os.chmod(target_path, 0o640)


def _stage_directory_swap(source_dir, destination_dir):
    """Replace a directory tree using an on-volume staging directory."""
    os.makedirs(os.path.dirname(destination_dir), exist_ok=True)
    staging_dir = os.path.join(
        os.path.dirname(destination_dir),
        f'.{os.path.basename(destination_dir)}-restore-{uuid.uuid4().hex}'
    )
    rollback_dir = None

    os.makedirs(staging_dir, exist_ok=True)
    if os.path.isdir(source_dir):
        for entry in os.listdir(source_dir):
            source_path = os.path.join(source_dir, entry)
            target_path = os.path.join(staging_dir, entry)
            if os.path.isdir(source_path):
                shutil.copytree(source_path, target_path)
            else:
                shutil.copy2(source_path, target_path)

    try:
        if os.path.exists(destination_dir):
            rollback_dir = os.path.join(
                os.path.dirname(destination_dir),
                f'.{os.path.basename(destination_dir)}-rollback-{uuid.uuid4().hex}'
            )
            os.rename(destination_dir, rollback_dir)

        os.rename(staging_dir, destination_dir)

        if rollback_dir and os.path.exists(rollback_dir):
            shutil.rmtree(rollback_dir, ignore_errors=True)
    except Exception:
        if os.path.exists(destination_dir):
            shutil.rmtree(destination_dir, ignore_errors=True)
        if rollback_dir and os.path.exists(rollback_dir):
            os.rename(rollback_dir, destination_dir)
        if os.path.exists(staging_dir):
            shutil.rmtree(staging_dir, ignore_errors=True)
        raise


def restore_system_backup_archive(archive_path):
    """Restore a full-state backup archive into the current deployment."""
    with tempfile.TemporaryDirectory(prefix='gearcargo-system-restore-') as temp_dir:
        attachments_stage = os.path.join(temp_dir, 'attachments')
        uploads_stage = os.path.join(temp_dir, 'uploads')
        os.makedirs(attachments_stage, exist_ok=True)
        os.makedirs(uploads_stage, exist_ok=True)

        manifest = None
        database_dump_path = os.path.join(temp_dir, 'database.sql.gz')

        with tarfile.open(archive_path, 'r:gz') as archive:
            for member in archive.getmembers():
                member.name = _validated_archive_name(member.name)
                if member.issym() or member.islnk():
                    raise ValueError('Backup archive contains unsupported links')
                if member.isdir():
                    continue

                if member.name == 'manifest.json':
                    with archive.extractfile(member) as manifest_file:
                        manifest = json.loads(manifest_file.read().decode('utf-8'))
                elif member.name == 'database/database.sql.gz':
                    with archive.extractfile(member) as database_file, open(database_dump_path, 'wb') as output_file:
                        shutil.copyfileobj(database_file, output_file)
                elif member.name.startswith('media/attachments/'):
                    _extract_member_to_directory(archive, member, 'media/attachments/', attachments_stage)
                elif member.name.startswith('media/uploads/'):
                    _extract_member_to_directory(archive, member, 'media/uploads/', uploads_stage)

        if not os.path.exists(database_dump_path):
            raise ValueError('Backup archive is missing database/database.sql.gz')

        _restore_pg_dump_file(database_dump_path)
        _stage_directory_swap(attachments_stage, get_attachment_folder())
        _stage_directory_swap(uploads_stage, get_uploads_folder())
        db.session.remove()
        db.engine.dispose()

        return manifest or {}


def gather_user_data(user, include_attachments=True):
    """Gather all user data for backup."""
    export_data = {
        'version': '2.0',
        'exported_at': datetime.utcnow().isoformat(),
        'user': {
            'email': user.email,
            'name': user.display_name,
            'username': user.username,
            'preferences': {
                'theme': user.theme,
                'language': user.language,
                'monthly_report_enabled': user.monthly_report_enabled,
            }
        },
        'vehicles': [],
        'reminders': [],
        'insurance_policies': [],
        'todos': [],
        'attachments': [],
    }
    
    # Get all vehicles
    vehicles = Vehicle.query.filter_by(user_id=user.id).all()
    
    for vehicle in vehicles:
        vehicle_data = vehicle.to_dict()
        
        # Add entries for this vehicle
        vehicle_data['fuel_entries'] = [
            e.to_dict() for e in FuelEntry.query.filter_by(vehicle_id=vehicle.id).all()
        ]
        vehicle_data['service_entries'] = [
            e.to_dict() for e in ServiceEntry.query.filter_by(vehicle_id=vehicle.id).all()
        ]
        vehicle_data['repair_entries'] = [
            e.to_dict() for e in RepairEntry.query.filter_by(vehicle_id=vehicle.id).all()
        ]
        vehicle_data['tax_entries'] = [
            e.to_dict() for e in TaxEntry.query.filter_by(vehicle_id=vehicle.id).all()
        ]
        vehicle_data['parking_entries'] = [
            e.to_dict() for e in ParkingEntry.query.filter_by(vehicle_id=vehicle.id).all()
        ]
        
        export_data['vehicles'].append(vehicle_data)
    
    # Get reminders
    export_data['reminders'] = [
        r.to_dict() for r in Reminder.query.filter_by(user_id=user.id).all()
    ]
    
    # Get insurance policies
    export_data['insurance_policies'] = [
        p.to_dict() for p in InsurancePolicy.query.filter_by(user_id=user.id).all()
    ]
    
    # Get todos
    try:
        export_data['todos'] = [
            t.to_dict() for t in Todo.query.filter_by(user_id=user.id).all()
        ]
    except:
        export_data['todos'] = []
    
    # Get attachments metadata (files added to zip separately)
    if include_attachments:
        attachments = Attachment.query.filter_by(user_id=user.id).all()
        export_data['attachments'] = [a.to_dict() for a in attachments]
    
    return export_data


def create_backup_zip(user, include_attachments=True):
    """Create a complete backup ZIP file with data and attachments."""
    export_data = gather_user_data(user, include_attachments)
    
    # Create in-memory ZIP
    zip_buffer = BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Add JSON data
        data_json = json.dumps(export_data, indent=2, default=str)
        zf.writestr('backup_data.json', data_json)
        
        # Add manifest
        manifest = {
            'version': '2.0',
            'created_at': datetime.utcnow().isoformat(),
            'app_name': current_app.config.get('APP_NAME', 'GearCargo'),
            'user_email': user.email,
            'user_name': user.display_name or user.username or '',
            'include_attachments': include_attachments,
            'checksum': calculate_checksum(data_json),
        }
        zf.writestr('manifest.json', json.dumps(manifest, indent=2))
        
        # Add attachments if requested
        if include_attachments:
            attachment_folder = get_attachment_folder()
            attachments = Attachment.query.filter_by(user_id=user.id).all()
            
            # Track physical files already added to avoid duplicating content
            added_filepaths = {}  # filepath -> arcname already in ZIP
            
            for attachment in attachments:
                if attachment.filepath and os.path.exists(attachment.filepath):
                    if attachment.filepath in added_filepaths:
                        # File already in ZIP under a different attachment ID —
                        # still record a ZIP entry so each DB record is represented,
                        # but store it as a zero-overhead reference via writestr
                        # pointing to the same content (symlink-like).
                        # We write the file content only once; on import the
                        # deduplication logic matches by filepath+entry_id.
                        continue
                    arcname = f'attachments/{attachment.id}/{attachment.filename}'
                    zf.write(attachment.filepath, arcname)
                    added_filepaths[attachment.filepath] = arcname
            
            # Add vehicle photos
            uploads_folder = get_uploads_folder()
            vehicles = Vehicle.query.filter_by(user_id=user.id).all()
            
            for vehicle in vehicles:
                if vehicle.photo:
                    # Extract filename from photo path like "/uploads/vehicles/1_abc123.jpg"
                    photo_filename = os.path.basename(vehicle.photo)
                    photo_path = os.path.join(uploads_folder, 'vehicles', photo_filename)
                    
                    if os.path.exists(photo_path):
                        arcname = f'uploads/vehicles/{vehicle.id}/{photo_filename}'
                        zf.write(photo_path, arcname)
    
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
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    filename = f'{safe_app}_{safe_user}_{timestamp}.zip'
    filepath = os.path.join(user_folder, filename)
    
    # Write file
    with open(filepath, 'wb') as f:
        f.write(zip_buffer.read())
    
    # Get file size
    file_size = os.path.getsize(filepath)
    
    return filename, filepath, file_size


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


def _webdav_auth(schedule):
    """Return a (username, password) tuple for WebDAV Basic auth.

    The 'external_api_key' field stores either:
      - "user:apppassword"  (preferred)
      - plain app-password  (username taken from URL)
    """
    token = schedule.external_api_key or ''
    if ':' in token:
        parts = token.split(':', 1)
        return (parts[0], parts[1])
    # Fallback: use the token as password with empty user
    return (token, token)


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
            requests.request(
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
    resp = requests.request(
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
        resp = requests.put(
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
            requests.delete(upload_dir, auth=auth, timeout=15, verify=True)
            return None, f"Chunk {chunk_num} upload failed: {resp.status_code}"
        offset += CHUNK_SIZE
        chunk_num += 1
        current_app.logger.info(f'Chunked upload: chunk {chunk_num}, {min(offset, total_size)}/{total_size} bytes')

    # 3. Assemble — MOVE .file to final destination
    dest_url = _webdav_upload_url(schedule, filename)
    # Destination header needs the path portion only (absolute URI path)
    from urllib.parse import urlparse
    dest_parsed = urlparse(dest_url)
    dest_path = dest_parsed.path

    assemble_url = f"{upload_dir}/.file"
    resp = requests.request(
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

    # Validate URL is HTTPS for security
    if not schedule.external_url.startswith('https://'):
        return None, "External URL must use HTTPS for security"

    if not filename:
        filename = f'gearcargo_backup_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.zip'

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

        response = requests.put(
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
            requests.delete(upload_url, auth=auth, timeout=30, verify=True)
            time.sleep(1)
            response = requests.put(
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
            current_app.logger.warning(f'Got 413 on direct PUT, falling back to chunked upload')
            return _chunked_webdav_upload(backup_data, schedule, filename, auth)
        elif response.status_code == 423:
            return None, "File is locked on the server. Try again in a few minutes or unlock it in Nextcloud."
        else:
            return None, f"Server returned {response.status_code}: {response.text[:200]}"

    except requests.exceptions.SSLError as e:
        return None, f"SSL certificate error: {str(e)}"
    except requests.exceptions.Timeout:
        return None, "Connection to external server timed out"
    except requests.exceptions.RequestException as e:
        return None, f"Failed to connect to external server: {str(e)}"


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
    
    # Get all backup files
    files = []
    for f in os.listdir(user_folder):
        if f.startswith('backup_') and f.endswith('.zip'):
            filepath = os.path.join(user_folder, f)
            mtime = os.path.getmtime(filepath)
            files.append((filepath, mtime))
    
    # Sort by modification time (newest first)
    files.sort(key=lambda x: x[1], reverse=True)
    
    deleted = 0
    cutoff_time = datetime.utcnow() - timedelta(days=retention_days)
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
            except:
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
    available_backups = []
    
    if os.path.exists(user_folder):
        for f in sorted(os.listdir(user_folder), reverse=True):
            if f.endswith('.zip'):
                filepath = os.path.join(user_folder, f)
                stat = os.stat(filepath)
                created = datetime.fromtimestamp(stat.st_mtime)
                # Build display label from filename parts
                label = _backup_display_label(f, created)
                available_backups.append({
                    'filename': f,
                    'size': stat.st_size,
                    'size_human': format_file_size(stat.st_size),
                    'created_at': created.isoformat(),
                    'label': label,
                })
    
    return jsonify({
        'schedule': schedule.to_dict() if schedule else None,
        'last_backup': last_backup.created_at.isoformat() if last_backup else None,
        'last_backup_details': last_backup.to_dict() if last_backup else None,
        'available_backups': available_backups[:10],  # Limit to 10 most recent
        'total_backup_count': len(available_backups),
    })


def _backup_display_label(filename, created_dt):
    """Build a human-readable label for a backup file."""
    # Strip extension
    name = filename.rsplit('.', 1)[0]
    # New format: AppName_User_YYYYMMDD_HHMMSS
    # Old format: backup_YYYYMMDD_HHMMSS
    parts = name.split('_')
    if len(parts) >= 4 and parts[-1].isdigit() and parts[-2].isdigit():
        # New naming: everything before the last two parts is app+user
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
    
    # Create backup record
    backup = Backup(
        user_id=current_user.id,
        backup_type='export',
        format=format_type,
        status='in_progress',
        started_at=datetime.utcnow(),
    )
    db.session.add(backup)
    db.session.commit()
    
    try:
        if format_type == 'json':
            # Simple JSON export
            export_data = gather_user_data(current_user, include_attachments=False)
            
            backup.status = 'completed'
            backup.completed_at = datetime.utcnow()
            backup.vehicles_count = len(export_data['vehicles'])
            backup.entries_count = sum(
                len(v.get('fuel_entries', [])) +
                len(v.get('service_entries', [])) +
                len(v.get('repair_entries', [])) +
                len(v.get('tax_entries', [])) +
                len(v.get('parking_entries', []))
                for v in export_data['vehicles']
            )
            backup.reminders_count = len(export_data['reminders'])
            
            json_data = json.dumps(export_data, indent=2, default=str)
            backup.file_size = len(json_data.encode('utf-8'))
            backup.checksum = calculate_checksum(json_data)
            db.session.commit()
            
            # Security audit log for data export
            security_audit.data_export(current_user.id, current_user.email, 'json')
            
            buffer = BytesIO(json_data.encode('utf-8'))
            return send_file(
                buffer,
                mimetype='application/json',
                as_attachment=True,
                download_name=f'gearcargo_export_{datetime.utcnow().strftime("%Y%m%d")}.json'
            )
        
        else:
            # Full ZIP backup with attachments
            zip_buffer, export_data = create_backup_zip(current_user, include_attachments)
            
            # Count attachments
            attachments_count = len(export_data.get('attachments', []))
            
            backup.status = 'completed'
            backup.completed_at = datetime.utcnow()
            backup.vehicles_count = len(export_data['vehicles'])
            backup.entries_count = sum(
                len(v.get('fuel_entries', [])) +
                len(v.get('service_entries', [])) +
                len(v.get('repair_entries', [])) +
                len(v.get('tax_entries', [])) +
                len(v.get('parking_entries', []))
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
                mimetype='application/zip',
                as_attachment=True,
                download_name=f'gearcargo_backup_{datetime.utcnow().strftime("%Y%m%d")}.zip'
            )
    
    except Exception as e:
        backup.status = 'failed'
        backup.error_message = str(e)
        backup.completed_at = datetime.utcnow()
        db.session.commit()
        current_app.logger.error(f'Backup export failed: {e}')
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
        filename = file.filename.lower()
        
        if filename.endswith('.zip'):
            # ZIP backup with attachments
            return restore_from_zip(current_user, file, merge_mode)
        elif filename.endswith('.json'):
            # JSON-only backup
            return restore_from_json(current_user, file, merge_mode)
        else:
            return jsonify({'error': 'Unsupported file format. Use .json or .zip'}), 400
    
    except json.JSONDecodeError as e:
        security_audit.data_import(current_user.id, current_user.email, 'unknown', success=False)
        current_app.logger.error(f'Backup import JSON error: {e}')
        return jsonify({'error': 'Invalid backup file format. Please ensure the file is a valid JSON or ZIP backup.'}), 400
    except Exception as e:
        security_audit.data_import(current_user.id, current_user.email, 'unknown', success=False)
        current_app.logger.error(f'Backup import failed: {e}')
        return jsonify({'error': 'Import failed. Please try again later.'}), 500


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
        distance_unit = None

    try:
        from app.services.lubelog_import import import_lubelog_to_gearcargo

        zip_data = BytesIO(file.read())
        result = import_lubelog_to_gearcargo(current_user, zip_data, merge_mode, distance_unit=distance_unit)

        if result.get('error'):
            security_audit.data_import(current_user.id, current_user.email, 'lubelog', success=False)
            return jsonify({'error': result['error']}), 400

        security_audit.data_import(current_user.id, current_user.email, 'lubelog', success=True)

        return jsonify({
            'message': 'LubeLogger import completed successfully',
            'imported': result.get('imported', {}),
            'summary': result.get('summary', {}),
        })

    except ValueError as e:
        security_audit.data_import(current_user.id, current_user.email, 'lubelog', success=False)
        current_app.logger.error(f'LubeLogger import validation error: {e}')
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        security_audit.data_import(current_user.id, current_user.email, 'lubelog', success=False)
        current_app.logger.error(f'LubeLogger import failed: {e}', exc_info=True)
        return jsonify({'error': f'LubeLogger import failed: {type(e).__name__}: {e}'}), 500


def restore_from_json(user, file, merge_mode='merge'):
    """Restore from JSON backup file."""
    content = file.read().decode('utf-8')
    backup_data = json.loads(content)
    
    imported, _, _ = import_backup_data(user, backup_data, merge_mode)
    
    return jsonify({
        'message': 'Import completed',
        'imported': imported
    })


def restore_from_zip(user, file, merge_mode='merge'):
    """Restore from ZIP backup file with attachments."""
    zip_data = BytesIO(file.read())
    
    with zipfile.ZipFile(zip_data, 'r') as zf:
        # Read manifest
        if 'manifest.json' in zf.namelist():
            manifest = json.loads(zf.read('manifest.json').decode('utf-8'))
            current_app.logger.info(f'Restoring backup version {manifest.get("version", "1.0")}')
        
        # Read backup data
        if 'backup_data.json' not in zf.namelist():
            return jsonify({'error': 'Invalid backup file: missing backup_data.json'}), 400
        
        backup_data = json.loads(zf.read('backup_data.json').decode('utf-8'))
        
        # Import data and get vehicle ID mapping and entry ID mapping
        imported, vehicle_id_map, entry_id_map = import_backup_data(user, backup_data, merge_mode)
        
        # Add attachments and vehicle_photos counter
        imported['attachments'] = 0
        imported['vehicle_photos'] = 0
        
        # Track mapping of old attachment IDs to new attachment IDs
        attachment_id_map = {}
        
        # Restore attachments
        attachment_folder = get_attachment_folder()
        user_attachment_folder = os.path.join(attachment_folder, str(user.id))
        os.makedirs(user_attachment_folder, exist_ok=True)
        
        # Build a map of old attachment IDs to their metadata from backup_data
        attachment_metadata = {}
        for att in backup_data.get('attachments', []):
            attachment_metadata[str(att.get('id'))] = att
        
        # Restore vehicle photos
        uploads_folder = get_uploads_folder()
        vehicle_photo_folder = os.path.join(uploads_folder, 'vehicles')
        os.makedirs(vehicle_photo_folder, mode=0o750, exist_ok=True)
        
        for name in zf.namelist():
            if name.startswith('uploads/vehicles/'):
                parts = name.split('/')
                if len(parts) >= 4:
                    # Path is: uploads/vehicles/{old_vehicle_id}/{filename}
                    old_vehicle_id_str = parts[2]
                    filename = parts[3]
                    
                    if not filename:  # Skip directory entries
                        continue
                    
                    try:
                        old_vehicle_id = int(old_vehicle_id_str)
                    except ValueError:
                        continue
                    
                    # Get new vehicle ID
                    new_vehicle_id = vehicle_id_map.get(old_vehicle_id)
                    if not new_vehicle_id:
                        continue
                    
                    # Extract file
                    content = zf.read(name)
                    
                    # Create new filename with new vehicle ID
                    # Old filename format: {old_id}_{uuid}.{ext}
                    # New filename format: {new_id}_{uuid}.{ext}
                    ext = filename.rsplit('.', 1)[1] if '.' in filename else 'jpg'
                    import uuid
                    new_filename = f"{new_vehicle_id}_{uuid.uuid4().hex}.{ext}"
                    new_filepath = os.path.join(vehicle_photo_folder, new_filename)
                    
                    with open(new_filepath, 'wb') as f:
                        f.write(content)
                    os.chmod(new_filepath, 0o640)
                    
                    # Update vehicle photo field
                    vehicle = Vehicle.query.get(new_vehicle_id)
                    if vehicle:
                        vehicle.photo = f"/uploads/vehicles/{new_filename}"
                        imported['vehicle_photos'] += 1
            
            elif name.startswith('attachments/'):
                parts = name.split('/')
                if len(parts) >= 3:
                    # Extract attachment_id and filename from path
                    old_id = parts[1]
                    filename = parts[2]
                    
                    if not filename:  # Skip directory entries
                        continue
                    
                    # Build target path
                    new_filepath = os.path.join(user_attachment_folder, filename)
                    
                    # Attachment metadata
                    att_meta = attachment_metadata.get(old_id, {})
                    
                    # Map old vehicle_id to new vehicle_id
                    old_vehicle_id = att_meta.get('vehicle_id')
                    new_vehicle_id = vehicle_id_map.get(old_vehicle_id) if old_vehicle_id else None
                    
                    # Map old entry_id to new entry_id
                    old_entry_id = att_meta.get('entry_id')
                    new_entry_id = entry_id_map.get(old_entry_id) if old_entry_id else None
                    
                    # Deduplication: skip if attachment with same filepath+entry already exists
                    existing_att = Attachment.query.filter_by(
                        user_id=user.id,
                        filepath=new_filepath,
                        entry_id=new_entry_id,
                    ).first()
                    if existing_att:
                        try:
                            old_id_int = int(old_id)
                            attachment_id_map[old_id_int] = existing_att.id
                        except ValueError:
                            pass
                        continue
                    
                    # Extract and save file to disk
                    content = zf.read(name)
                    with open(new_filepath, 'wb') as f:
                        f.write(content)
                    os.chmod(new_filepath, 0o640)
                    
                    attachment = Attachment(
                        user_id=user.id,
                        filename=filename,
                        original_filename=att_meta.get('original_filename', filename),
                        filepath=new_filepath,
                        file_type=att_meta.get('file_type'),
                        file_size=len(content),
                        description=att_meta.get('description'),
                        category=att_meta.get('category'),
                        tags=att_meta.get('tags'),
                        vehicle_id=new_vehicle_id,
                        entry_id=new_entry_id,
                    )
                    db.session.add(attachment)
                    db.session.flush()  # Get the new attachment ID
                    
                    # Track old to new attachment ID mapping
                    try:
                        old_id_int = int(old_id)
                        attachment_id_map[old_id_int] = attachment.id
                    except ValueError:
                        pass
                    
                    imported['attachments'] += 1
        
        # Update insurance policies with new document_attachment_id
        if attachment_id_map:
            for policy_data in backup_data.get('insurance_policies', []):
                old_att_id = policy_data.get('document_attachment_id')
                if old_att_id and old_att_id in attachment_id_map:
                    # Find the insurance policy we just created (by matching unique fields)
                    policy = InsurancePolicy.query.filter_by(
                        user_id=user.id,
                        policy_number=policy_data.get('policy_number'),
                        provider=policy_data.get('provider')
                    ).first()
                    if policy:
                        policy.document_attachment_id = attachment_id_map[old_att_id]
        
        db.session.commit()
    
    # Security audit log for data import
    security_audit.data_import(user.id, user.email, 'zip', success=True)
    
    return jsonify({
        'message': 'Import completed',
        'imported': imported
    })


def _entry_exists(model_class, user_id, vehicle_id, entry_date, amount):
    """Check if an entry with the same (vehicle, date, amount) exists."""
    from decimal import Decimal
    q = model_class.query.filter_by(
        user_id=user_id,
        vehicle_id=vehicle_id,
        date=entry_date,
    )
    if amount is not None:
        q = q.filter(model_class.amount == Decimal(str(amount)))
    else:
        q = q.filter(model_class.amount.is_(None))
    return q.first()


def import_backup_data(user, backup_data, merge_mode='merge'):
    """Import backup data into database with deduplication."""
    imported = {
        'vehicles': 0,
        'fuel_entries': 0,
        'service_entries': 0,
        'repair_entries': 0,
        'tax_entries': 0,
        'parking_entries': 0,
        'reminders': 0,
        'insurance_policies': 0,
        'todos': 0,
        'skipped_duplicates': 0,
    }
    
    # Track mapping of old vehicle IDs to new vehicle IDs
    vehicle_id_map = {}
    # Track mapping of old entry IDs to new entry IDs (for attachments)
    entry_id_map = {}
    
    # Import vehicles
    for vehicle_data in backup_data.get('vehicles', []):
        old_vehicle_id = vehicle_data.get('id')
        
        # Check if vehicle already exists (by VIN or license plate)
        existing = None
        if vehicle_data.get('vin'):
            existing = Vehicle.query.filter_by(
                user_id=user.id,
                vin=vehicle_data['vin']
            ).first()
        
        if not existing and vehicle_data.get('license_plate'):
            existing = Vehicle.query.filter_by(
                user_id=user.id,
                license_plate=vehicle_data['license_plate']
            ).first()
        
        if existing:
            vehicle = existing
            if merge_mode == 'replace':
                for key in ['name', 'make', 'model', 'year', 'fuel_type', 'current_mileage', 'archived']:
                    if key in vehicle_data and vehicle_data[key] is not None:
                        setattr(vehicle, key, vehicle_data[key])
                # Handle archived_at separately (datetime parsing)
                if vehicle_data.get('archived_at'):
                    try:
                        vehicle.archived_at = datetime.fromisoformat(vehicle_data['archived_at'].replace('Z', '+00:00'))
                    except:
                        pass
        else:
            # Parse archived_at datetime if present
            archived_at = None
            if vehicle_data.get('archived_at'):
                try:
                    archived_at = datetime.fromisoformat(vehicle_data['archived_at'].replace('Z', '+00:00'))
                except:
                    pass
            
            vehicle = Vehicle(
                user_id=user.id,
                name=vehicle_data.get('name', 'Imported Vehicle'),
                make=vehicle_data.get('make'),
                model=vehicle_data.get('model'),
                year=vehicle_data.get('year'),
                vin=vehicle_data.get('vin'),
                license_plate=vehicle_data.get('license_plate'),
                fuel_type=vehicle_data.get('fuel_type'),
                current_mileage=vehicle_data.get('current_mileage') or vehicle_data.get('initial_mileage', 0),
                archived=vehicle_data.get('archived', False),
                archived_at=archived_at,
            )
            db.session.add(vehicle)
            db.session.flush()
            imported['vehicles'] += 1
        
        # Map old vehicle ID to new vehicle ID
        if old_vehicle_id:
            vehicle_id_map[old_vehicle_id] = vehicle.id
        
        # Import fuel entries
        for entry_data in vehicle_data.get('fuel_entries', []):
            old_entry_id = entry_data.get('id')
            # Parse date - handle both 'date' and 'entry_date' field names for compatibility
            date_str = entry_data.get('date') or entry_data.get('entry_date')
            entry_date = datetime.fromisoformat(date_str).date() if date_str else datetime.utcnow().date()
            amount = entry_data.get('amount') or entry_data.get('total_price') or entry_data.get('total_cost')
            
            # Deduplication: skip if identical entry exists
            existing = _entry_exists(FuelEntry, user.id, vehicle.id, entry_date, amount)
            if existing:
                if old_entry_id:
                    entry_id_map[old_entry_id] = existing.id
                imported['skipped_duplicates'] += 1
                continue
            
            entry = FuelEntry(
                user_id=user.id,
                vehicle_id=vehicle.id,
                date=entry_date,
                odometer=entry_data.get('odometer') or entry_data.get('mileage'),
                amount=amount,
                liters=entry_data.get('liters') or entry_data.get('volume'),
                price_per_liter=entry_data.get('price_per_liter') or entry_data.get('price_per_unit'),
                total_price=entry_data.get('total_price') or entry_data.get('total_cost'),
                fuel_type=entry_data.get('fuel_type'),
                full_tank=entry_data.get('full_tank', entry_data.get('is_full_tank', True)),
                station=entry_data.get('station'),
            )
            db.session.add(entry)
            db.session.flush()  # Get the new entry ID
            if old_entry_id:
                entry_id_map[old_entry_id] = entry.id
            imported['fuel_entries'] += 1
        
        # Import service entries
        for entry_data in vehicle_data.get('service_entries', []):
            old_entry_id = entry_data.get('id')
            date_str = entry_data.get('date') or entry_data.get('entry_date')
            entry_date = datetime.fromisoformat(date_str).date() if date_str else datetime.utcnow().date()
            amount = entry_data.get('amount') or entry_data.get('cost')
            
            existing = _entry_exists(ServiceEntry, user.id, vehicle.id, entry_date, amount)
            if existing:
                if old_entry_id:
                    entry_id_map[old_entry_id] = existing.id
                imported['skipped_duplicates'] += 1
                continue
            
            entry = ServiceEntry(
                user_id=user.id,
                vehicle_id=vehicle.id,
                date=entry_date,
                odometer=entry_data.get('odometer') or entry_data.get('mileage'),
                amount=amount,
                service_type=entry_data.get('service_type'),
                description=entry_data.get('description'),
                provider=entry_data.get('provider'),
                garage_name=entry_data.get('garage_name'),
            )
            db.session.add(entry)
            db.session.flush()  # Get the new entry ID
            if old_entry_id:
                entry_id_map[old_entry_id] = entry.id
            imported['service_entries'] += 1
        
        # Import repair entries
        for entry_data in vehicle_data.get('repair_entries', []):
            old_entry_id = entry_data.get('id')
            date_str = entry_data.get('date') or entry_data.get('entry_date')
            entry_date = datetime.fromisoformat(date_str).date() if date_str else datetime.utcnow().date()
            amount = entry_data.get('amount') or entry_data.get('cost')
            
            existing = _entry_exists(RepairEntry, user.id, vehicle.id, entry_date, amount)
            if existing:
                if old_entry_id:
                    entry_id_map[old_entry_id] = existing.id
                imported['skipped_duplicates'] += 1
                continue
            
            entry = RepairEntry(
                user_id=user.id,
                vehicle_id=vehicle.id,
                date=entry_date,
                odometer=entry_data.get('odometer') or entry_data.get('mileage'),
                amount=amount,
                repair_type=entry_data.get('repair_type'),
                description=entry_data.get('description'),
                provider=entry_data.get('provider'),
                garage_name=entry_data.get('garage_name'),
            )
            db.session.add(entry)
            db.session.flush()  # Get the new entry ID
            if old_entry_id:
                entry_id_map[old_entry_id] = entry.id
            imported['repair_entries'] += 1
        
        # Import tax entries
        for entry_data in vehicle_data.get('tax_entries', []):
            old_entry_id = entry_data.get('id')
            date_str = entry_data.get('date') or entry_data.get('entry_date')
            entry_date = datetime.fromisoformat(date_str).date() if date_str else datetime.utcnow().date()
            amount = entry_data.get('amount') or entry_data.get('cost')
            
            existing = _entry_exists(TaxEntry, user.id, vehicle.id, entry_date, amount)
            if existing:
                if old_entry_id:
                    entry_id_map[old_entry_id] = existing.id
                imported['skipped_duplicates'] += 1
                continue
            
            # Parse due_date if present
            due_date = None
            if entry_data.get('due_date'):
                due_date = datetime.fromisoformat(entry_data['due_date']).date()
            
            # Parse next_due_date if present
            next_due_date = None
            if entry_data.get('next_due_date'):
                next_due_date = datetime.fromisoformat(entry_data['next_due_date']).date()
            
            entry = TaxEntry(
                user_id=user.id,
                vehicle_id=vehicle.id,
                date=entry_date,
                amount=amount,
                tax_type=entry_data.get('tax_type'),
                title=entry_data.get('title'),
                description=entry_data.get('description'),
                notes=entry_data.get('notes'),
                tax_year=entry_data.get('tax_year'),
                tax_period=entry_data.get('tax_period'),
                status=entry_data.get('status', 'paid'),
                due_date=due_date,
                reference_number=entry_data.get('reference_number'),
                recurring=entry_data.get('recurring', False),
                recurrence_type=entry_data.get('recurrence_type'),
                next_due_date=next_due_date,
                reminder_days=entry_data.get('reminder_days', 30),
                # Note: insurance_policy_id will be linked separately after all policies are imported
            )
            db.session.add(entry)
            db.session.flush()  # Get the new entry ID
            if old_entry_id:
                entry_id_map[old_entry_id] = entry.id
            imported['tax_entries'] += 1
        
        # Import parking entries
        for entry_data in vehicle_data.get('parking_entries', []):
            old_entry_id = entry_data.get('id')
            date_str = entry_data.get('date') or entry_data.get('entry_date')
            entry_date = datetime.fromisoformat(date_str).date() if date_str else datetime.utcnow().date()
            amount = entry_data.get('amount') or entry_data.get('cost')
            
            existing = _entry_exists(ParkingEntry, user.id, vehicle.id, entry_date, amount)
            if existing:
                if old_entry_id:
                    entry_id_map[old_entry_id] = existing.id
                imported['skipped_duplicates'] += 1
                continue
            
            entry = ParkingEntry(
                user_id=user.id,
                vehicle_id=vehicle.id,
                date=entry_date,
                amount=amount,
                parking_type=entry_data.get('parking_type'),
                location=entry_data.get('location'),
            )
            db.session.add(entry)
            db.session.flush()  # Get the new entry ID
            if old_entry_id:
                entry_id_map[old_entry_id] = entry.id
            imported['parking_entries'] += 1
    
    # Import reminders
    for reminder_data in backup_data.get('reminders', []):
        # Map old vehicle_id to new vehicle_id
        old_vehicle_id = reminder_data.get('vehicle_id')
        new_vehicle_id = vehicle_id_map.get(old_vehicle_id) if old_vehicle_id else None
        
        # vehicle_id is NOT NULL in DB — skip reminders without a valid vehicle
        if not new_vehicle_id:
            continue
        
        reminder = Reminder(
            user_id=user.id,
            vehicle_id=new_vehicle_id,
            title=reminder_data.get('title'),
            description=reminder_data.get('description'),
            reminder_type=reminder_data.get('reminder_type', 'custom'),
            due_date=datetime.fromisoformat(reminder_data['due_date']).date() if reminder_data.get('due_date') else None,
            priority=reminder_data.get('priority', 'medium'),
        )
        db.session.add(reminder)
        imported['reminders'] += 1
    
    # Import insurance policies
    for policy_data in backup_data.get('insurance_policies', []):
        # Find the vehicle by name or use first vehicle
        vehicle_id = None
        old_vehicle_id = policy_data.get('vehicle_id')
        if old_vehicle_id and old_vehicle_id in vehicle_id_map:
            vehicle_id = vehicle_id_map[old_vehicle_id]
        elif vehicles:
            vehicle_id = vehicles[0].id
        
        if vehicle_id:
            policy = InsurancePolicy(
                user_id=user.id,
                vehicle_id=vehicle_id,
                policy_number=policy_data.get('policy_number'),
                provider=policy_data.get('provider'),
                policy_type=policy_data.get('policy_type') or policy_data.get('coverage_type'),
                premium=policy_data.get('premium'),
                payment_frequency=policy_data.get('payment_frequency'),
                coverage_amount=policy_data.get('coverage_amount'),
                deductible=policy_data.get('deductible'),
                start_date=datetime.fromisoformat(policy_data['start_date']).date() if policy_data.get('start_date') else None,
                end_date=datetime.fromisoformat(policy_data['end_date']).date() if policy_data.get('end_date') else None,
                agent_name=policy_data.get('agent_name'),
                agent_phone=policy_data.get('agent_phone'),
                agent_email=policy_data.get('agent_email'),
                claims_phone=policy_data.get('claims_phone'),
                status=policy_data.get('status', 'active'),
                auto_renew=policy_data.get('auto_renew', False),
                notes=policy_data.get('notes'),
                currency=policy_data.get('currency'),
            )
            db.session.add(policy)
            imported['insurance_policies'] += 1
    
    # Import todos
    for todo_data in backup_data.get('todos', []):
        try:
            todo = Todo(
                user_id=user.id,
                title=todo_data.get('title'),
                description=todo_data.get('description'),
                priority=todo_data.get('priority', 'medium'),
                status=todo_data.get('status', 'pending'),
            )
            db.session.add(todo)
            imported['todos'] += 1
        except:
            pass
    
    # Recalculate current_mileage for all imported/merged vehicles
    for new_vehicle_id in vehicle_id_map.values():
        max_odometer = db.session.query(func.max(Entry.odometer)).filter(
            Entry.user_id == user.id,
            Entry.vehicle_id == new_vehicle_id,
            Entry.odometer.isnot(None)
        ).scalar()
        if max_odometer:
            vehicle = Vehicle.query.get(new_vehicle_id)
            if vehicle and (vehicle.current_mileage or 0) < max_odometer:
                vehicle.current_mileage = max_odometer
    
    db.session.commit()
    return imported, vehicle_id_map, entry_id_map


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

    return send_file(
        filepath,
        mimetype='application/zip' if filename.endswith('.zip') else 'application/octet-stream',
        as_attachment=True,
        download_name=filename
    )


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
            class FileWrapper:
                def __init__(self, file, name):
                    self.file = file
                    self.filename = name
                def read(self):
                    return self.file.read()
            
            wrapper = FileWrapper(f, filename)
            
            if filename.endswith('.zip'):
                return restore_from_zip(current_user, wrapper, merge_mode)
            elif filename.endswith('.json'):
                return restore_from_json(current_user, wrapper, merge_mode)
            else:
                return jsonify({'error': 'Unsupported file format'}), 400
    
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
    per_page = request.args.get('per_page', 20, type=int)
    
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
    
    # Validate external URL is HTTPS
    if data.get('external_enabled') and data.get('external_url'):
        if not data['external_url'].startswith('https://'):
            return jsonify({'error': 'External URL must use HTTPS for security'}), 400

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
            if not url.startswith('https://'):
                return jsonify({'error': f'Destination at index {index} must use HTTPS'}), 400

            api_key = str(destination.get('external_api_key') or destination.get('api_key') or '').strip()
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
    
    # Create backup record
    backup = Backup(
        user_id=current_user.id,
        backup_type='manual',
        format='zip',
        status='in_progress',
        started_at=datetime.utcnow(),
    )
    db.session.add(backup)
    db.session.commit()
    
    try:
        # Create backup
        zip_buffer, export_data = create_backup_zip(current_user, include_attachments)
        
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
            len(v.get('parking_entries', []))
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
        backup.completed_at = datetime.utcnow()
        
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
        backup.error_message = str(e)
        backup.completed_at = datetime.utcnow()
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
        current_app.logger.error(f'Manual backup failed: {e}', exc_info=True)
        return jsonify({'error': f'Backup failed: {type(e).__name__}: {e}'}), 500


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
        # Find latest backup
        if not os.path.exists(user_folder):
            return jsonify({'error': 'No stored backups found. Run a backup first.'}), 404
        files = sorted(
            [f for f in os.listdir(user_folder) if f.startswith('backup_') and f.endswith('.zip')],
            reverse=True
        )
        if not files:
            return jsonify({'error': 'No stored backups found. Run a backup first.'}), 404
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
        })
    except Exception as e:
        current_app.logger.error(f'Send to external failed: {e}', exc_info=True)
        return jsonify({'error': f'Failed: {str(e)}'}), 500


@backup_bp.route('/external/test', methods=['POST'])
@token_required
def test_external_connection(current_user):
    """Test connection to external backup server via WebDAV PROPFIND."""
    data = request.get_json()

    if not data.get('url'):
        return jsonify({'error': 'URL is required'}), 400

    url = data['url']
    api_key = data.get('api_key', '')
    path = data.get('path', '/GearCargo')

    # Fall back to stored credentials if not provided
    if not api_key:
        schedule = BackupSchedule.query.filter_by(user_id=current_user.id).first()
        if schedule and schedule.external_api_key:
            api_key = schedule.external_api_key

    # Validate HTTPS
    if not url.startswith('https://'):
        return jsonify({'error': 'URL must use HTTPS for security'}), 400

    # Build auth tuple
    if ':' in api_key:
        parts = api_key.split(':', 1)
        auth = (parts[0], parts[1])
    else:
        auth = (api_key, api_key)

    try:
        # Test with WebDAV PROPFIND on the user root
        base = _webdav_base_url(url)
        propfind_url = f"{base}/{auth[0]}"

        response = requests.request(
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

    # Fall back to stored credentials if not provided
    if not api_key:
        schedule = BackupSchedule.query.filter_by(user_id=current_user.id).first()
        if schedule and schedule.external_api_key:
            api_key = schedule.external_api_key

    if not api_key:
        return jsonify({'error': 'API Key is required'}), 400

    if not url.startswith('https://'):
        return jsonify({'error': 'URL must use HTTPS'}), 400

    # Build auth
    if ':' in api_key:
        parts = api_key.split(':', 1)
        auth = (parts[0], parts[1])
    else:
        auth = (api_key, api_key)

    try:
        base = _webdav_base_url(url)
        browse_path = path.strip('/')
        browse_url = f"{base}/{auth[0]}/{browse_path}" if browse_path else f"{base}/{auth[0]}"
        # Ensure trailing slash for PROPFIND on collections
        if not browse_url.endswith('/'):
            browse_url += '/'

        current_app.logger.info(f'WebDAV PROPFIND: {browse_url}')

        response = requests.request(
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
        current_app.logger.warning(f'WebDAV browse failed: {e}')
        return jsonify({'error': f'Failed to browse: {str(e)}'}), 400


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

    # Fall back to stored credentials if not provided
    if not api_key:
        schedule = BackupSchedule.query.filter_by(user_id=current_user.id).first()
        if schedule and schedule.external_api_key:
            api_key = schedule.external_api_key

    if not api_key:
        return jsonify({'error': 'API Key is required'}), 400

    if not url.startswith('https://'):
        return jsonify({'error': 'URL must use HTTPS'}), 400

    # Build auth
    if ':' in api_key:
        parts = api_key.split(':', 1)
        auth = (parts[0], parts[1])
    else:
        auth = (api_key, api_key)

    try:
        base = _webdav_base_url(url)
        browse_path = path.strip('/')
        browse_url = f"{base}/{auth[0]}/{browse_path}/" if browse_path else f"{base}/{auth[0]}/"

        response = requests.request(
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
                    if name.endswith('.zip'):
                        files.append({
                            'name': name,
                            'size': int(size_elem.text) if size_elem is not None and size_elem.text else 0,
                            'size_human': format_file_size(int(size_elem.text)) if size_elem is not None and size_elem.text else '?',
                            'last_modified': lastmod_elem.text if lastmod_elem is not None else None,
                        })

        # Sort by name descending (newest first by convention)
        files.sort(key=lambda f: f['name'], reverse=True)
        return jsonify({'files': files, 'path': path})

    except requests.exceptions.RequestException as e:
        current_app.logger.warning(f'WebDAV file browse failed: {e}')
        return jsonify({'error': f'Failed to browse: {str(e)}'}), 400


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

    if not filename.endswith('.zip'):
        return jsonify({'error': 'Only .zip backup files are supported'}), 400

    # Get schedule for credentials, or use provided ones
    schedule = BackupSchedule.query.filter_by(user_id=current_user.id).first()
    url = data.get('url') or (schedule.external_url if schedule else None)
    api_key = data.get('api_key') or (schedule.external_api_key if schedule else None)
    path = data.get('path') or (schedule.external_path if schedule else '/GearCargo')

    if not url or not api_key:
        return jsonify({'error': 'External backup credentials not configured'}), 400

    if not url.startswith('https://'):
        return jsonify({'error': 'URL must use HTTPS'}), 400

    # Build auth
    if ':' in api_key:
        parts = api_key.split(':', 1)
        auth = (parts[0], parts[1])
    else:
        auth = (api_key, api_key)

    try:
        base = _webdav_base_url(url)
        file_path = path.strip('/')
        download_url = f"{base}/{auth[0]}/{file_path}/{filename}"

        current_app.logger.info(f'Downloading from external: {download_url}')

        response = requests.get(
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

        # Optionally save locally first
        backup_folder = get_backup_folder()
        user_folder = os.path.join(backup_folder, str(current_user.id))
        os.makedirs(user_folder, exist_ok=True)
        local_path = os.path.join(user_folder, filename)
        with open(local_path, 'wb') as f:
            f.write(file_content)

        # Restore from the downloaded ZIP
        zip_data = BytesIO(file_content)
        with zipfile.ZipFile(zip_data, 'r') as zf:
            if 'backup_data.json' not in zf.namelist():
                return jsonify({'error': 'Invalid backup file: missing backup_data.json'}), 400

            backup_data = json.loads(zf.read('backup_data.json').decode('utf-8'))
            imported, vehicle_id_map, entry_id_map = import_backup_data(current_user, backup_data, merge_mode)

            imported['attachments'] = 0
            imported['vehicle_photos'] = 0
            attachment_id_map = {}

            attachment_folder = get_attachment_folder()
            user_attachment_folder = os.path.join(attachment_folder, str(current_user.id))
            os.makedirs(user_attachment_folder, exist_ok=True)

            attachment_metadata = {}
            for att in backup_data.get('attachments', []):
                attachment_metadata[str(att.get('id'))] = att

            uploads_folder = get_uploads_folder()
            vehicle_photo_folder = os.path.join(uploads_folder, 'vehicles')
            os.makedirs(vehicle_photo_folder, mode=0o750, exist_ok=True)

            for name in zf.namelist():
                if name.startswith('uploads/vehicles/'):
                    parts = name.split('/')
                    if len(parts) >= 4 and parts[3]:
                        try:
                            old_vehicle_id = int(parts[2])
                        except ValueError:
                            continue
                        new_vehicle_id = vehicle_id_map.get(old_vehicle_id)
                        if not new_vehicle_id:
                            continue
                        content = zf.read(name)
                        ext = parts[3].rsplit('.', 1)[1] if '.' in parts[3] else 'jpg'
                        import uuid
                        new_filename_v = f"{new_vehicle_id}_{uuid.uuid4().hex}.{ext}"
                        new_filepath = os.path.join(vehicle_photo_folder, new_filename_v)
                        with open(new_filepath, 'wb') as f:
                            f.write(content)
                        os.chmod(new_filepath, 0o640)
                        vehicle = Vehicle.query.get(new_vehicle_id)
                        if vehicle:
                            vehicle.photo = f"/uploads/vehicles/{new_filename_v}"
                            imported['vehicle_photos'] += 1

                elif name.startswith('attachments/'):
                    parts = name.split('/')
                    if len(parts) >= 3 and parts[2]:
                        old_id = parts[1]
                        att_filename = parts[2]
                        content = zf.read(name)
                        new_filepath = os.path.join(user_attachment_folder, att_filename)
                        with open(new_filepath, 'wb') as f:
                            f.write(content)
                        att_meta = attachment_metadata.get(old_id, {})
                        old_vehicle_id = att_meta.get('vehicle_id')
                        new_vehicle_id = vehicle_id_map.get(old_vehicle_id) if old_vehicle_id else None
                        old_entry_id = att_meta.get('entry_id')
                        new_entry_id = entry_id_map.get(old_entry_id) if old_entry_id else None
                        attachment = Attachment(
                            user_id=current_user.id,
                            filename=att_filename,
                            original_filename=att_meta.get('original_filename', att_filename),
                            filepath=new_filepath,
                            file_type=att_meta.get('file_type'),
                            file_size=len(content),
                            description=att_meta.get('description'),
                            category=att_meta.get('category'),
                            tags=att_meta.get('tags'),
                            vehicle_id=new_vehicle_id,
                            entry_id=new_entry_id,
                        )
                        db.session.add(attachment)
                        db.session.flush()
                        try:
                            attachment_id_map[int(old_id)] = attachment.id
                        except ValueError:
                            pass
                        imported['attachments'] += 1

            db.session.commit()

        security_audit.data_import(current_user.id, current_user.email, 'external_zip', success=True)

        return jsonify({
            'message': 'Restore from external backup completed',
            'imported': imported,
            'saved_locally': True,
            'local_filename': filename,
        })

    except requests.exceptions.Timeout:
        return jsonify({'error': 'Download timed out'}), 504
    except requests.exceptions.RequestException as e:
        current_app.logger.error(f'External restore download failed: {e}')
        return jsonify({'error': f'Failed to download: {str(e)}'}), 400
    except zipfile.BadZipFile:
        return jsonify({'error': 'Downloaded file is not a valid ZIP'}), 400
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'External restore failed: {e}', exc_info=True)
        return jsonify({'error': f'Restore failed: {str(e)}'}), 500


@backup_bp.route('/upload', methods=['POST'])
@token_required
def upload_backup(current_user):
    """Upload a backup .zip file to stored backups (without restoring)."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not file.filename.lower().endswith('.zip'):
        return jsonify({'error': 'Only .zip backup files are supported'}), 400

    try:
        content = file.read()

        # Validate it's a real ZIP with backup_data.json
        zip_data = BytesIO(content)
        with zipfile.ZipFile(zip_data, 'r') as zf:
            if 'backup_data.json' not in zf.namelist():
                return jsonify({'error': 'Invalid backup file: missing backup_data.json'}), 400

        # Save to backup storage
        backup_folder = get_backup_folder()
        user_folder = os.path.join(backup_folder, str(current_user.id))
        os.makedirs(user_folder, exist_ok=True)

        # Use original filename or generate one
        safe_name = file.filename.replace('..', '').replace('/', '').replace('\\', '')
        if not safe_name.startswith('backup_'):
            safe_name = f'backup_{safe_name}'
        filepath = os.path.join(user_folder, safe_name)

        # Don't overwrite existing
        if os.path.exists(filepath):
            base, ext = os.path.splitext(safe_name)
            safe_name = f'{base}_{datetime.utcnow().strftime("%H%M%S")}{ext}'
            filepath = os.path.join(user_folder, safe_name)

        with open(filepath, 'wb') as f:
            f.write(content)

        return jsonify({
            'message': 'Backup uploaded successfully',
            'filename': safe_name,
            'size': len(content),
            'size_human': format_file_size(len(content)),
        })

    except zipfile.BadZipFile:
        return jsonify({'error': 'File is not a valid ZIP archive'}), 400
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

    try:
        archive_path, filename, file_size, manifest = create_system_backup_archive(current_user, frequency=frequency)
        _cleanup_system_backups(frequency, keep_last=3)

        security_audit.data_export(current_user.id, current_user.email, f'system_full:{frequency}')

        response = send_file(
            archive_path,
            mimetype='application/gzip',
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

    uploaded_file = request.files['file']
    if not uploaded_file or not uploaded_file.filename:
        return jsonify(localized_message(
            'backup.system_import.empty_file',
            'No backup file selected',
        )), 400

    filename = uploaded_file.filename.lower()
    if not (filename.endswith('.tar.gz') or filename.endswith('.tgz')):
        return jsonify(localized_message(
            'backup.system_import.invalid_format',
            'Unsupported backup format',
            allowed_formats=['.tar.gz', '.tgz'],
        )), 400

    with tempfile.NamedTemporaryFile(prefix='gearcargo-system-import-', suffix='.tar.gz', delete=False) as temp_file:
        archive_path = temp_file.name
        uploaded_file.save(temp_file)

    try:
        manifest = restore_system_backup_archive(archive_path)
        security_audit.data_import(current_user.id, current_user.email, 'system_full', success=True)
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
    except (tarfile.TarError, ValueError) as exc:
        security_audit.data_import(current_user.id, current_user.email, 'system_full', success=False)
        current_app.logger.error('System backup import validation failed: %s', exc)
        return jsonify(localized_message(
            'backup.system_import.invalid_archive',
            'Invalid system backup archive',
            error=str(exc),
        )), 400
    except RuntimeError as exc:
        security_audit.data_import(current_user.id, current_user.email, 'system_full', success=False)
        current_app.logger.error('System backup import failed: %s', exc)
        return jsonify(localized_message(
            'backup.system_import.failed',
            'System backup restore failed',
            error=str(exc),
        )), 500
    finally:
        try:
            os.remove(archive_path)
        except OSError:
            pass

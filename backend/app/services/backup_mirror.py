"""A second copy of every finished backup, in a folder the operator mounts.

The app only copies files into BACKUP_MIRROR_FOLDER: it opens no connection, stores no
credentials and takes no address from anyone, so there is nothing to point at the home network.
"""
import contextlib
import errno
import io
import json
import os
import posixpath
import shutil
from datetime import timedelta
from pathlib import Path

from flask import current_app

from app.services import backup_encryption as backup_crypto
from app.services.backup_notices import notify_mirror_failing
from app.services.restore_transaction import digest, guarded_app_context
from app.utils.timeutils import isoformat_utc, naive_utc, utc_naive_now

# The operator creates this file on the mounted share. Without it nothing is written, so an
# unmounted share cannot make copies land on the server's own disk.
MIRROR_MARKER_NAME = '.gearcargo-backup-mirror'
STATUS_FILE_NAME = '.mirror-status.json'
ARTIFACT_SUFFIXES = ('.zip', '.gcb', '.tar.gz')
MIRROR_FOLDER_MODE = 0o700

STATE_WAITING = 'waiting'
STATE_CURRENT = 'current'
STATE_UNAVAILABLE = 'unavailable'
STATE_FAILED = 'failed'
FAILING_STATES = (STATE_UNAVAILABLE, STATE_FAILED)
# A storage that is off overnight is not worth a notice; a day without copies is.
NOTICE_DELAY = timedelta(hours=24)


def mirror_root():
    folder = current_app.config.get('BACKUP_MIRROR_FOLDER')
    return Path(folder) if folder else None


def _backup_root():
    return Path(current_app.config['BACKUP_FOLDER'])


def _is_mounted(mirror):
    return (mirror / MIRROR_MARKER_NAME).is_file()


def _is_artifact(path):
    return (not path.name.startswith('.') and path.name.lower().endswith(ARTIFACT_SUFFIXES)
            and not path.is_symlink())


def _artifacts(root):
    """Finished backup files under root by relative path, and the folders that could not be read."""
    found, unreadable = {}, []
    for directory, folder_names, file_names in os.walk(root, onerror=unreadable.append):
        folder_names[:] = [name for name in folder_names
                           if not name.startswith('.') and not Path(directory, name).is_symlink()]
        for path in (Path(directory, name) for name in file_names):
            if not _is_artifact(path):
                continue
            # Retention can rotate a file away while this listing runs.
            with contextlib.suppress(FileNotFoundError):
                found[path.relative_to(root).as_posix()] = path.stat()
    return found, [Path(failure.filename).relative_to(root).as_posix() for failure in unreadable]


def _mirror_path(mirror, relative):
    """Where a backup lives in the mirror; refused when a link would take it outside."""
    path = mirror / relative
    if mirror.resolve() not in path.resolve().parents:
        raise ValueError('Backup mirror path leaves its folder')
    return path


def _copy(source, target):
    target.parent.mkdir(mode=MIRROR_FOLDER_MODE, parents=True, exist_ok=True)
    with open(source, 'rb') as stream:
        backup_crypto.atomic_write(stream, target)
    original = source.stat()
    # Retention compares these times. A share that refuses to set them only prunes later.
    with contextlib.suppress(OSError):
        os.utime(target, ns=(original.st_atime_ns, original.st_mtime_ns))
    if digest(target) != digest(source):
        target.unlink()
        raise OSError('The mirrored backup does not match its original')


def _prune(mirror, local, mirrored):
    """Follow local retention without trusting an empty or damaged local folder.

    A copy goes only when its original is gone and it is older than every backup still kept
    locally in the same folder. A folder with no local backups left is never pruned.
    """
    oldest_kept = {}
    for relative, details in local.items():
        folder = posixpath.dirname(relative)
        oldest_kept[folder] = min(oldest_kept.get(folder, details.st_mtime_ns), details.st_mtime_ns)
    for relative, details in mirrored.items():
        oldest = oldest_kept.get(posixpath.dirname(relative))
        if relative in local or oldest is None or details.st_mtime_ns >= oldest:
            continue
        _mirror_path(mirror, relative).unlink(missing_ok=True)


def _synchronise(mirror):
    """Copy what the mirror lacks, then prune. Returns how many files were copied."""
    backups = _backup_root()
    local, unreadable_folders = _artifacts(backups)
    mirrored, _ = _artifacts(mirror)
    missing = [relative for relative, details in local.items()
               if relative not in mirrored or mirrored[relative].st_size != details.st_size]
    for relative in missing:
        _copy(backups / relative, _mirror_path(mirror, relative))
    _prune(mirror, local, _artifacts(mirror)[0])
    # Copy what can be read first, then say that something could not be.
    for folder in unreadable_folders:
        current_app.logger.warning('Backup mirror cannot read the backup folder %s', folder)
    if unreadable_folders:
        raise PermissionError(errno.EACCES, 'A backup folder is not readable')
    return len(missing)


def _status_path():
    return _backup_root() / STATUS_FILE_NAME


def _read_status():
    try:
        return json.loads(_status_path().read_text())
    except (OSError, ValueError):
        return {}


def _failure_streak(state, previous, now):
    """Since when copies have been failing, and whether the administrators have been told.

    `notified` turns true once the failure has lasted NOTICE_DELAY. Recovery drops both, so
    the next failure starts a new streak with its own notice.
    """
    if state not in FAILING_STATES:
        return {}
    failing_since = naive_utc(previous.get('failing_since')) or now
    return {'failing_since': isoformat_utc(failing_since),
            'notified': bool(previous.get('notified')) or now - failing_since >= NOTICE_DELAY}


def _record(state, copied=0):
    previous = _read_status()
    now = utc_naive_now()
    status = {'state': state,
              'last_copied_at': isoformat_utc(now) if copied else previous.get('last_copied_at'),
              **_failure_streak(state, previous, now)}
    if status == previous:
        return
    try:
        backup_crypto.atomic_write(io.BytesIO(json.dumps(status).encode()), _status_path())
    except OSError as failure:
        current_app.logger.warning('Backup mirror status could not be saved (%s)', type(failure).__name__)
        return
    # Only after the save: a status that cannot be written would repeat the notice on every run.
    if status.get('notified') and not previous.get('notified'):
        notify_mirror_failing()
    if copied:
        current_app.logger.info('Backup mirror: copied %s file(s)', copied)
    if state == previous.get('state'):
        return
    # WARNING at most: an ERROR would mark the scheduled job failed and eventually stop it.
    log = current_app.logger.info if state == STATE_CURRENT else current_app.logger.warning
    log('Backup mirror is now %s', state)


def mirror_backups(app):
    """Scheduled job. An unreachable or failing mirror becomes a state, never an exception."""
    with guarded_app_context(app):
        mirror = mirror_root()
        if mirror is None:
            return
        if not _is_mounted(mirror):
            _record(STATE_UNAVAILABLE)
            return
        try:
            copied = _synchronise(mirror)
        except (OSError, ValueError) as failure:
            current_app.logger.warning('Backup mirror copy failed (%s)', type(failure).__name__)
            _record(STATE_FAILED)
            return
        _record(STATE_CURRENT, copied)


def mirror_status():
    """What the Backup screen shows, or None when no mirror is configured. Never a path."""
    if mirror_root() is None:
        return None
    status = _read_status()
    return {'state': status.get('state', STATE_WAITING), 'last_copied_at': status.get('last_copied_at')}


def remove_mirrored_file(relative):
    """Best effort after a person deletes a stored backup. A copy that stays is pruned later."""
    mirror = mirror_root()
    if mirror is None or not _is_mounted(mirror):
        return
    try:
        _mirror_path(mirror, relative).unlink(missing_ok=True)
    except (OSError, ValueError) as failure:
        current_app.logger.warning('Backup mirror copy could not be removed (%s)', type(failure).__name__)


def remove_mirrored_account(user_id):
    """Remove a deleted account's copies. Raises OSError while the mirror is away, so cleanup retries."""
    mirror = mirror_root()
    if mirror is None:
        return
    if not _is_mounted(mirror):
        raise OSError('Backup mirror is unavailable')
    folder = _mirror_path(mirror, str(user_id))
    if folder.is_dir():
        shutil.rmtree(folder)

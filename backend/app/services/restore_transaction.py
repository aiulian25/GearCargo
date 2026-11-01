"""Durable restore coordination (journal v1), on the shared backup volume.

A filesystem switch and SQL commit are not one atomic operation. Files are
durable before commit; an AppSetting marker in that same transaction resolves
the commit/crash ambiguity. An unfinished journal excludes application activity
until recovery either retains the committed state or restores the previous one.
"""
from contextlib import contextmanager
from functools import wraps
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import threading
import uuid

from flask import current_app, g, jsonify, request
from sqlalchemy import text

from app import db

JOURNAL_VERSION = 1
DB_LOCK = 1768389421
_local = threading.local()
_open_fds = set()
_fd_lock = threading.Lock()


def _after_fork_child():
    # Gunicorn preloads while the master's scheduler can hold a lease. Inherited
    # flock descriptions must not keep that lease alive in every worker forever.
    global _fd_lock
    for fd in _open_fds:
        os.close(fd)
    _open_fds.clear()
    _local.leases = {}
    _fd_lock = threading.Lock()


def _before_fork():
    _fd_lock.acquire()


def _after_fork_parent():
    _fd_lock.release()


os.register_at_fork(before=_before_fork, after_in_parent=_after_fork_parent,
                    after_in_child=_after_fork_child)


class RestoreBusy(RuntimeError):
    pass


class RestoreFailure(RuntimeError):
    def __init__(self, restore_id, state):
        self.restore_id, self.state = restore_id, state
        super().__init__('Restore failed; previous data was restored.' if state == 'rolled_back'
                         else 'Restore requires recovery. Application data is temporarily unavailable.')


def state_root():
    return Path(current_app.config.get('RESTORE_STATE_FOLDER') or
                Path(current_app.config['BACKUP_FOLDER']) / '.restore')


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_bytes(path, data):
    path = Path(path)
    with path.open('xb') as stream:
        os.chmod(path, 0o600)
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    sync_dir(path.parent)


def atomic_json(path, data):
    temporary = path.with_suffix('.tmp')
    with temporary.open('w') as stream:
        os.chmod(temporary, 0o600)
        json.dump(data, stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    sync_dir(path.parent)


def digest(path):
    value = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


@contextmanager
def activity_guard(*, exclusive=False, pending=False, blocking=False):
    """Reentrant within a thread; flock coordinates workers and background jobs.

    Never upgrade a shared lease: two upgraders can deadlock or lose exclusion.
    Restore HTTP routes acquire their exclusive lease before authentication.
    """
    root = state_root()
    key = (os.getpid(), str(root))
    leases = getattr(_local, 'leases', {})
    _local.leases = leases
    if key in leases:
        if exclusive and not leases[key][1]:
            raise RestoreBusy('Restore needs exclusive application access. Retry shortly.')
        yield
        return
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with _fd_lock:
        fd = os.open(root / 'lock', os.O_CREAT | os.O_RDWR, 0o600)
        _open_fds.add(fd)
    try:
        try:
            fcntl.flock(fd, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) |
                        (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError:
            raise RestoreBusy('Restore maintenance is active. Retry shortly.') from None
        if not pending and (root / 'active.json').exists():
            raise RestoreBusy('An interrupted restore requires recovery before data can be used.')
        leases[key] = (fd, exclusive)
        try:
            yield
        finally:
            leases.pop(key, None)
    finally:
        with _fd_lock:
            _open_fds.discard(fd)
            os.close(fd)


@contextmanager
def guarded_app_context(app):
    """Background work holds a shared lease for its entire read/write operation."""
    with app.app_context():
        with activity_guard(blocking=True):
            yield


def background_activity(function):
    @wraps(function)
    def guarded(app, *args, **kwargs):
        with guarded_app_context(app):
            return function(app, *args, **kwargs)
    return guarded


def checkpoint(name, journal):
    """Fault-injection seam; production performs no action."""


class Journal:
    def __init__(self, data):
        self.data = data
        self.root = state_root()
        self.directory = self.root / data['id']

    @classmethod
    def create(cls, kind):
        journal = cls({'version': JOURNAL_VERSION, 'id': uuid.uuid4().hex,
                       'kind': kind, 'phase': 'validating', 'areas': [], 'files': [],
                       'directories': [], 'db_started': False, 'process': None})
        journal.directory.mkdir(mode=0o700)
        journal.save()
        return journal

    @property
    def marker(self):
        return 'restore_commit_' + self.data['id']

    def save(self, phase=None):
        if phase:
            self.data['phase'] = phase
        atomic_json(self.root / 'active.json', self.data)

    def area(self, root):
        root = Path(root).absolute()
        if root.is_symlink():
            raise ValueError('Restore media root cannot be a symbolic link.')
        resolved, journal_root = root.resolve(), self.root.resolve()
        if resolved == journal_root or resolved in journal_root.parents or journal_root in resolved.parents:
            raise ValueError('Restore media and journal storage must be separate.')
        root.mkdir(parents=True, exist_ok=True)
        path = root / ('.gc-restore-' + self.data['id'])
        if str(path) not in self.data['areas']:
            self.data['areas'].append(str(path))
            self.save()
            path.mkdir(mode=0o700)
            sync_dir(root)
        return path

    def stage_file(self, content, destination):
        destination = Path(destination).absolute()
        area = self.area(destination.parent)
        staged = area / uuid.uuid4().hex
        write_bytes(staged, content)
        os.chmod(staged, 0o640)
        # Persist mode as well as contents before publication.
        with staged.open('rb') as stream:
            os.fsync(stream.fileno())
        self.data['files'].append({'staged': str(staged), 'path': str(destination),
                                   'sha256': hashlib.sha256(content).hexdigest()})
        self.save('staging')

    def publish_files(self):
        self.save('publishing_files')
        for index, item in enumerate(self.data['files']):
            checkpoint(f'before_file_{index}', self)
            # link is atomic and refuses to overwrite a pre-existing filename.
            os.link(item['staged'], item['path'])
            sync_dir(Path(item['path']).parent)
            checkpoint(f'after_file_{index}', self)

    def stage_directory(self, source, destination, budget=None):
        destination = Path(destination).absolute()
        for item in self.data['directories']:
            other = Path(item['root']).resolve()
            here = destination.resolve()
            if here == other or here in other.parents or other in here.parents:
                raise ValueError('System restore media roots must not overlap.')
        area = self.area(destination)
        new, old = area / 'new', area / 'old'
        shutil.copytree(source, new, copy_function=budget.copy if budget else shutil.copy2)
        old.mkdir()
        inventory = {}
        for path in new.rglob('*'):
            if budget:
                budget.remaining()
            if path.is_symlink():
                raise ValueError('Restore media cannot contain symbolic links.')
            if path.is_file():
                os.chmod(path, 0o640)
                with path.open('rb') as stream:
                    os.fsync(stream.fileno())
                inventory[str(path.relative_to(new))] = budget.digest(path) if budget else digest(path)
        for directory in sorted([p for p in new.rglob('*') if p.is_dir()], reverse=True):
            sync_dir(directory)
        sync_dir(new); sync_dir(old); sync_dir(area)
        # Keep mount-point roots in place; journal each top-level rename.
        self.data['directories'].append({
            'root': str(destination), 'area': str(area),
            'old_names': sorted(p.name for p in destination.iterdir() if p != area),
            'new_names': sorted(p.name for p in new.iterdir()), 'inventory': inventory,
        })
        self.save('staging')

    def publish_directories(self):
        self.save('publishing_directories')
        for index, item in enumerate(self.data['directories']):
            checkpoint(f'before_directory_{index}', self)
            root, area = Path(item['root']), Path(item['area'])
            for name in item['old_names']:
                os.rename(root / name, area / 'old' / name)
                sync_dir(root); sync_dir(area / 'old')
                checkpoint(f'after_old_move_{index}', self)
            for name in item['new_names']:
                os.rename(area / 'new' / name, root / name)
                sync_dir(root); sync_dir(area / 'new')
                checkpoint(f'after_new_move_{index}', self)
            checkpoint(f'after_directory_{index}', self)

    def mark_transaction(self):
        from app.models import AppSetting
        db.session.add(AppSetting(key=self.marker, value=self.data['kind']))


def lock_database_transaction():
    if db.engine.dialect.name == 'postgresql':
        db.session.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': DB_LOCK})


def _committed(journal):
    # A fresh connection plus transaction lock waits for any former writer's
    # commit/rollback before resolving an ambiguous disconnect during commit.
    db.session.rollback()
    with db.engine.begin() as connection:
        if connection.dialect.name == 'postgresql':
            connection.execute(text("SET LOCAL lock_timeout = '10s'"))
            connection.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': DB_LOCK})
        elif connection.dialect.name == 'sqlite':
            connection.exec_driver_sql('BEGIN IMMEDIATE')
        return connection.execute(text('SELECT value FROM app_settings WHERE key = :key'),
                                  {'key': journal.marker}).scalar() == journal.data['kind']


def process_identity(pid):
    try:
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(') ', 1)[1].split()
        return {'pid': pid, 'start': fields[19],
                'boot': Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
    except FileNotFoundError:
        return None


def _stop_interrupted_process(journal):
    child = journal.data.get('process')
    if child and process_identity(child['pid']) == child:
        os.kill(child['pid'], signal.SIGKILL)
    if journal.data['kind'] == 'system' and db.engine.dialect.name == 'postgresql':
        # The SQL process can survive a web-worker crash. Terminate its server
        # session before waiting on the transaction advisory lock in _committed.
        with db.engine.begin() as connection:
            connection.execute(text('SELECT pg_terminate_backend(pid) FROM pg_stat_activity '
                'WHERE application_name = :name AND pid <> pg_backend_pid()'),
                {'name': 'gearcargo-restore-' + journal.data['id']})


def _verify_published(journal):
    for item in journal.data['files']:
        if digest(item['path']) != item['sha256']:
            raise RuntimeError('Published restore file failed verification.')
    for item in journal.data['directories']:
        for relative, expected in item['inventory'].items():
            if digest(Path(item['root']) / relative) != expected:
                raise RuntimeError('Published restore directory failed verification.')


def _rollback_media(journal):
    for item in reversed(journal.data['files']):
        path, staged = Path(item['path']), Path(item['staged'])
        # The retained hardlink identifies files this operation published.
        if path.exists() and staged.exists() and os.path.samefile(path, staged):
            path.unlink()
            sync_dir(path.parent)
    for item in reversed(journal.data['directories']):
        root, area = Path(item['root']), Path(item['area'])
        for name in item['new_names']:
            if not (area / 'new' / name).exists() and (root / name).exists():
                os.rename(root / name, area / 'new' / name)
                sync_dir(root); sync_dir(area / 'new')
        for name in item['old_names']:
            if (area / 'old' / name).exists():
                if (root / name).exists():
                    raise RuntimeError('Recovery destination unexpectedly exists.')
                os.rename(area / 'old' / name, root / name)
                sync_dir(root); sync_dir(area / 'old')


def _cleanup(journal, outcome):
    # Outcome is durable before cleanup. Recovery can repeat partial cleanup.
    journal.save(outcome)
    if journal.data.get('staging_database'):
        from app.routes.backup import _drop_restore_database
        _drop_restore_database(journal.data['staging_database'])
    for area in journal.data['areas']:
        if Path(area).exists():
            shutil.rmtree(area)
            sync_dir(Path(area).parent)
    if journal.directory.exists():
        shutil.rmtree(journal.directory)
    (journal.root / 'active.json').unlink()
    sync_dir(journal.root)
    # A stale marker is harmless; never turn completed recovery into failure
    # merely because optional marker garbage collection is unavailable.
    try:
        with db.engine.begin() as connection:
            connection.execute(text('DELETE FROM app_settings WHERE key = :key'), {'key': journal.marker})
    except Exception:
        current_app.logger.warning('Restore completed; commit-marker cleanup deferred.')


def recover(journal):
    """Idempotent recovery. Caller must hold the exclusive application lease."""
    db.session.rollback()
    _stop_interrupted_process(journal)
    phase = journal.data['phase']
    if phase in ('completed', 'rolled_back'):
        _cleanup(journal, phase)
        return phase
    committed = _committed(journal) if journal.data['db_started'] else False
    if committed:
        _verify_published(journal)
        _cleanup(journal, 'completed')
        return 'completed'
    journal.save('rolling_back')
    if journal.data['kind'] == 'system' and journal.data['db_started']:
        from app.routes.backup import _restore_pg_dump_file
        snapshot = journal.directory / 'previous.sql.gz'
        if digest(snapshot) != journal.data['previous_database_sha256']:
            raise RuntimeError('Previous database snapshot failed verification.')
        _restore_pg_dump_file(snapshot, journal=journal)
    _rollback_media(journal)
    _cleanup(journal, 'rolled_back')
    return 'rolled_back'


def recover_unfinished():
    with activity_guard(exclusive=True, pending=True):
        path = state_root() / 'active.json'
        if not path.exists():
            return 'idle'
        data = json.loads(path.read_text())
        if data.get('version') != JOURNAL_VERSION or not isinstance(data.get('id'), str) or \
                len(data['id']) != 32 or any(c not in '0123456789abcdef' for c in data['id']):
            raise RuntimeError('Unsupported or invalid restore journal; operator recovery required.')
        _validate_journal_paths(data)
        return recover(Journal(data))


def _validate_journal_paths(data):
    """Fail closed on damaged journal paths instead of guessing cleanup targets."""
    from app.routes.backup import get_attachment_folder, get_uploads_folder
    roots = [Path(get_attachment_folder()).resolve(), Path(get_uploads_folder()).resolve()]
    try:
        if data['kind'] not in ('personal', 'system') or type(data['db_started']) is not bool:
            raise ValueError()
        if data['phase'] not in {'validating', 'validating_database', 'snapshotting', 'staging',
                'importing', 'publishing_files', 'publishing_directories', 'applying_database',
                'committing', 'rolling_back', 'completed', 'rolled_back'}:
            raise ValueError()
        if data.get('staging_database') not in (None, 'gc_restore_' + data['id']):
            raise ValueError()
        areas = {Path(path) for path in data['areas']}
        for area in areas:
            if not area.is_absolute() or area.name != '.gc-restore-' + data['id'] or area.is_symlink():
                raise ValueError()
            parent = area.parent.resolve()
            if not any(parent == root or root in parent.parents for root in roots):
                raise ValueError()
        for item in data['files']:
            stage, final = Path(item['staged']), Path(item['path'])
            if stage.parent not in areas or not final.is_absolute() or final.parent != stage.parent.parent:
                raise ValueError()
        for item in data['directories']:
            area, root = Path(item['area']), Path(item['root'])
            if area not in areas or area.parent != root or root.resolve() not in roots:
                raise ValueError()
            for name in item['old_names'] + item['new_names']:
                if name in ('', '.', '..', area.name) or Path(name).name != name:
                    raise ValueError()
            for relative in item['inventory']:
                if Path(relative).is_absolute() or '..' in Path(relative).parts:
                    raise ValueError()
    except (KeyError, TypeError, ValueError):
        raise RuntimeError('Restore journal paths are invalid; operator recovery required.') from None


def recovery_status():
    path = state_root() / 'active.json'
    if path.exists():
        try:
            phase = json.loads(path.read_text())['phase']
        except (ValueError, KeyError, OSError):
            phase = 'recovery_required'
        try:
            with activity_guard(exclusive=True, pending=True):
                # Journal exists but no restore/recovery process owns the lock.
                # Do not present a crashed or failed recovery as ongoing work.
                phase = 'recovery_required'
        except RestoreBusy:
            pass
        return {'maintenance': True, 'phase': phase}
    try:
        with activity_guard():
            return {'maintenance': False, 'phase': 'idle'}
    except RestoreBusy:
        return {'maintenance': True, 'phase': 'validating'}


def init_restore_coordination(app):
    """Gate requests before auth writes; install explicit operator recovery."""
    def enter():
        if request.path == '/api/backup/recovery-status' or not (
                request.path.startswith('/api/') or request.path.startswith('/uploads/')):
            return
        exclusive = request.path in {'/api/backup/import', '/api/backup/import/lubelog', '/api/backup/system/import',
                                      '/api/backup/external/restore'} or request.path.startswith('/api/backup/restore/')
        # Permanent deletion and its cleanup also need write exclusion, before auth writes.
        exclusive = exclusive or (request.method == 'DELETE' and (
            request.endpoint in {'admin.delete_user', 'attachments.delete_attachment'} or (request.endpoint == 'vehicles.delete_vehicle'
            and request.args.get('hard', 'false').lower() == 'true')))
        lease = activity_guard(exclusive=exclusive)
        try:
            lease.__enter__()
        except RestoreBusy as exc:
            return jsonify(error=str(exc), recovery={'state': 'maintenance', **recovery_status()}), 503, {'Retry-After': '5'}
        g._restore_activity_lease = lease

    app.before_request_funcs.setdefault(None, []).insert(0, enter)

    @app.teardown_request
    def leave(_error):
        lease = g.pop('_restore_activity_lease', None)
        if lease:
            lease.__exit__(None, None, None)

    @app.get('/api/backup/recovery-status')
    def public_restore_status():
        # No account data, filenames, credentials or DB access during cutover.
        return jsonify(recovery_status())

    @app.cli.command('recover-restores')
    def recover_command():
        import click
        click.echo(recover_unfinished())


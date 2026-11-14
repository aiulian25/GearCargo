"""GC-117: every finished backup also exists in a folder the operator mounts.

The copy is verified, follows local retention without trusting an empty local folder, and an
unreachable or failing mirror becomes a visible state rather than a stopped scheduled job.
"""
import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import db
from app.models import DeletionTask, ScheduledEffect, User
from app.services import backup_mirror
from app.services.backup_mirror import (
    MIRROR_MARKER_NAME, NOTICE_DELAY, STATE_CURRENT, STATE_FAILED, STATE_UNAVAILABLE, STATE_WAITING,
    STATUS_FILE_NAME, mirror_backups,
)
from app.services.backup_notices import MIRROR_FAILING, NOTICE_TAG_PREFIX, NOTICE_TEXT
from app.services.deletion import MIRROR_ACCOUNT_TASK, cleanup_pending, delete_owned_data
from app.services.scheduled_effects import process_scheduled_effects
from app.services.scheduler_ownership import run_due_job
from app.services.scheduler_registry import BACKUP_MIRROR_INTERVAL_SECONDS, job_definitions
from app.utils.timeutils import isoformat_utc, utc_naive_now
from tests.test_scheduler_coordination import definition

SECONDS_PER_DAY = 86400
STATUS_URL = '/api/backup/status'
FIRST_RUN = datetime(2026, 11, 14, 3, 0)


@pytest.fixture()
def mirror(app, tmp_path):
    folder = tmp_path / 'mirror'
    folder.mkdir()
    (folder / MIRROR_MARKER_NAME).touch()
    app.config['BACKUP_MIRROR_FOLDER'] = str(folder)
    return folder


def _backups(app):
    return Path(app.config['BACKUP_FOLDER'])


def _write(path, content=b'archive bytes', age_days=0):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    stamp = time.time() - age_days * SECONDS_PER_DAY
    os.utime(path, (stamp, stamp))
    return path


def _files(folder):
    return sorted(path.relative_to(folder).as_posix() for path in folder.rglob('*') if path.is_file())


def _status(app):
    return json.loads((_backups(app) / STATUS_FILE_NAME).read_text())


@pytest.fixture()
def clock(monkeypatch):
    """The mirror job's idea of now, moved by hand."""
    moment = SimpleNamespace(now=FIRST_RUN)
    monkeypatch.setattr(backup_mirror, 'utc_naive_now', lambda: moment.now)
    return moment


def _run_after(app, clock, elapsed):
    clock.now = FIRST_RUN + elapsed
    mirror_backups(app)


def _administrator(name='operator', **fields):
    account = User(username=name, email=f'{name}@example.com', password_hash='not a login', is_admin=True, **fields)
    db.session.add(account)
    db.session.commit()
    return account.id


def test_without_the_setting_nothing_is_copied_and_the_screen_gets_no_mirror(app, client, user, auth_headers, tmp_path):
    _write(_backups(app) / '1' / 'personal.zip')

    mirror_backups(app)

    assert not (_backups(app) / STATUS_FILE_NAME).exists()
    assert client.get(STATUS_URL, headers=auth_headers(user.id)).json['mirror'] is None
    assert 'backup_mirror' not in job_definitions(app)


def test_the_job_is_scheduled_only_when_a_mirror_is_configured(app, mirror):
    definition = job_definitions(app)['backup_mirror']

    assert definition.function is mirror_backups
    assert definition.seconds == BACKUP_MIRROR_INTERVAL_SECONDS


def test_an_unmounted_share_gets_nothing_written_and_reports_unavailable(app, mirror):
    (mirror / MIRROR_MARKER_NAME).unlink()
    _write(_backups(app) / '1' / 'personal.zip')

    mirror_backups(app)

    assert _files(mirror) == []
    assert (_status(app)['state'], _status(app)['last_copied_at']) == (STATE_UNAVAILABLE, None)


def test_personal_and_system_backups_are_copied_in_their_layout_and_nothing_else(app, mirror, tmp_path):
    backups = _backups(app)
    originals = {
        '1/GearCargo_driver_20261109_030000_scheduled.zip': b'personal plaintext',
        '1/GearCargo_driver_20261110_030000_scheduled.zip.gcb': b'personal encrypted',
        'system/daily/gearcargo_daily_20261110_030000.tar.gz': b'system daily',
        'system/weekly/gearcargo_weekly_20261108_033000.tar.gz.gcb': b'system weekly encrypted',
        'system/gearcargo_system_backup_manual_20261110_120000.tar.gz': b'manual export',
    }
    for relative, content in originals.items():
        _write(backups / relative, content)
    _write(backups / '.restore' / 'journal.tar.gz')
    _write(backups / '1' / '.backup-abc.partial')
    _write(backups / 'system' / 'daily' / 'gearcargo_daily_20261111_030000.tar.gz.partial.x1')
    _write(backups / '1' / 'notes.txt')
    (backups / '1' / 'linked.zip').symlink_to(_write(tmp_path / 'outside' / 'secret.zip'))

    mirror_backups(app)

    assert _files(mirror) == sorted([MIRROR_MARKER_NAME, *originals])
    for relative, content in originals.items():
        assert (mirror / relative).read_bytes() == content
        assert (mirror / relative).stat().st_mtime_ns == (backups / relative).stat().st_mtime_ns
    assert _status(app)['state'] == STATE_CURRENT
    assert _status(app)['last_copied_at']


def test_a_second_run_copies_nothing_and_leaves_the_status_alone(app, mirror):
    _write(_backups(app) / '1' / 'personal.zip')
    mirror_backups(app)
    first_status, first_copy = _status(app), (mirror / '1' / 'personal.zip').stat()
    status_written_at = (_backups(app) / STATUS_FILE_NAME).stat().st_mtime_ns

    mirror_backups(app)

    assert _status(app) == first_status
    assert (_backups(app) / STATUS_FILE_NAME).stat().st_mtime_ns == status_written_at
    assert (mirror / '1' / 'personal.zip').stat().st_ino == first_copy.st_ino


def test_a_truncated_copy_is_replaced(app, mirror):
    _write(_backups(app) / '1' / 'personal.zip', b'the complete archive')
    _write(mirror / '1' / 'personal.zip', b'the comp')

    mirror_backups(app)

    assert (mirror / '1' / 'personal.zip').read_bytes() == b'the complete archive'


def test_a_copy_that_fails_its_checksum_is_removed_and_reported(app, mirror, monkeypatch):
    _write(_backups(app) / '1' / 'personal.zip')
    monkeypatch.setattr(backup_mirror, 'digest', lambda path: str(path))

    mirror_backups(app)

    assert _files(mirror) == [MIRROR_MARKER_NAME]
    assert (_status(app)['state'], _status(app)['last_copied_at']) == (STATE_FAILED, None)


def test_the_mirror_follows_local_retention_without_trusting_a_missing_original(app, mirror):
    backups = _backups(app)
    _write(backups / 'system' / 'daily' / 'day2.tar.gz', age_days=2)
    _write(backups / 'system' / 'daily' / 'day1.tar.gz', age_days=1)
    _write(mirror / 'system' / 'daily' / 'day5.tar.gz', age_days=5)
    _write(mirror / 'system' / 'daily' / 'today.tar.gz', age_days=0)
    _write(mirror / '7' / 'departed.zip', age_days=30)

    mirror_backups(app)

    # Rotated out locally: gone. Newer than every local backup, or in a folder with none: kept.
    assert _files(mirror) == [MIRROR_MARKER_NAME, '7/departed.zip', 'system/daily/day1.tar.gz',
                              'system/daily/day2.tar.gz', 'system/daily/today.tar.gz']


def test_a_failing_copy_reports_failed_keeps_the_originals_and_the_next_run_recovers(app, mirror, monkeypatch):
    original = _write(_backups(app) / '1' / 'personal.zip', b'kept')
    logged = []
    handler = logging.Handler()
    handler.emit = logged.append
    app.logger.addHandler(handler)
    write = backup_mirror.backup_crypto.atomic_write

    def full_mirror(source, destination):
        if mirror in Path(destination).parents:
            raise OSError('No space left on device')
        write(source, destination)

    with monkeypatch.context() as broken:
        broken.setattr(backup_mirror.backup_crypto, 'atomic_write', full_mirror)
        mirror_backups(app)

    assert _status(app)['state'] == STATE_FAILED
    assert original.read_bytes() == b'kept'
    # An ERROR record would mark the scheduled job failed and stop it after five attempts.
    assert logged and all(record.levelno < logging.ERROR for record in logged)

    mirror_backups(app)
    app.logger.removeHandler(handler)

    assert _status(app)['state'] == STATE_CURRENT
    assert (mirror / '1' / 'personal.zip').read_bytes() == b'kept'


def test_a_status_that_cannot_be_saved_never_fails_the_scheduled_job(app, mirror, monkeypatch):
    _write(_backups(app) / '1' / 'personal.zip')

    def full_server_disk(_source, _destination):
        raise OSError('No space left on device')

    monkeypatch.setattr(backup_mirror.backup_crypto, 'atomic_write', full_server_disk)

    mirror_backups(app)

    assert not (_backups(app) / STATUS_FILE_NAME).exists()


@pytest.mark.skipif(os.geteuid() == 0, reason='root can read every folder')
def test_a_backup_folder_the_application_cannot_read_is_reported_not_skipped(app, mirror):
    """`run-backup.sh manual` started as root used to leave exactly this behind."""
    _write(_backups(app) / '1' / 'personal.zip')
    locked = _write(_backups(app) / 'system' / 'manual' / 'manual.tar.gz').parent
    logged = []
    handler = logging.Handler()
    handler.emit = logged.append
    app.logger.addHandler(handler)
    locked.chmod(0o000)
    try:
        mirror_backups(app)
    finally:
        locked.chmod(0o700)

    assert _files(mirror) == [MIRROR_MARKER_NAME, '1/personal.zip']
    assert _status(app)['state'] == STATE_FAILED
    assert 'system/manual' in ' '.join(record.getMessage() for record in logged)

    mirror_backups(app)
    app.logger.removeHandler(handler)

    assert _status(app)['state'] == STATE_CURRENT
    assert (mirror / 'system' / 'manual' / 'manual.tar.gz').exists()


def test_administrators_are_told_once_after_a_day_of_failures(app, mirror, user, clock, sent_pushes):
    """GC-119. The ordinary account, the muted and the deactivated administrator hear nothing."""
    operator = _administrator()
    _administrator('muted', notifications_enabled=False)
    _administrator('departed', is_active=False)
    (mirror / MIRROR_MARKER_NAME).unlink()

    _run_after(app, clock, timedelta(0))
    _run_after(app, clock, NOTICE_DELAY - timedelta(minutes=1))
    assert sent_pushes == []

    _run_after(app, clock, NOTICE_DELAY)
    _run_after(app, clock, NOTICE_DELAY * 3)

    title, body = NOTICE_TEXT[MIRROR_FAILING]['en']
    assert [(push['user_id'], push['title'], push['body'], push['tag']) for push in sent_pushes] == [
        (operator, title, body, NOTICE_TAG_PREFIX + MIRROR_FAILING)]
    assert _status(app)['notified'] is True


def test_recovery_ends_the_streak_and_a_new_failure_is_announced_again(app, mirror, user, clock, sent_pushes):
    _administrator()
    marker = mirror / MIRROR_MARKER_NAME
    marker.unlink()
    _run_after(app, clock, timedelta(0))
    _run_after(app, clock, NOTICE_DELAY)
    marker.touch()
    _run_after(app, clock, NOTICE_DELAY + timedelta(hours=1))

    assert _status(app) == {'state': STATE_CURRENT, 'last_copied_at': None}
    assert len(sent_pushes) == 1

    marker.unlink()
    _run_after(app, clock, NOTICE_DELAY + timedelta(hours=2))
    _run_after(app, clock, NOTICE_DELAY * 2 + timedelta(hours=1))
    assert len(sent_pushes) == 1

    _run_after(app, clock, NOTICE_DELAY * 2 + timedelta(hours=2))
    assert len(sent_pushes) == 2


def test_unreachable_and_failed_runs_count_as_one_streak(app, mirror, user, clock, sent_pushes, monkeypatch):
    _administrator()
    _write(_backups(app) / '1' / 'personal.zip')
    marker = mirror / MIRROR_MARKER_NAME
    marker.unlink()
    _run_after(app, clock, timedelta(0))
    marker.touch()
    monkeypatch.setattr(backup_mirror, 'digest', lambda path: str(path))
    _run_after(app, clock, NOTICE_DELAY / 2)
    assert _status(app)['state'] == STATE_FAILED

    _run_after(app, clock, NOTICE_DELAY)

    assert len(sent_pushes) == 1


def test_the_notice_waits_for_a_status_that_can_be_saved(app, mirror, user, clock, sent_pushes, monkeypatch):
    """Sent before the save, a full server disk would repeat it every quarter of an hour."""
    _administrator()
    (mirror / MIRROR_MARKER_NAME).unlink()
    _run_after(app, clock, timedelta(0))

    def full_server_disk(_source, _destination):
        raise OSError('No space left on device')

    with monkeypatch.context() as broken:
        broken.setattr(backup_mirror.backup_crypto, 'atomic_write', full_server_disk)
        _run_after(app, clock, NOTICE_DELAY)
    assert sent_pushes == []

    _run_after(app, clock, NOTICE_DELAY + timedelta(seconds=BACKUP_MIRROR_INTERVAL_SECONDS))

    assert len(sent_pushes) == 1


def test_a_notice_that_cannot_be_sent_never_fails_the_copy_job(app, mirror, user, clock, monkeypatch):
    _administrator()
    (mirror / MIRROR_MARKER_NAME).unlink()
    _run_after(app, clock, timedelta(0))

    def unreachable_push_service(*_arguments, **_options):
        raise RuntimeError('push service down')

    monkeypatch.setattr('app.routes.push.send_push_to_user', unreachable_push_service)

    _run_after(app, clock, NOTICE_DELAY)

    assert _status(app)['notified'] is True


def test_the_scheduled_job_queues_the_notice_and_the_delivery_job_sends_it(app, mirror, user, monkeypatch):
    operator = _administrator()
    (mirror / MIRROR_MARKER_NAME).unlink()
    (_backups(app) / STATUS_FILE_NAME).write_text(json.dumps({
        'state': STATE_UNAVAILABLE, 'last_copied_at': None,
        'failing_since': isoformat_utc(utc_naive_now() - NOTICE_DELAY), 'notified': False}))

    assert run_due_job(app, 'backup_mirror', definition(app, mirror_backups, name='backup_mirror'))

    queued = ScheduledEffect.query.one()
    assert (queued.kind, queued.user_id, queued.status) == ('push', operator, 'pending')

    delivered = []
    monkeypatch.setattr('app.routes.push.send_push_to_user',
                        lambda user_id, title, body, data=None, tag=None: delivered.append((user_id, tag)) or 1)
    assert run_due_job(app, 'scheduled_deliveries',
                       definition(app, process_scheduled_effects, name='scheduled_deliveries'))

    assert delivered == [(operator, NOTICE_TAG_PREFIX + MIRROR_FAILING)]
    db.session.expire_all()
    assert ScheduledEffect.query.one().status == 'sent'


def test_a_link_inside_the_mirror_cannot_send_a_copy_outside_it(app, mirror, tmp_path):
    outside = tmp_path / 'outside'
    outside.mkdir()
    (mirror / 'system').symlink_to(outside, target_is_directory=True)
    _write(_backups(app) / 'system' / 'daily' / 'day1.tar.gz')

    mirror_backups(app)

    assert _files(outside) == []
    assert _status(app)['state'] == STATE_FAILED


def test_the_backup_screen_gets_the_state_and_never_the_path(app, client, user, auth_headers, mirror):
    headers = auth_headers(user.id)

    assert client.get(STATUS_URL, headers=headers).json['mirror'] == {'state': STATE_WAITING, 'last_copied_at': None}
    _write(_backups(app) / str(user.id) / 'personal.zip')
    mirror_backups(app)
    response = client.get(STATUS_URL, headers=headers)

    assert response.json['mirror'] == {'state': STATE_CURRENT, 'last_copied_at': _status(app)['last_copied_at']}
    assert str(mirror) not in response.get_data(as_text=True)


def test_deleting_a_stored_backup_also_removes_its_copy(app, client, user, auth_headers, mirror):
    _write(_backups(app) / str(user.id) / 'personal.zip')
    _write(_backups(app) / str(user.id) / 'kept.zip')
    mirror_backups(app)

    response = client.delete('/api/backup/delete/personal.zip', headers=auth_headers(user.id))

    assert response.status_code == 200, response.json
    assert _files(mirror) == [MIRROR_MARKER_NAME, f'{user.id}/kept.zip']


def _mirror_tasks():
    return DeletionTask.query.filter_by(kind=MIRROR_ACCOUNT_TASK).all()


def test_deleting_an_account_removes_its_copies_once_the_mirror_is_reachable(app, user, mirror):
    user_id = user.id
    _write(_backups(app) / str(user_id) / 'personal.zip')
    _write(_backups(app) / '999' / 'neighbour.zip')
    mirror_backups(app)
    (mirror / MIRROR_MARKER_NAME).unlink()

    operation_id = delete_owned_data(user_id)
    cleanup_pending(operation_id)

    assert [task.payload for task in _mirror_tasks()] == [{'user_id': user_id}]
    assert (mirror / str(user_id) / 'personal.zip').exists()

    (mirror / MIRROR_MARKER_NAME).touch()
    cleanup_pending(operation_id)
    db.session.expire_all()

    assert _mirror_tasks() == []
    assert _files(mirror) == [MIRROR_MARKER_NAME, '999/neighbour.zip']

    mirror_backups(app)

    # GC-120: this backup had no record. Left on the server, it would be copied back here.
    assert _files(mirror) == [MIRROR_MARKER_NAME, '999/neighbour.zip']


def test_the_copies_of_a_deleted_account_wait_for_its_local_backups(app, user, mirror):
    """Removed first, they would return with the next run while a local file is still pending."""
    user_id = user.id
    local = _write(_backups(app) / str(user_id) / 'personal.zip')
    mirror_backups(app)
    operation_id = delete_owned_data(user_id)
    local.write_bytes(b'changed after the deletion was recorded')

    cleanup_pending(operation_id)

    assert local.exists()
    assert (mirror / str(user_id) / 'personal.zip').exists()
    assert len(_mirror_tasks()) == 1

    local.unlink()
    cleanup_pending(operation_id)
    mirror_backups(app)
    db.session.expire_all()

    assert _mirror_tasks() == []
    assert _files(mirror) == [MIRROR_MARKER_NAME]


def test_copies_whose_originals_were_rotated_away_go_with_the_account(app, user, mirror):
    _write(mirror / str(user.id) / 'rotated.zip')

    cleanup_pending(delete_owned_data(user.id))

    assert _files(mirror) == [MIRROR_MARKER_NAME]


def test_deleting_an_account_queues_no_mirror_cleanup_without_a_mirror(app, user):
    delete_owned_data(user.id)

    assert _mirror_tasks() == []

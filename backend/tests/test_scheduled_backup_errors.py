"""Regression tests for L8: error-handling scope in process_scheduled_backups.

`backup`/`user` are function-scoped and persist across loop iterations. A failure
BEFORE they are assigned made the `except` either:
  * NameError on `if backup:` (first iteration → crashes the whole hourly job), or
  * mutate the PREVIOUS iteration's `backup` (later iterations → mis-marks another
    user's backup record as failed).
The fix resets `backup = None`/`user = None` at the top of each `if should_run:`
iteration and guards the failure notification with `user is not None`.

To make a schedule "due" we match this UTC hour + weekday exactly as the job
computes them.
"""

from datetime import datetime, timezone
import io

import app.services as services
import app.models as models
from app import db
from app.models import User
from app.models.backup import Backup, BackupSchedule


def _due_schedule(uid, **overrides):
    now = datetime.now(timezone.utc)
    fields = dict(
        user_id=uid,
        enabled=True,
        frequency='weekly',
        day_of_week=now.weekday(),   # runs today
        hour=now.hour,               # runs this hour
        notify_on_failure=True,
        notify_on_success=False,
        last_run_at=None,
    )
    fields.update(overrides)
    s = BackupSchedule(**fields)
    db.session.add(s)
    db.session.commit()
    return s


def _mk_user(email):
    u = User(username=email.split('@')[0], email=email, is_active=True)
    u.set_password('StrongPass123!')
    db.session.add(u)
    db.session.commit()
    return u


def test_failure_before_backup_assigned_does_not_crash(app, monkeypatch):
    """A failure before the Backup record is created must NOT NameError; the
    schedule is simply marked failed and the job finishes."""
    with app.app_context():
        uid = _mk_user('sched1@example.com').id
        _due_schedule(uid)

    # Backup construction raises → `backup` is never assigned this iteration.
    def _boom_backup(**kwargs):
        raise RuntimeError('backup construction failed')
    monkeypatch.setattr(models, 'Backup', _boom_backup)

    # Record (and neutralise) the failure notification.
    calls = []
    monkeypatch.setattr(services, 'send_backup_notification',
                        lambda *a, **k: calls.append(a))

    # On the OLD code this raises NameError('backup') out of the job.
    services.process_scheduled_backups(app)

    with app.app_context():
        db.session.remove()
        s = BackupSchedule.query.filter_by(user_id=uid).first()
        assert s.last_status == 'failed'
        assert 'backup construction failed' in (s.last_error or '')
    # user was resolved, so the (guarded) failure notification still fired once
    assert len(calls) == 1


def test_one_users_failure_does_not_mismark_anothers_backup(app, monkeypatch):
    """Cross-iteration: user1's backup succeeds, then user2 fails before its own
    Backup is created. The stale `backup` must NOT be reused to mark user1's
    record failed."""
    with app.app_context():
        uid1 = _mk_user('u1@example.com').id
        uid2 = _mk_user('u2@example.com').id
        # user1's schedule is inserted first → processed first (rowid order).
        _due_schedule(uid1)
        _due_schedule(uid2)
        backup_folder = app.config['BACKUP_FOLDER']

    real_backup_cls = models.Backup

    class _BackupProxy:
        """Callable that raises on construction for user2 (before assignment) but
        delegates every other attribute (e.g. `.query`, columns) to the real
        Backup class, so `cleanup_user_backups` etc. keep working for user1."""
        def __call__(self, **kwargs):
            if kwargs.get('user_id') == uid2:
                raise RuntimeError('user2 backup boom')
            return real_backup_cls(**kwargs)

        def __getattr__(self, name):
            return getattr(real_backup_cls, name)

    monkeypatch.setattr(models, 'Backup', _BackupProxy())

    # Make user1's backup succeed with light fakes (no real zip/disk/network).
    import os
    monkeypatch.setattr('app.routes.backup.create_backup_zip',
                        lambda user, include_attachments=True: (
                            io.BytesIO(b'PK\x03\x04'),
                            {'vehicles': [], 'reminders': [], 'attachments': []},
                        ))
    monkeypatch.setattr('app.routes.backup.save_backup_to_disk',
                        lambda user, buf, inc: ('sched.zip', os.path.join(backup_folder, 'sched.zip'), 4))
    monkeypatch.setattr('app.routes.backup.send_to_all_external_destinations',
                        lambda *a, **k: (None, []))
    monkeypatch.setattr(services, 'send_backup_notification', lambda *a, **k: None)

    services.process_scheduled_backups(app)

    with app.app_context():
        db.session.remove()
        # user1's backup must remain 'completed' (OLD code flips it to 'failed'
        # with user2's error message).
        b1 = Backup.query.filter_by(user_id=uid1).first()
        assert b1 is not None
        assert b1.status == 'completed', (b1.status, b1.error_message)
        assert b1.error_message is None
        # user2's schedule is marked failed; no Backup row was created for it.
        s2 = BackupSchedule.query.filter_by(user_id=uid2).first()
        assert s2.last_status == 'failed'
        assert Backup.query.filter_by(user_id=uid2).count() == 0

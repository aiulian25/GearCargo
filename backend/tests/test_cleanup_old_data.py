"""Tests for services.cleanup_old_data (R4-38 coverage).

The nightly housekeeping job had no tests at all, yet it issues bulk DELETEs
against three tables. These pin what it removes AND — more importantly — what
it must leave alone: a mis-scoped filter here silently destroys a user's
recent notification history or signs out every live session.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app import db
from app.models import Backup, NotificationLog, User
from app.models.user_session import UserSession
from app.services import cleanup_old_data
from app.utils.timeutils import utc_naive_now

RETENTION_DAYS = 90


@pytest.fixture
def owner(app):
    with app.app_context():
        user = User(username='cleanup', email='cleanup@example.com', is_active=True)
        user.set_password('StrongPass123!')
        db.session.add(user)
        db.session.commit()
        return user.id


def _log(user_id, age_days, title='Reminder due'):
    return NotificationLog(
        user_id=user_id, notification_type='reminder', title=title,
        channel='push', created_at=utc_naive_now() - timedelta(days=age_days),
    )


def _session(user_id, jti, expires_in_days=7, revoked=False):
    return UserSession(
        user_id=user_id, jti=jti, revoked=revoked,
        absolute_expires_at=utc_naive_now() + timedelta(days=expires_in_days),
    )


def test_notification_logs_older_than_the_retention_window_are_deleted(app, owner):
    with app.app_context():
        db.session.add(_log(owner, age_days=RETENTION_DAYS + 1, title='Stale'))
        db.session.add(_log(owner, age_days=RETENTION_DAYS - 1, title='Recent'))
        db.session.commit()

    cleanup_old_data(app)

    with app.app_context():
        remaining = [log.title for log in NotificationLog.query.all()]
        assert remaining == ['Recent']


def test_revoked_sessions_are_purged_even_when_not_yet_expired(app, owner):
    with app.app_context():
        db.session.add(_session(owner, 'jti-revoked', revoked=True))
        db.session.add(_session(owner, 'jti-live'))
        db.session.commit()

    cleanup_old_data(app)

    with app.app_context():
        remaining = [s.jti for s in UserSession.query.all()]
        assert remaining == ['jti-live']


def test_expired_sessions_are_purged_even_when_not_revoked(app, owner):
    with app.app_context():
        db.session.add(_session(owner, 'jti-expired', expires_in_days=-1))
        db.session.add(_session(owner, 'jti-live'))
        db.session.commit()

    cleanup_old_data(app)

    with app.app_context():
        assert [s.jti for s in UserSession.query.all()] == ['jti-live']


def test_only_local_backups_past_retention_are_deleted(app, owner):
    """A cloud-stored backup row is the only record of that file — never drop it."""
    with app.app_context():
        old = utc_naive_now() - timedelta(days=RETENTION_DAYS + 1)
        db.session.add(Backup(user_id=owner, backup_type='manual',
                              filename='old-local.zip', created_at=old))
        db.session.add(Backup(user_id=owner, backup_type='manual',
                              filename='old-cloud.zip',
                              cloud_file_id='drive-123', created_at=old))
        db.session.add(Backup(user_id=owner, backup_type='manual',
                              filename='recent-local.zip',
                              created_at=utc_naive_now() - timedelta(days=1)))
        db.session.commit()

    cleanup_old_data(app)

    with app.app_context():
        remaining = sorted(b.filename for b in Backup.query.all())
        assert remaining == ['old-cloud.zip', 'recent-local.zip']


def test_cleanup_is_idempotent_and_safe_on_an_empty_database(app):
    cleanup_old_data(app)
    cleanup_old_data(app)

    with app.app_context():
        assert NotificationLog.query.count() == 0
        assert UserSession.query.count() == 0


def test_cleanup_never_touches_another_users_recent_data(app, owner):
    with app.app_context():
        other = User(username='bystander', email='bystander@example.com',
                     is_active=True)
        other.set_password('StrongPass123!')
        db.session.add(other)
        db.session.commit()
        db.session.add(_log(other.id, age_days=1, title='Theirs'))
        db.session.add(_session(other.id, 'jti-theirs'))
        db.session.commit()

    cleanup_old_data(app)

    with app.app_context():
        assert [log.title for log in NotificationLog.query.all()] == ['Theirs']
        assert [s.jti for s in UserSession.query.all()] == ['jti-theirs']

"""GC-119: a backup copy that keeps failing tells someone, in the language of their account.

This file covers the external destination and the wording. The second copy's notice (one per
run of failures) is tested with its job in test_backup_mirror.py.
"""
from datetime import datetime

import pytest
from sqlalchemy import update

from app import db
from app.models import BackupSchedule, JobRun, ScheduledEffect
from app.services.backup_notices import (
    EXTERNAL_COPY_FAILED, MIRROR_FAILING, NOTICE_DATA, NOTICE_TAG_PREFIX, NOTICE_TEXT,
    notify_external_copy_failed,
)
from app.services.scheduled_effects import enqueue_effect, process_scheduled_effects
from app.services.scheduler_ownership import run_due_job
from tests.test_scheduler_coordination import definition

SUPPORTED_LANGUAGES = {'en', 'ro', 'es'}
RETRY_LIMIT = 8
LONG_AGO = datetime(2000, 1, 1)
DELIVERY_JOB = 'scheduled_deliveries'


@pytest.fixture()
def schedule(user):
    backup_schedule = BackupSchedule(user_id=user.id, enabled=True)
    db.session.add(backup_schedule)
    db.session.commit()
    return backup_schedule


def _queued_delivery(app, user_id, kind='backup'):
    """One undelivered effect of this kind, and the job that delivers it."""
    queue = definition(app, lambda app: enqueue_effect(kind, user_id, 'one', {'title': 'Queued'}))
    assert run_due_job(app, 'fixture', queue)
    return definition(app, process_scheduled_effects, name=DELIVERY_JOB)


def _deliver(app, delivery):
    with db.engine.begin() as connection:
        connection.execute(update(ScheduledEffect).values(next_attempt_at=LONG_AGO))
        connection.execute(update(JobRun).where(JobRun.job_name == DELIVERY_JOB).values(next_due_at=LONG_AGO))
    return run_due_job(app, DELIVERY_JOB, delivery)


def _abandon_on_the_last_attempt():
    """What a process that died during its final upload leaves behind."""
    effect = ScheduledEffect.query.one()
    effect.status, effect.attempts, effect.lease_until = 'sending', RETRY_LIMIT, LONG_AGO
    db.session.commit()


def _effect_status():
    db.session.expire_all()
    return ScheduledEffect.query.one().status


def test_an_external_copy_that_ran_out_of_retries_tells_the_owner_once(app, user, schedule, sent_pushes, monkeypatch):
    owner = user.id
    delivery = _queued_delivery(app, owner)
    monkeypatch.setattr('app.services.scheduled_effects.deliver', lambda *_arguments: False)

    for _ in range(RETRY_LIMIT - 1):
        assert _deliver(app, delivery)
    assert sent_pushes == []

    assert _deliver(app, delivery)
    assert _deliver(app, delivery)

    title, body = NOTICE_TEXT[EXTERNAL_COPY_FAILED]['en']
    assert sent_pushes == [{'user_id': owner, 'title': title, 'body': body, 'data': NOTICE_DATA,
                            'tag': NOTICE_TAG_PREFIX + EXTERNAL_COPY_FAILED}]
    assert _effect_status() == 'failed'


def test_a_delivery_abandoned_on_its_last_attempt_is_announced_too(app, user, schedule, sent_pushes):
    delivery = _queued_delivery(app, user.id)
    _abandon_on_the_last_attempt()

    assert _deliver(app, delivery)

    assert len(sent_pushes) == 1
    assert _effect_status() == 'failed'


def test_an_exhausted_push_or_email_stays_quiet(app, user, schedule, sent_pushes, monkeypatch):
    delivery = _queued_delivery(app, user.id, kind='push')
    monkeypatch.setattr('app.services.scheduled_effects.deliver', lambda *_arguments: False)

    for _ in range(RETRY_LIMIT):
        assert _deliver(app, delivery)

    assert _effect_status() == 'failed'
    assert sent_pushes == []


def test_the_owner_notice_is_sent_at_once_and_never_queued_behind_the_job_that_sends_it(app, user, schedule):
    delivery = _queued_delivery(app, user.id)
    _abandon_on_the_last_attempt()

    assert _deliver(app, delivery)

    assert ScheduledEffect.query.count() == 1


def test_a_notice_that_cannot_be_sent_does_not_fail_the_delivery_job(app, user, schedule, monkeypatch):
    delivery = _queued_delivery(app, user.id)
    _abandon_on_the_last_attempt()

    def unreachable_push_service(*_arguments, **_options):
        raise RuntimeError('push service down')

    monkeypatch.setattr('app.routes.push.send_push_to_user', unreachable_push_service)

    assert _deliver(app, delivery)
    assert _effect_status() == 'failed'


@pytest.mark.parametrize('owner_fields, schedule_fields', [
    ({'notifications_enabled': False}, {}),
    ({'is_active': False}, {}),
    ({}, {'notify_on_failure': False}),
])
def test_an_account_that_does_not_want_the_notice_gets_none(user, schedule, sent_pushes, owner_fields, schedule_fields):
    for record, fields in ((user, owner_fields), (schedule, schedule_fields)):
        for name, value in fields.items():
            setattr(record, name, value)
    db.session.commit()

    notify_external_copy_failed(user.id)

    assert sent_pushes == []


@pytest.mark.parametrize('language, expected', [('en', 'en'), ('ro', 'ro'), ('es', 'es'), ('de', 'en'), (None, 'en')])
def test_the_notice_is_in_the_language_of_the_account(user, schedule, sent_pushes, language, expected):
    user.language = language
    db.session.commit()

    notify_external_copy_failed(user.id)

    assert (sent_pushes[0]['title'], sent_pushes[0]['body']) == NOTICE_TEXT[EXTERNAL_COPY_FAILED][expected]


@pytest.mark.parametrize('notice', [EXTERNAL_COPY_FAILED, MIRROR_FAILING])
def test_every_notice_has_a_title_and_a_body_in_every_supported_language(notice):
    assert set(NOTICE_TEXT[notice]) == SUPPORTED_LANGUAGES
    assert all(title.strip() and body.strip() for title, body in NOTICE_TEXT[notice].values())

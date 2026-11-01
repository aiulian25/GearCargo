"""GC-021: one logical notification per channel and reminder occurrence."""
from app import db
from datetime import date, datetime, timedelta, timezone
from threading import Barrier
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from app.models import Reminder, Vehicle, User
from app.services import check_due_reminders, _check_mileage_reminders
from app.services import reminder_delivery as delivery
from app.utils.timeutils import utc_today


def test_due_today_does_not_send_again_on_the_next_scheduler_run(app, user, monkeypatch):
    calls = []
    monkeypatch.setattr('app.routes.push.send_push_to_user', lambda *args, **kwargs: calls.append(kwargs) or 1)
    with app.app_context():
        vehicle = Vehicle(user_id=user.id, name='Date reminder fixture')
        db.session.add(vehicle)
        db.session.flush()
        db.session.add(Reminder(user_id=user.id, vehicle_id=vehicle.id, title='Due today', due_date=utc_today(), notify_email=False))
        db.session.commit()
    check_due_reminders(app)
    check_due_reminders(app)
    assert len(calls) == 1


@pytest.fixture
def clock(monkeypatch):
    current = [datetime(2028, 2, 22, 12)]
    monkeypatch.setattr(delivery, 'utc_naive_now', lambda: current[0])
    return current


@pytest.fixture
def transports(app, monkeypatch):
    calls = {'push': [], 'email': []}
    outcomes = {'push': 1, 'email': True}
    def send(channel):
        def transport(*args, **kwargs):
            calls[channel].append((args, kwargs))
            value = outcomes[channel]
            if isinstance(value, Exception):
                raise value
            return value
        return transport
    monkeypatch.setattr('app.routes.push.send_push_to_user', send('push'))
    monkeypatch.setattr('app.services.email_service.EmailService.send_alert_notification', send('email'))
    app.config['MAIL_ENABLED'] = True
    return calls, outcomes


def make_reminder(user, **changes):
    values = dict(user_id=user.id, title='Oil', due_date=date(2028, 2, 29), notify_days_before=7)
    values.update(changes)
    row = Reminder(**values)
    db.session.add(row)
    db.session.commit()
    return row


def make_vehicle(user, mileage=10000, **changes):
    row = Vehicle(user_id=user.id, name='Miles car', distance_unit='miles', current_mileage=mileage, **changes)
    db.session.add(row)
    db.session.commit()
    return row


def test_before_during_and_after_advance_window(app, user, clock, transports):
    calls, _ = transports
    reminder = make_reminder(user)
    for now, expected in [(datetime(2028, 2, 21, 23, 59), 0), (datetime(2028, 2, 22), 1),
                          (datetime(2028, 2, 22, 12), 1), (datetime(2028, 2, 29), 1), (datetime(2028, 3, 20), 1)]:
        clock[0] = now
        check_due_reminders(app)
        assert len(calls['push']) == len(calls['email']) == expected
    db.session.refresh(reminder)
    assert reminder.last_notified_at == datetime(2028, 2, 22)
    assert all(item['status'] == 'sent' for item in reminder.notification_state['channels'].values())


@pytest.mark.parametrize('zone,now,expected', [
    ('America/Los_Angeles', datetime(2028, 2, 22, 7, 59), 0),
    ('America/Los_Angeles', datetime(2028, 2, 22, 8), 1),
    ('Pacific/Auckland', datetime(2028, 2, 21, 11), 1),
    ('invalid-zone', datetime(2028, 2, 22), 1),
    ('America/New_York', datetime(2028, 3, 12, 5), 1),  # DST transition day.
])
def test_lead_window_uses_owner_local_date(app, user, clock, transports, zone, now, expected):
    user.timezone = zone
    make_reminder(user, due_date=date(2028, 3, 19) if now.month == 3 else date(2028, 2, 29))
    clock[0] = now
    check_due_reminders(app)
    assert len(transports[0]['push']) == expected


def test_zero_lead_time_and_long_overdue_first_notice(app, user, clock, transports):
    make_reminder(user, notify_days_before=0)
    check_due_reminders(app)
    assert transports[0]['push'] == []
    clock[0] = datetime(2028, 4, 1)
    check_due_reminders(app)
    check_due_reminders(app)
    assert len(transports[0]['push']) == len(transports[0]['email']) == 1


def test_snoozed_mileage_crossing_stays_silent_until_deadline(app, user, clock, transports):
    vehicle = make_vehicle(user)
    r = make_reminder(user, vehicle_id=vehicle.id, due_date=date(2030, 1, 1), due_mileage=9000,
                      snoozed_until=clock[0] + timedelta(days=1))
    _check_mileage_reminders(app)
    assert transports[0]['push'] == transports[0]['email'] == []
    clock[0] += timedelta(days=1)
    _check_mileage_reminders(app)
    _check_mileage_reminders(app)
    assert len(transports[0]['push']) == len(transports[0]['email']) == 1
    assert '9,000 miles' in transports[0]['push'][0][0][2]
    db.session.refresh(r)
    assert r.mileage_notified


@pytest.mark.parametrize('preference', ['master', 'push', 'email', 'email_type', 'inactive'])
def test_preferences_do_not_mark_unsent_channels_delivered(app, user, clock, transports, preference):
    vehicle = make_vehicle(user)
    r = make_reminder(user, vehicle_id=vehicle.id, due_mileage=9000)
    if preference == 'master': user.notifications_enabled = False
    elif preference == 'inactive': user.is_active = False
    elif preference == 'email_type': user.email_reminder_alerts = False
    elif preference == 'push': r.notify_push = False
    else: r.notify_email = False
    db.session.commit()
    check_due_reminders(app)
    disabled = ['push', 'email'] if preference in ('master', 'inactive') else ['push' if preference == 'push' else 'email']
    for channel in disabled:
        assert transports[0][channel] == []
    db.session.refresh(r)
    assert all(r.notification_state.get('channels', {}).get(channel, {}).get('status') != 'sent' for channel in disabled)
    user.notifications_enabled = user.is_active = user.email_reminder_alerts = True
    r.notify_push = r.notify_email = True
    db.session.commit()
    check_due_reminders(app)
    assert len(transports[0]['push']) == len(transports[0]['email']) == 1


@pytest.mark.parametrize('failure', [0, RuntimeError('fixture transport failure')])
def test_failed_channel_retries_without_repeating_successful_channel(app, user, clock, transports, failure):
    calls, outcomes = transports
    r = make_reminder(user)
    outcomes['push'] = failure
    check_due_reminders(app)
    check_due_reminders(app)
    assert len(calls['push']) == len(calls['email']) == 1
    db.session.refresh(r)
    assert r.notification_state['channels']['push']['status'] == 'retry'
    assert r.notification_state['channels']['email']['status'] == 'sent'
    outcomes['push'] = 1
    clock[0] += timedelta(hours=1)
    check_due_reminders(app)
    assert len(calls['push']) == 2 and len(calls['email']) == 1


def test_failed_mileage_transports_remain_retryable(app, user, clock, transports):
    vehicle = make_vehicle(user)
    r = make_reminder(user, vehicle_id=vehicle.id, due_date=date(2030, 1, 1), due_mileage=9000)
    calls, outcomes = transports
    outcomes.update(push=0, email=False)
    _check_mileage_reminders(app)
    db.session.refresh(r)
    assert r.last_notified_at is None and not r.mileage_notified
    outcomes.update(push=1, email=True)
    clock[0] += timedelta(hours=1)
    _check_mileage_reminders(app)
    assert len(calls['push']) == len(calls['email']) == 2
    db.session.refresh(r)
    assert r.mileage_notified


def test_date_and_mileage_share_an_occurrence(app, user, clock, transports):
    vehicle = make_vehicle(user)
    make_reminder(user, vehicle_id=vehicle.id, due_mileage=9000)
    _check_mileage_reminders(app)
    check_due_reminders(app)
    assert len(transports[0]['push']) == len(transports[0]['email']) == 1


def test_expired_worker_claim_is_retried_but_live_claim_is_not(app, user, clock, transports):
    r = make_reminder(user, notify_email=False)
    claim = delivery.claim(r.id, 'push', 'date', clock[0], app)
    assert claim
    check_due_reminders(app)
    assert transports[0]['push'] == []
    clock[0] += delivery.LEASE
    check_due_reminders(app)
    assert len(transports[0]['push']) == 1
    # The expired worker cannot overwrite its successor's successful outcome.
    delivery.finish(r.id, 'push', claim, False, clock[0])
    db.session.refresh(r)
    assert r.notification_state['channels']['push']['status'] == 'sent'


def test_reschedule_between_claim_and_transport_does_not_send_stale_claim(app, user, clock, transports, monkeypatch):
    r = make_reminder(user, notify_email=False)
    original_claim = delivery.claim
    changed = False

    def claim_then_reschedule(*args):
        nonlocal changed
        claimed = original_claim(*args)
        if claimed and not changed:
            changed = True
            current = db.session.get(Reminder, r.id)
            current.due_date = date(2028, 2, 28)
            current.notification_state = {}
            db.session.commit()
        return claimed

    monkeypatch.setattr(delivery, 'claim', claim_then_reschedule)
    check_due_reminders(app)
    assert transports[0]['push'] == []
    check_due_reminders(app)
    check_due_reminders(app)
    assert len(transports[0]['push']) == 1


def test_concurrent_scheduler_ticks_claim_each_channel_once(app, user, clock, transports):
    if db.engine.dialect.name != 'postgresql':
        pytest.skip('Production-engine dispatch concurrency')
    make_reminder(user)
    barrier = Barrier(2)
    def run():
        barrier.wait(timeout=10)
        check_due_reminders(app)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: run(), range(2)))
    assert len(transports[0]['push']) == len(transports[0]['email']) == 1


def test_legacy_attempt_flags_do_not_trigger_a_flood(app, user, clock, transports):
    make_reminder(user, last_notified_at=datetime(2020, 1, 1), notification_state=None)
    make_reminder(user, mileage_notified=True, notification_state=None)
    check_due_reminders(app)
    assert transports[0]['push'] == transports[0]['email'] == []


def test_snooze_preserves_due_date_and_starts_one_new_cycle(client, app, user, auth_headers, clock, transports, monkeypatch):
    from app.routes import reminders as routes
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock[0].replace(tzinfo=timezone.utc) if tz else clock[0]
    monkeypatch.setattr(routes, 'datetime', Clock)
    r = make_reminder(user)
    check_due_reminders(app)
    response = client.post(f'/api/reminders/{r.id}/snooze', headers=auth_headers(user.id), json={'days': 2})
    assert response.status_code == 200
    assert response.json['reminder']['due_date'] == '2028-02-29'
    check_due_reminders(app)
    assert len(transports[0]['push']) == 1
    clock[0] += timedelta(days=2)
    check_due_reminders(app)
    check_due_reminders(app)
    assert len(transports[0]['push']) == len(transports[0]['email']) == 2
    for days in (0, -1, 366, 'tomorrow'):
        assert client.post(f'/api/reminders/{r.id}/snooze', headers=auth_headers(user.id), json={'days': days}).status_code == 400


@pytest.mark.parametrize('due,frequency,expected', [
    (date(2028, 1, 31), 'monthly', [date(2028, 2, 29), date(2028, 3, 31)]),
    (date(2028, 2, 29), 'yearly', [date(2029, 2, 28), date(2030, 2, 28), date(2031, 2, 28), date(2032, 2, 29)]),
])
def test_calendar_recurrence_preserves_original_anchor(client, user, auth_headers, due, frequency, expected):
    r = make_reminder(user, due_date=due, recurring=True, frequency=frequency, frequency_value=1)
    headers = auth_headers(user.id)
    for next_due in expected:
        assert client.post(f'/api/reminders/{r.id}/complete', headers=headers).status_code == 200
        successor = Reminder.query.filter_by(completed_from_id=r.id).one()
        assert successor.due_date == next_due
        assert client.post(f'/api/reminders/{r.id}/complete', headers=headers).status_code == 200
        assert Reminder.query.filter_by(completed_from_id=r.id).count() == 1
        r = successor


def test_mileage_recurrence_uses_current_vehicle_units_and_requires_legacy_choice(client, user, auth_headers):
    vehicle = make_vehicle(user, mileage=12000)
    r = make_reminder(user, vehicle_id=vehicle.id, due_mileage=10000, recurring=True, frequency='monthly', frequency_value=1)
    headers = auth_headers(user.id)
    response = client.post(f'/api/reminders/{r.id}/complete', headers=headers)
    assert response.status_code == 409 and response.json['code'] == 'MILEAGE_RECURRENCE_REQUIRED'
    db.session.refresh(r)
    assert not r.completed and Reminder.query.filter_by(completed_from_id=r.id).count() == 0
    for threshold in (10000, 12000):
        assert client.post(f'/api/reminders/{r.id}/complete', headers=headers, json={'next_due_mileage': threshold}).status_code == 409
    assert client.post(f'/api/reminders/{r.id}/complete', headers=headers, json={'next_due_mileage': 17000}).status_code == 200
    successor = Reminder.query.filter_by(completed_from_id=r.id).one()
    assert successor.due_mileage == 17000
    successor.repeat_mileage = 5000
    db.session.commit()
    assert client.post(f'/api/reminders/{successor.id}/complete', headers=headers).status_code == 200
    assert Reminder.query.filter_by(completed_from_id=successor.id).one().due_mileage == 22000


def test_create_and_edit_preserve_delivery_preferences_and_interval(client, user, auth_headers):
    vehicle = make_vehicle(user)
    headers = auth_headers(user.id)
    payload = dict(title='Oil', vehicle_id=vehicle.id, due_date='2028-02-29', due_mileage=10000,
        repeat_interval='1_month', repeat_mileage=5000, notify_days_before=14, notify_push=False, notify_email=False)
    created = client.post('/api/reminders', headers=headers, json=payload)
    assert created.status_code == 201, created.json
    r = created.json['reminder']
    assert r['repeat_mileage'] == 5000 and r['notify_days_before'] == 14
    assert r['notify_push'] is False and r['notify_email'] is False
    changed = client.put(f'/api/reminders/{r["id"]}', headers=headers, json={'repeat_mileage': 7000, 'notify_email': True})
    assert changed.status_code == 200 and changed.json['reminder']['repeat_mileage'] == 7000
    for value in (0, -1, 'x', 2147483648):
        assert client.post('/api/reminders', headers=headers, json={**payload, 'repeat_mileage': value}).status_code == 400
    assert client.post('/api/reminders', headers=headers, json={**payload, 'repeat_interval': ''}).status_code == 400


def test_migration_preserves_unknown_delivery_and_requires_mileage_choice():
    import importlib.util
    from pathlib import Path
    from sqlalchemy import create_engine, inspect, text
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    path = Path(__file__).parents[1] / 'migrations/versions/gc021_reminder_occurrences.py'
    spec = importlib.util.spec_from_file_location('gc021_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE reminders (id INTEGER PRIMARY KEY, due_date DATE, due_mileage INTEGER, snoozed_until DATETIME, recurring BOOLEAN, last_notified_at DATETIME, mileage_notified BOOLEAN)'))
        connection.execute(text("INSERT INTO reminders VALUES (1, '2028-01-31', 10000, NULL, 1, '2027-01-01', 0), (2, '2028-02-29', NULL, NULL, 0, NULL, 0), (3, '2028-02-29', 10000, '2028-02-22 12:00:00', 1, NULL, 1)"))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        import json
        rows = connection.execute(text('SELECT * FROM reminders ORDER BY id')).mappings().all()
        for row in (rows[0], rows[2]):
            state = json.loads(row['notification_state'])
            assert {v['status'] for v in state['channels'].values()} == {'legacy_unknown'}
            reminder = SimpleNamespace(due_date=date.fromisoformat(row['due_date']), due_mileage=row['due_mileage'], snoozed_until=row['snoozed_until'])
            assert state['occurrence'] == delivery.occurrence_key(reminder)
            assert row['repeat_mileage'] is None
        assert rows[0]['recurrence_anchor_date'] == '2028-01-31'
        assert json.loads(rows[1]['notification_state'])['channels'] == {}
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
        assert 'notification_state' not in {c['name'] for c in inspect(connection).get_columns('reminders')}
        assert connection.execute(text('SELECT due_mileage FROM reminders WHERE id=1')).scalar() == 10000
    engine.dispose()


def test_backup_preserves_channel_outcomes_and_reads_prior_format(app, user, clock, transports):
    from copy import deepcopy
    from app.routes.backup import gather_user_data, import_backup_data
    from app.services.backup_schema import prepare_backup
    vehicle = make_vehicle(user)
    r = make_reminder(user, vehicle_id=vehicle.id, due_mileage=15000, repeat_mileage=5000,
                      recurring=True, frequency='monthly', recurrence_anchor_date=date(2028, 1, 31))
    transports[1]['email'] = False
    check_due_reminders(app)
    payload = gather_user_data(user, False)
    assert payload['version'] == '4.7'
    portable = payload['reminders'][0]
    assert portable['notification_state']['channels']['push']['status'] == 'sent'
    assert portable['notification_state']['channels']['email']['status'] == 'retry'
    old = deepcopy(payload)
    old['version'] = '4.3'
    for field in ('repeat_mileage', 'recurrence_anchor_date', 'notification_state'):
        del old['reminders'][0][field]
    prepared = prepare_backup(old)
    assert prepared.records['reminders'][0]['notification_state'] is None
    target = User(username='restored-delivery', email='restored-delivery@example.invalid', is_active=True)
    target.set_password('FixturePassword123!')
    db.session.add(target)
    db.session.commit()
    import_backup_data(target, payload)
    restored = Reminder.query.filter_by(user_id=target.id).one()
    assert restored.id != r.id and restored.repeat_mileage == 5000
    assert restored.recurrence_anchor_date == date(2028, 1, 31)
    assert restored.notification_state == portable['notification_state']
    user.notifications_enabled = False
    db.session.commit()
    clock[0] += timedelta(hours=1)
    transports[1]['email'] = True
    check_due_reminders(app)
    assert len(transports[0]['push']) == 1 and len(transports[0]['email']) == 2


def test_edit_reschedules_but_notes_and_lead_changes_do_not_duplicate(client, app, user, auth_headers, clock, transports):
    r = make_reminder(user)
    check_due_reminders(app)
    headers = auth_headers(user.id)
    assert client.put(f'/api/reminders/{r.id}', headers=headers, json={'notes': 'New notes', 'notify_days_before': 30}).status_code == 200
    check_due_reminders(app)
    assert len(transports[0]['push']) == 1
    assert client.put(f'/api/reminders/{r.id}', headers=headers, json={'due_date': '2028-03-01'}).status_code == 200
    check_due_reminders(app)
    assert len(transports[0]['push']) == 2


@pytest.mark.parametrize('token,frequency,value,serialized', [
    ('weekly', 'weekly', 1, '1_week'), ('monthly', 'monthly', 1, '1_month'),
    ('quarterly', 'monthly', 3, '3_months'), ('biannually', 'monthly', 6, '6_months'),
    ('yearly', 'yearly', 1, '1_year'),
])
def test_standalone_form_repeat_tokens_roundtrip(client, user, auth_headers, token, frequency, value, serialized):
    response = client.post('/api/reminders', headers=auth_headers(user.id), json={
        'title': 'Oil', 'due_date': '2028-01-31', 'due_mileage': 10000,
        'repeat_interval': token, 'repeat_mileage': 5000,
    })
    assert response.status_code == 201, response.json
    row = response.json['reminder']
    assert (row['recurring'], row['frequency'], row['frequency_value'], row['repeat_interval']) == (True, frequency, value, serialized)

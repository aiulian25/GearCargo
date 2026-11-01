"""GC-024: process roles and durable scheduled-job ownership."""
from app import create_app
from app.config import TestingConfig
from datetime import datetime, timedelta, date
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import pytest
from sqlalchemy import select, update, text
from app import db
from app.models import JobRun, ScheduledEffect, Vehicle, InsurancePolicy
from app.services.scheduler_registry import JobDefinition
from app.services.scheduler_ownership import seed_jobs, run_due_job, MAX_ATTEMPTS


def test_web_factory_starts_no_scheduled_work(app, monkeypatch):
    import app.services as services
    import threading
    started = []
    monkeypatch.setattr(services, 'init_scheduler', lambda app: started.append('scheduler'))
    monkeypatch.setattr(threading.Thread, 'start', lambda thread: started.append(thread.name))
    monkeypatch.setattr('app.init_default_admin', lambda app: None)
    class WebConfig(TestingConfig):
        TESTING = False
        OLLAMA_ENABLED = True
        SQLALCHEMY_DATABASE_URI = app.config['SQLALCHEMY_DATABASE_URI']
        SECRET_KEY = 'scheduler-fixture-0123456789abcdef0123456789'
        JWT_SECRET_KEY = SECRET_KEY
        WTF_CSRF_SECRET_KEY = SECRET_KEY
        SESSION_TYPE = 'filesystem'
        VOLUMES_PATH = app.config['VOLUMES_PATH']
        BACKUP_FOLDER = app.config['BACKUP_FOLDER']
    create_app(WebConfig)
    assert started == [], 'Ordinary app creation started scheduled work or backfills'


def definition(app, callback, name='fixture', **options):
    app.config['PROCESS_ROLE'] = 'scheduler'
    definitions = {name: JobDefinition(name, callback, **{'seconds': 60, 'start_after': -1, **options})}
    seed_jobs(app, definitions)
    return definitions


def test_occurrence_success_is_durable_and_restart_does_not_replay(app):
    calls = []
    jobs = definition(app, lambda app: calls.append('once'))
    assert run_due_job(app, 'fixture', jobs)
    seed_jobs(app, jobs)
    assert not run_due_job(app, 'fixture', jobs)
    with app.app_context():
        row = db.session.get(JobRun, 'fixture')
        assert row.status == 'idle' and row.last_success_at and row.next_due_at > row.occurrence_at
    assert calls == ['once']


def test_bounded_retry_same_occurrence_and_redacted_status(app):
    def fail(app):
        raise RuntimeError('https://user:private-secret@provider.invalid')
    jobs = definition(app, fail)
    for attempt in range(MAX_ATTEMPTS):
        assert not run_due_job(app, 'fixture', jobs)
        with app.app_context(), db.engine.begin() as connection:
            row = connection.execute(select(JobRun.__table__)).mappings().one()
            if attempt == 0:
                occurrence = row['occurrence_at']
            assert row['occurrence_at'] == occurrence
            assert row['attempts'] == attempt + 1
            connection.execute(update(JobRun).values(next_attempt_at=datetime(2000, 1, 1)))
    assert not run_due_job(app, 'fixture', jobs)
    result = app.test_cli_runner().invoke(args=['scheduler-status'])
    assert result.exit_code == 0
    assert 'private-secret' not in result.output and 'provider.invalid' not in result.output
    assert json.loads(result.output)['jobs'][0]['status'] == 'failed'
    assert app.test_cli_runner().invoke(args=['scheduler-retry', 'fixture']).exit_code == 0
    jobs['fixture'].function = lambda app: None
    assert run_due_job(app, 'fixture', jobs)


def test_existing_logged_job_failure_is_not_reported_as_success(app):
    jobs = definition(app, lambda app: app.logger.error('A handled operation failed'))
    assert not run_due_job(app, 'fixture', jobs)
    with app.app_context():
        assert db.session.get(JobRun, 'fixture').status == 'retry'


def test_registry_coalesces_downtime_and_seeds_without_history(app):
    from app.services.scheduler_registry import job_definitions
    now = datetime(2028, 1, 31, 23, 59, 59)
    assert JobDefinition('interval', None, seconds=60).next_time(now) == datetime(2028, 2, 1)
    assert JobDefinition('month', None, cron={'day': 1, 'hour': 9}).next_time(now) == datetime(2028, 2, 1, 9)
    definitions = job_definitions(app)
    assert 'process_recurring_taxes_startup' not in definitions
    assert definitions['process_recurring_taxes'].start_after == 30
    seed_jobs(app, definitions)
    with app.app_context():
        assert ScheduledEffect.query.count() == 0
        assert all(row.attempts == 0 and row.last_started_at is None for row in JobRun.query.all())


def test_non_scheduler_roles_cannot_consume(app):
    from app.services import init_scheduler
    for role in ('web', 'worker', 'cli'):
        app.config['PROCESS_ROLE'] = role
        with pytest.raises(RuntimeError, match='role'):
            init_scheduler(app)
        with pytest.raises(RuntimeError, match='role'):
            run_due_job(app, 'fixture')


def test_rq_entrypoint_uses_consumer_role(monkeypatch, app):
    import rq_worker
    roles = []
    class Worker:
        def work(self, **kwargs):
            assert kwargs == {'with_scheduler': False}
    monkeypatch.setattr(rq_worker, 'create_app', lambda **kwargs: (roles.append(kwargs) or app))
    monkeypatch.setattr(rq_worker, 'build_worker', lambda app: Worker())
    rq_worker.main()
    assert roles == [{'process_role': 'worker'}]


def test_flask_cli_factory_role_is_explicit(app, monkeypatch):
    monkeypatch.setenv('FLASK_RUN_FROM_CLI', 'true')
    monkeypatch.setattr('app.init_default_admin', lambda app: pytest.fail('CLI initialized an administrator'))
    config = type('CliConfig', (TestingConfig,), {'SQLALCHEMY_DATABASE_URI': app.config['SQLALCHEMY_DATABASE_URI'],
        'BACKUP_FOLDER': app.config['BACKUP_FOLDER'], 'VOLUMES_PATH': app.config['VOLUMES_PATH']})
    other = create_app(config)
    assert other.config['PROCESS_ROLE'] == 'cli'


def test_job_transaction_is_fenced_against_changed_owner(app, user):
    original = user.username
    def stale(app):
        with db.engine.begin() as connection:
            connection.execute(update(JobRun).where(JobRun.job_name == 'fixture').values(owner_token='replacement', fence=2))
        from app.models import User
        db.session.get(User, user.id).username = 'must-not-commit'
        db.session.commit()
    jobs = definition(app, stale)
    assert not run_due_job(app, 'fixture', jobs)
    db.session.refresh(user)
    assert user.username == original


def test_scheduled_effect_commits_with_record_and_retries_without_regeneration(app, user, monkeypatch):
    from app.services.scheduled_effects import enqueue_effect, process_scheduled_effects
    user_id = user.id
    def generate(app):
        enqueue_effect('push', user_id, 'one', {'title': 'Private title', 'body': 'Private body'})
        db.session.add(Vehicle(user_id=user_id, name='Committed generation'))
        db.session.commit()
        raise RuntimeError('Interrupted before job acknowledgement')
    jobs = definition(app, generate)
    assert not run_due_job(app, 'fixture', jobs)
    row = ScheduledEffect.query.one()
    assert 'Private' not in row.payload and Vehicle.query.count() == 1
    with db.engine.begin() as connection:
        connection.execute(update(JobRun).values(next_attempt_at=datetime(2000, 1, 1)))
    jobs['fixture'].function = lambda app: enqueue_effect('push', user_id, 'one', {'title': 'Private title', 'body': 'Private body'})
    assert run_due_job(app, 'fixture', jobs)
    assert ScheduledEffect.query.count() == 1
    delivered = []
    monkeypatch.setattr('app.services.scheduled_effects.deliver', lambda effect, payload, user: (delivered.append(payload) or True))
    delivery = definition(app, process_scheduled_effects, name='scheduled_deliveries')
    assert run_due_job(app, 'scheduled_deliveries', delivery)
    assert len(delivered) == 1
    db.session.refresh(row)
    assert row.status == 'sent' and row.payload is None


def test_rolled_back_generation_has_no_delivery(app, user):
    from app.services.scheduled_effects import enqueue_effect
    def generate(app):
        enqueue_effect('push', user.id, 'one', {'title': 'Never send'})
        raise RuntimeError('Rollback')
    jobs = definition(app, generate)
    assert not run_due_job(app, 'fixture', jobs)
    assert ScheduledEffect.query.count() == 0


def test_owner_loss_before_commit_rolls_back_domain_and_delivery(app, user):
    from app.services.scheduler_ownership import active_run
    from app.services.scheduled_effects import enqueue_effect
    user_id = user.id
    def generate(app):
        db.session.add(Vehicle(user_id=user_id, name='Must roll back'))
        db.session.flush()
        enqueue_effect('push', user_id, 'one', {'title': 'Never send'})
        active_run.get().lock.lost.set()
        db.session.commit()
    jobs = definition(app, generate)
    assert not run_due_job(app, 'fixture', jobs)
    assert Vehicle.query.count() == 0 and ScheduledEffect.query.count() == 0


def test_email_and_push_queue_inside_jobs_but_reminders_keep_their_receipts(app, user, monkeypatch):
    from app.services.email_service import EmailService
    from app.routes.push import send_push_to_user
    app.config['MAIL_ENABLED'] = True
    sent = []
    monkeypatch.setattr('app.mail.send', lambda message: sent.append(message.subject))
    user_id, address = user.id, user.email
    def generate(app):
        assert EmailService._send_user_email(user, 'report', to=address, subject='Scheduled report', content_html='Private report')
        assert EmailService._send_user_email(user, 'report', to=address, subject='Changed rendering on retry', content_html='Private report')
        assert EmailService._send_user_email(user, 'second', to=address, subject='Second report', content_html='Private report')
        assert send_push_to_user(user_id, 'Renewed', 'Private body', data={'type': 'insurance_renewed'}, tag='renewed') == 1
        # Existing reminder acknowledgement stays synchronous/per-channel.
        assert send_push_to_user(user_id, 'Reminder', 'Due', data={'type': 'reminder'}) == 0
    jobs = definition(app, generate)
    assert run_due_job(app, 'fixture', jobs)
    assert sent == []
    assert {row.kind for row in ScheduledEffect.query.all()} == {'email', 'push'}
    from app.services.scheduled_effects import process_scheduled_effects
    delivery = definition(app, process_scheduled_effects, name='scheduled_deliveries')
    assert run_due_job(app, 'scheduled_deliveries', delivery)
    assert sent == ['GearCargo: Scheduled report', 'GearCargo: Second report']


def test_effect_failure_retry_exhaustion_and_manual_retry(app, user, monkeypatch):
    from app.services.scheduled_effects import enqueue_effect, process_scheduled_effects
    user_id = user.id
    jobs = definition(app, lambda app: enqueue_effect('push', user_id, 'one', {'title': 'Private title'}))
    assert run_due_job(app, 'fixture', jobs)
    calls = []
    monkeypatch.setattr('app.services.scheduled_effects.deliver', lambda *args: (calls.append('attempt') or False))
    delivery = definition(app, process_scheduled_effects, name='scheduled_deliveries')
    for _ in range(8):
        with db.engine.begin() as connection:
            connection.execute(update(ScheduledEffect).values(next_attempt_at=datetime(2000, 1, 1)))
            connection.execute(update(JobRun).where(JobRun.job_name == 'scheduled_deliveries').values(next_due_at=datetime(2000, 1, 1)))
        assert run_due_job(app, 'scheduled_deliveries', delivery)
    assert len(calls) == 8 and ScheduledEffect.query.one().status == 'failed'
    assert app.test_cli_runner().invoke(args=['scheduler-retry-deliveries']).exit_code == 0
    db.session.expire_all()
    assert ScheduledEffect.query.one().status == 'pending'


@pytest.mark.parametrize('removed', [False, True])
def test_queued_push_cancels_when_vehicle_is_archived_or_deleted(app, user, monkeypatch, removed):
    from app.services.scheduled_effects import enqueue_effect, process_scheduled_effects
    vehicle = Vehicle(user_id=user.id, name='Queued notification vehicle')
    db.session.add(vehicle); db.session.commit()
    user_id, vehicle_id = user.id, vehicle.id
    jobs = definition(app, lambda app: enqueue_effect('push', user_id, 'one',
        {'title': 'Due', 'body': 'Vehicle alert', 'data': {'vehicle_id': vehicle_id}}))
    assert run_due_job(app, 'fixture', jobs)
    if removed:
        db.session.delete(vehicle)
    else:
        vehicle.archived = True
    db.session.commit()
    monkeypatch.setattr('app.routes.push.send_push_to_user', lambda *args, **kwargs: pytest.fail('Inactive vehicle notified'))
    delivery = definition(app, process_scheduled_effects, name='scheduled_deliveries')
    assert run_due_job(app, 'scheduled_deliveries', delivery)
    assert ScheduledEffect.query.one().status == 'cancelled'


def test_scheduler_status_requires_admin_and_omits_payloads(app, client, user, auth_headers):
    definition(app, lambda app: None)
    assert client.get('/api/admin/scheduler', headers=auth_headers(user.id)).status_code == 403
    user.is_admin = True; db.session.commit()
    response = client.get('/api/admin/scheduler', headers=auth_headers(user.id, is_admin=True))
    assert response.status_code == 200
    assert {'jobs', 'deliveries'} == set(response.json)
    assert 'lag_seconds' in response.json['jobs'][0] and 'owner_token' not in response.json['jobs'][0]


def test_abandoned_delivery_claim_recovers_but_stops_at_retry_limit(app, user, monkeypatch):
    from app.services.scheduled_effects import enqueue_effect, process_scheduled_effects
    jobs = definition(app, lambda app: enqueue_effect('push', user.id, 'one', {'title': 'Recovery'}))
    assert run_due_job(app, 'fixture', jobs)
    effect = ScheduledEffect.query.one()
    effect.status = 'sending'
    effect.lease_until = datetime(2000, 1, 1)
    effect.attempts = 7
    db.session.commit()
    monkeypatch.setattr('app.services.scheduled_effects.deliver', lambda *args: True)
    delivery = definition(app, process_scheduled_effects, name='scheduled_deliveries')
    assert run_due_job(app, 'scheduled_deliveries', delivery)
    db.session.refresh(effect)
    assert effect.status == 'sent' and effect.attempts == 8
    effect.status = 'sending'
    effect.lease_until = datetime(2000, 1, 1)
    db.session.commit()
    with db.engine.begin() as connection:
        connection.execute(update(JobRun).where(JobRun.job_name == 'scheduled_deliveries').values(next_due_at=datetime(2000, 1, 1)))
    monkeypatch.setattr('app.services.scheduled_effects.deliver', lambda *args: pytest.fail('Exhausted claim sent again'))
    assert run_due_job(app, 'scheduled_deliveries', delivery)
    db.session.refresh(effect)
    assert effect.status == 'failed' and effect.attempts == 8


def test_scheduled_backup_retry_keeps_one_archive_and_external_intent(app, user, monkeypatch):
    from app.models import BackupSchedule, Backup
    from app.services import process_scheduled_backups
    from app.utils.timeutils import utc_naive_now
    now = utc_naive_now()
    schedule = BackupSchedule(user_id=user.id, enabled=True, frequency='weekly', day_of_week=now.weekday(),
        hour=now.hour, notify_on_success=True)
    db.session.add(schedule); db.session.commit()
    monkeypatch.setattr('app.routes.backup.send_to_all_external_destinations',
        lambda *args, **kwargs: pytest.fail('Scheduled generation contacted an external destination'))
    def generate(app):
        process_scheduled_backups(app)
        raise RuntimeError('Crash after committed archive')
    jobs = definition(app, generate, name='send_scheduled_backups')
    assert not run_due_job(app, 'send_scheduled_backups', jobs)
    backup = Backup.query.one()
    assert backup.status == 'completed' and Path(backup.filepath).is_file()
    assert ScheduledEffect.query.filter_by(kind='backup').count() == 1
    with db.engine.begin() as connection:
        connection.execute(update(JobRun).values(next_attempt_at=datetime(2000, 1, 1)))
    jobs['send_scheduled_backups'].function = process_scheduled_backups
    assert run_due_job(app, 'send_scheduled_backups', jobs)
    assert Backup.query.count() == 1 and len(list(Path(backup.filepath).parent.glob('*.zip'))) == 1
    assert ScheduledEffect.query.filter_by(kind='backup').count() == 1


def test_account_deletion_removes_queued_effects_without_removing_global_cursor(app, user):
    from app.services.scheduled_effects import enqueue_effect
    from app.services.deletion import delete_owned_data
    user_id = user.id
    jobs = definition(app, lambda app: enqueue_effect('push', user_id, 'one', {'title': 'Private'}))
    assert run_due_job(app, 'fixture', jobs)
    delete_owned_data(user_id)
    assert ScheduledEffect.query.count() == 0 and JobRun.query.count() == 1


def test_scheduler_migration_adds_empty_operational_tables_and_downgrades():
    import importlib.util
    from sqlalchemy import create_engine, inspect
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    path = Path(__file__).parents[1] / 'migrations/versions/gc024_job_claims.py'
    spec = importlib.util.spec_from_file_location('scheduler_migration', path)
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE users (id INTEGER PRIMARY KEY)'))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        assert connection.execute(text('SELECT count(*) FROM scheduled_job_runs')).scalar_one() == 0
        assert connection.execute(text('SELECT count(*) FROM scheduled_effects')).scalar_one() == 0
        assert 'uq_scheduled_effect_occurrence' in {c['name'] for c in inspect(connection).get_unique_constraints('scheduled_effects')}
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
        assert inspect(connection).get_table_names() == ['users']
    engine.dispose()


@pytest.mark.parametrize('failure', [None, 'dump', 'archive'])
def test_system_archive_occurrence_is_atomic_and_retry_safe(tmp_path, failure):
    import shlex
    script = Path(__file__).parents[2] / 'scripts/docker-backup.sh'
    binaries = tmp_path / 'bin'; binaries.mkdir()
    calls = tmp_path / 'dump-calls'
    dump = binaries / 'pg_dump'
    dump.write_text('#!/bin/sh\nprintf "called\\n" >> '+shlex.quote(str(calls))+'\n'
        + ('exit 1\n' if failure == 'dump' else 'printf "fixture database\\n"\n'))
    dump.chmod(0o755)
    if failure == 'archive':
        archive = binaries / 'tar'
        archive.write_text('#!/bin/sh\n/usr/bin/tar "$@"\nexit 1\n'); archive.chmod(0o755)
    environment = {**os.environ, 'PATH': str(binaries)+':/usr/bin:/bin', 'BACKUP_OCCURRENCE': '20280101_030000',
        'BACKUP_ROOT': str(tmp_path/'archives'), 'ATTACHMENTS_DIR': str(tmp_path/'attachments'),
        'UPLOADS_DIR': str(tmp_path/'uploads'), 'KEEP_LAST': '7'}
    first = subprocess.run(['sh', str(script), 'daily'], env=environment, capture_output=True, text=True, timeout=20)
    if failure:
        assert first.returncode != 0
        assert not list((tmp_path/'archives').rglob('*.tar.gz'))
        assert not list((tmp_path/'archives').rglob('*.partial.*'))
    else:
        assert first.returncode == 0, first.stderr
        second = subprocess.run(['sh', str(script), 'daily'], env=environment, capture_output=True, text=True, timeout=20)
        assert second.returncode == 0, second.stderr
        assert calls.read_text().splitlines() == ['called']
        assert len(list((tmp_path/'archives').rglob('*.tar.gz'))) == 1


@pytest.fixture
def scheduler_processes(app, user, tmp_path):
    vehicle = Vehicle(user_id=user.id, name='Scheduler car')
    db.session.add(vehicle); db.session.flush()
    policy = InsurancePolicy(user_id=user.id, vehicle_id=vehicle.id, provider='Fixture', premium=10,
        start_date=date.today() - timedelta(days=366), end_date=date.today() - timedelta(days=1),
        status='active', auto_renew=True)
    db.session.add(policy); db.session.commit()
    policy_id = policy.id
    settings = {key: app.config[key] for key in ('SQLALCHEMY_DATABASE_URI', 'VOLUMES_PATH', 'UPLOAD_FOLDER', 'BACKUP_FOLDER',
        'SECRET_KEY', 'JWT_SECRET_KEY', 'SESSION_TYPE', 'SESSION_FILE_DIR')}
    config = tmp_path / 'settings.json'; config.write_text(json.dumps(settings))
    script = Path(__file__).with_name('scheduler_process_fixture.py')
    processes = []
    logs = Path(os.environ.get('GC_SCHEDULER_LOG_DIR', str(tmp_path))) / tmp_path.name
    logs.mkdir(parents=True, exist_ok=True)
    def start(mode, label):
        log = logs / (label + '.txt')
        with log.open('w') as stream:
            process = subprocess.Popen([sys.executable, str(script), str(config), str(tmp_path), mode, label],
                stdout=stream, stderr=subprocess.STDOUT)
        processes.append((process, log))
        return process, log
    yield tmp_path, start, policy_id
    for process, log in processes:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)


def wait_file(path, process, log):
    deadline = time.monotonic() + 20
    while not path.exists():
        assert process.poll() is None, log.read_text()
        assert time.monotonic() < deadline, log.read_text()
        time.sleep(0.02)


def expire_lease():
    db.session.remove()
    with db.engine.begin() as connection:
        connection.execute(update(JobRun).where(JobRun.job_name == 'test-renewal').values(lease_until=datetime(2000, 1, 1)))


def assert_one_generation(policy_id):
    db.session.remove()
    assert InsurancePolicy.query.filter_by(renewed_from_id=policy_id).count() == 1
    assert InsurancePolicy.query.count() == 2
    assert ScheduledEffect.query.filter_by(job_name='test-renewal', kind='push').count() == 1
    assert ScheduledEffect.query.filter_by(job_name='test-renewal', kind='generation').count() == 1
    assert db.session.get(JobRun, 'test-renewal').status == 'idle'


def test_two_scheduler_processes_share_one_occurrence(scheduler_processes):
    folder, start, policy_id = scheduler_processes
    first, first_log = start('run', 'first'); second, second_log = start('run', 'second')
    wait_file(folder/'ready-first', first, first_log); wait_file(folder/'ready-second', second, second_log)
    (folder/'start').touch()
    assert first.wait(timeout=25) == 0, first_log.read_text()
    assert second.wait(timeout=25) == 0, second_log.read_text()
    assert_one_generation(policy_id)


@pytest.mark.parametrize('point', ['crash_flush', 'crash_commit'])
@pytest.mark.parametrize('long_overdue', [False, True])
def test_process_loss_recovers_the_same_generation(scheduler_processes, point, long_overdue):
    folder, start, policy_id = scheduler_processes
    if long_overdue:
        policy = db.session.get(InsurancePolicy, policy_id)
        policy.start_date = date.today() - timedelta(days=31)
        policy.end_date = date.today() - timedelta(days=30)
        db.session.commit()
    (folder/'start').touch()
    crashed, log = start(point, 'crashed')
    assert crashed.wait(timeout=25) == 73, log.read_text()
    occurrence = db.session.get(JobRun, 'test-renewal').occurrence_at
    expire_lease()
    recovered, log = start('run', 'recovered')
    assert recovered.wait(timeout=25) == 0, log.read_text()
    assert_one_generation(policy_id)
    row = db.session.get(JobRun, 'test-renewal')
    assert row.occurrence_at == occurrence and row.attempts == 2


def test_expired_lease_does_not_steal_long_running_execution(scheduler_processes):
    folder, start, policy_id = scheduler_processes
    (folder/'start').touch()
    first, log = start('hold', 'first')
    wait_file(folder/'holding-first', first, log)
    expire_lease()
    second, second_log = start('run', 'second')
    assert second.wait(timeout=20) == 0, second_log.read_text()
    assert '"ran": false' in second_log.read_text()
    (folder/'release-first').touch()
    assert first.wait(timeout=20) == 0, log.read_text()
    assert_one_generation(policy_id)


def test_lost_database_execution_lock_fences_stale_process(scheduler_processes):
    if db.engine.dialect.name != 'postgresql':
        pytest.skip('PostgreSQL backend-session ownership loss')
    folder, start, policy_id = scheduler_processes
    (folder/'start').touch()
    first, log = start('hold', 'first')
    wait_file(folder/'holding-first', first, log)
    pid = json.loads((folder/'holding-first').read_text())['pid']
    with db.engine.begin() as connection:
        assert connection.execute(text('SELECT pg_terminate_backend(:pid)'), {'pid': pid}).scalar_one()
    expire_lease()
    second, second_log = start('run', 'second')
    assert second.wait(timeout=20) == 0, second_log.read_text()
    (folder/'release-first').touch()
    assert first.wait(timeout=20) == 0, log.read_text()
    assert '"ran": false' in log.read_text()
    assert_one_generation(policy_id)

"""GC-027: current health, bounded work and dependency-independent liveness."""
from datetime import timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from app import db
from app.models import OcrSlot, JobRun
from app.utils.timeutils import utc_naive_now
from test_redis_session_boundary import redis_server


@pytest.fixture
def ready_app(app):
    app.config.update(SCHEDULER_ENABLED=False, OCR_WORKER_ENABLED=False,
                      REDIS_URL='memory://', RATELIMIT_ENABLED=False)
    with app.app_context(), db.engine.begin() as connection:
        connection.execute(text('CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)'))
        connection.execute(text('DELETE FROM alembic_version'))
        connection.execute(text('INSERT INTO alembic_version VALUES (:head)'),
                           {'head': app.extensions['readiness'].heads[0]})
    return app


def refresh(app):
    app.extensions['readiness'].expires = 0
    return app.test_client().get('/health/ready')


def test_ready_route_reports_current_schema_and_timestamps(ready_app):
    response = refresh(ready_app)
    assert response.status_code == 200 and response.json['status'] == 'ready'
    assert response.json['ready'] is True
    assert response.json['checked_at'] and response.headers['Cache-Control'] == 'no-store'
    assert response.json['checks']['schema']['status'] == 'ready'
    assert response.json['checks']['scheduler']['status'] == 'disabled'


@pytest.mark.parametrize('path', ['/health', '/health/live'])
def test_liveness_bypasses_sessions_request_hooks_and_database(app, monkeypatch, path):
    def forbidden(*args, **kwargs):
        raise AssertionError('Liveness touched an application dependency')
    monkeypatch.setattr(app.session_interface, 'open_session', forbidden)
    app.before_request(forbidden)
    with app.app_context():
        monkeypatch.setattr(db.engine, 'connect', forbidden)
    response = app.test_client().get(path, headers={'Cookie': 'session=existing-browser-cookie'})
    assert response.status_code == 200
    assert response.json['status'] in ('healthy', 'alive')
    assert not response.headers.getlist('Set-Cookie')
    assert app.test_client().head(path).data == b''
    assert app.test_client().post(path).status_code == 405


@pytest.mark.parametrize('revision', [None, 'gc026_session_authority', 'unknown_newer_revision'])
def test_migration_mismatch_blocks_readiness_but_not_liveness(ready_app, revision):
    with ready_app.app_context(), db.engine.begin() as connection:
        connection.execute(text('DELETE FROM alembic_version'))
        if revision:
            connection.execute(text('INSERT INTO alembic_version VALUES (:head)'), {'head': revision})
    response = refresh(ready_app)
    assert response.status_code == 503 and response.json['checks']['schema']['status'] == 'mismatch'
    assert ready_app.test_client().get('/health/live').status_code == 200
    with ready_app.app_context(), db.engine.begin() as connection:
        connection.execute(text('DELETE FROM alembic_version'))
        connection.execute(text('INSERT INTO alembic_version VALUES (:head)'),
                           {'head': ready_app.extensions['readiness'].heads[0]})
    assert refresh(ready_app).status_code == 200


def test_database_outage_and_recovery_are_current_and_redacted(ready_app):
    original = ready_app.extensions['readiness'].database_url
    assert refresh(ready_app).status_code == 200
    ready_app.extensions['readiness'].database_url = 'postgresql+psycopg2://canary:private-secret@127.0.0.1:1/private_database'
    response = refresh(ready_app)
    assert response.status_code == 503
    assert response.json['checks']['database']['status'] == 'unavailable'
    assert all(value not in response.get_data(as_text=True) for value in ('canary', 'private-secret', 'private_database', '127.0.0.1'))
    assert ready_app.test_client().get('/health/live').status_code == 200
    ready_app.extensions['readiness'].database_url = original
    assert refresh(ready_app).status_code == 200


def test_restore_maintenance_is_not_ready(ready_app):
    folder = Path(ready_app.config['BACKUP_FOLDER']) / '.restore'
    folder.mkdir(exist_ok=True)
    journal = folder / 'active.json'
    journal.write_text('{}')
    response = refresh(ready_app)
    assert response.status_code == 503 and response.json['checks']['restore']['status'] == 'maintenance'
    assert ready_app.test_client().get('/health/live').status_code == 200
    journal.unlink()
    assert refresh(ready_app).status_code == 200


@pytest.mark.parametrize('required', ['optional', 'browser_sessions', 'rate_limiter'])
def test_real_redis_outage_policy_and_recovery(ready_app, redis_server, required):
    ready_app.config['REDIS_URL'] = redis_server[3]
    if required == 'browser_sessions':
        ready_app.config['SESSION_TYPE'] = 'redis'
    elif required == 'rate_limiter':
        ready_app.config.update(RATELIMIT_ENABLED=True, RATELIMIT_STORAGE_URL=redis_server[3])
    assert refresh(ready_app).json['status'] == 'ready'
    redis_server[1].terminate()
    redis_server[1].wait(timeout=10)
    response = refresh(ready_app)
    assert response.status_code == (200 if required == 'optional' else 503)
    assert response.json['status'] == ('degraded' if required == 'optional' else 'not_ready')
    assert response.json['checks']['redis_cache']['status'] == 'unavailable'
    assert ready_app.test_client().get('/health/live').status_code == 200
    redis_server[2]()
    assert refresh(ready_app).json['status'] == 'ready'


def test_scheduler_and_real_ocr_consumer_progress_not_decoder_activity(ready_app):
    from app.services.ocr_queue import run_one
    from app.services.scheduler_registry import job_definitions
    from app.services.scheduler_ownership import seed_jobs, run_due_job
    ready_app.config.update(SCHEDULER_ENABLED=True, OCR_WORKER_ENABLED=True, OCR_MAX_CONCURRENCY=1)
    with ready_app.app_context():
        db.session.add(OcrSlot(id=1, revision=0, last_seen_at=utc_naive_now()))
        db.session.commit()
    response = refresh(ready_app)
    assert response.json['status'] == 'degraded'
    assert response.json['checks']['ocr_queue']['status'] == 'stale'
    ready_app.config['PROCESS_ROLE'] = 'worker'
    assert run_one(ready_app, 1) is False  # Idle polling still proves a real consumer.
    ready_app.config['PROCESS_ROLE'] = 'scheduler'
    jobs = {'readiness_heartbeat': job_definitions(ready_app)['readiness_heartbeat']}
    seed_jobs(ready_app, jobs)
    assert run_due_job(ready_app, 'readiness_heartbeat', jobs)
    assert refresh(ready_app).json['status'] == 'ready'
    with ready_app.app_context():
        db.session.get(OcrSlot, 1).consumer_seen_at = utc_naive_now() - timedelta(seconds=121)
        db.session.get(JobRun, 'readiness_heartbeat').last_success_at = utc_naive_now() - timedelta(seconds=61)
        db.session.commit()
    checks = refresh(ready_app).json['checks']
    assert checks['ocr_queue']['status'] == checks['scheduler']['status'] == 'stale'


def test_rq_probe_samples_live_heartbeat_and_detects_missing_consumer(ready_app, redis_server):
    client = redis_server[0]
    ready_app.config.update(REDIS_URL=redis_server[3], TASK_QUEUE_BACKEND='rq')
    assert refresh(ready_app).json['checks']['task_queue']['status'] == 'stale'
    client.sadd('rq:workers:gearcargo', 'rq:worker:fixture')
    client.hset('rq:worker:fixture', 'last_heartbeat', utc_naive_now().isoformat())
    assert refresh(ready_app).json['status'] == 'ready'
    client.delete('rq:worker:fixture')
    assert refresh(ready_app).json['status'] == 'degraded'


def test_cache_coalesces_bursts_and_expires(ready_app, monkeypatch):
    import app.services.readiness as module
    calls = []
    original = module.subprocess.run
    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(module.subprocess, 'run', counted)
    first = refresh(ready_app)
    for _ in range(30):
        assert ready_app.test_client().get('/health/ready').json == first.json
    assert len(calls) == 1
    time.sleep(module.CACHE_SECONDS + .05)
    assert ready_app.test_client().get('/health/ready').status_code == 200
    assert len(calls) == 2


def test_parallel_check_never_starts_an_extra_probe_or_returns_stale_green(ready_app, monkeypatch):
    import app.services.readiness as module
    assert refresh(ready_app).status_code == 200
    ready_app.extensions['readiness'].expires = 0
    started, release = threading.Event(), threading.Event()
    def blocked(*args, **kwargs):
        started.set()
        assert release.wait(timeout=5)
        return SimpleNamespace(stdout=json.dumps(module.unavailable('fixture')))
    monkeypatch.setattr(module.subprocess, 'run', blocked)
    responses = []
    thread = threading.Thread(target=lambda: responses.append(ready_app.test_client().get('/health/ready')))
    thread.start()
    try:
        assert started.wait(timeout=5)
        response = ready_app.test_client().get('/health/ready')
        assert response.status_code == 503 and response.json['checks']['probe']['status'] == 'checking'
    finally:
        release.set()
        thread.join(timeout=5)
    assert responses[0].status_code == 503


def test_hung_probe_is_killed_within_wall_deadline_and_recovers(ready_app, tmp_path):
    state = ready_app.extensions['readiness']
    original = state.script
    pidfile = tmp_path / 'probe.pid'
    hung = tmp_path / 'hung_probe.py'
    hung.write_text(f'import os,time\nopen({str(pidfile)!r}, "w").write(str(os.getpid()))\ntime.sleep(60)\n')
    state.script = hung
    started = time.monotonic()
    response = refresh(ready_app)
    elapsed = time.monotonic() - started
    assert response.status_code == 503 and response.json['checks']['probe']['status'] == 'timeout'
    assert 3.5 <= elapsed < 6
    with pytest.raises(ProcessLookupError):
        os.kill(int(pidfile.read_text()), 0)
    state.script = original
    assert refresh(ready_app).status_code == 200


def test_forked_worker_discards_inherited_cache_and_lock(ready_app, monkeypatch):
    state = ready_app.extensions['readiness']
    assert refresh(ready_app).status_code == 200
    inherited = state.lock
    inherited.acquire()
    state.pid = -1
    try:
        assert ready_app.test_client().get('/health/ready').status_code == 200
        assert state.lock is not inherited and state.pid == os.getpid()
    finally:
        inherited.release()


def test_sqlite_probe_never_creates_a_missing_database(ready_app, tmp_path):
    missing = tmp_path / 'must-not-be-created.sqlite'
    ready_app.extensions['readiness'].database_url = 'sqlite:///' + str(missing)
    assert refresh(ready_app).status_code == 503
    assert not missing.exists()


def test_consumer_timestamp_migration_preserves_activity_without_inventing_liveness(ready_app):
    import importlib.util
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect
    path = Path(__file__).parents[1] / 'migrations/versions/gc027_consumer_readiness.py'
    spec = importlib.util.spec_from_file_location('readiness_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with ready_app.app_context(), db.engine.begin() as connection:
        connection.execute(text('INSERT INTO ocr_slots (id, revision, last_seen_at) VALUES (1, 0, CURRENT_TIMESTAMP)'))
        connection.execute(text('ALTER TABLE ocr_slots DROP COLUMN consumer_seen_at'))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            old, consumer = connection.execute(text('SELECT last_seen_at, consumer_seen_at FROM ocr_slots WHERE id=1')).one()
            assert old is not None and consumer is None
            migration.downgrade()
            assert 'consumer_seen_at' not in {c['name'] for c in inspect(connection).get_columns('ocr_slots')}
            migration.upgrade()


def test_postgres_heartbeat_committed_during_probe_is_not_reported_stale(ready_app, monkeypatch):
    import readiness_probe
    from sqlalchemy import event
    with ready_app.app_context():
        if db.engine.dialect.name != 'postgresql':
            pytest.skip('PostgreSQL transaction-start clock regression')
        ready_app.config['SCHEDULER_ENABLED'] = True
        db.session.add(JobRun(job_name='readiness_heartbeat', status='idle', attempts=0, fence=0))
        db.session.commit()
        create_engine = readiness_probe.create_engine
        injected = []
        def instrumented_engine(*args, **kwargs):
            engine = create_engine(*args, **kwargs)
            @event.listens_for(engine, 'before_cursor_execute')
            def pulse_after_transaction_started(conn, cursor, statement, parameters, context, executemany):
                if statement.startswith('SELECT last_success_at'):
                    with db.engine.begin() as writer:
                        writer.execute(text("UPDATE scheduled_job_runs SET last_success_at=clock_timestamp() WHERE job_name='readiness_heartbeat'"))
                    injected.append(True)
            return engine
        monkeypatch.setattr(readiness_probe, 'create_engine', instrumented_engine)
        checks = {}
        readiness_probe.database_checks(ready_app.extensions['readiness'].specification(), checks)
        assert injected and checks['scheduler']['status'] == 'ready'


def test_instance_relative_sqlite_uses_the_same_database_as_the_application(ready_app, tmp_path):
    from app import create_app
    from app.config import TestingConfig
    import secrets
    config = type('RelativeConfig', (TestingConfig,), {
        **ready_app.config, 'SQLALCHEMY_DATABASE_URI': 'sqlite:///gc027-' + secrets.token_hex(8) + '.sqlite',
        'SESSION_TYPE': 'filesystem', 'REDIS_URL': 'memory://',
    })
    # create_app resolves relative SQLite URLs through Flask's instance folder.
    other = create_app(config)
    with other.app_context():
        engine_url = db.engine.url
        target = Path(engine_url.database)
        assert target.is_absolute()
        try:
            with db.engine.begin() as connection:
                connection.execute(text('CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)'))
                connection.execute(text('DELETE FROM alembic_version'))
                connection.execute(text('INSERT INTO alembic_version VALUES (:head)'),
                                   {'head': other.extensions['readiness'].heads[0]})
            assert other.test_client().get('/health/ready').status_code == 200
        finally:
            db.engine.dispose()
            target.unlink(missing_ok=True)

"""Durable occurrence cursors with execution locks and transaction fencing.

Lease expiry alone never steals an execution from a live database/file lock.
Every ORM transaction locks and validates its ownership row before doing work.
The cursor is advanced only after success; crashes retry the same occurrence.
"""
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import logging
import os
from pathlib import Path
import threading
from uuid import uuid4

from sqlalchemy import event, select, text, update, func
from sqlalchemy.orm import Session

from app import db
from app.models.job_run import JobRun

LEASE = timedelta(minutes=2)
MAX_ATTEMPTS = 5
active_run = ContextVar('scheduled_job_run', default=None)


class LostJobOwnership(BaseException):
    """Do not let a job's broad per-record Exception handler ignore fencing."""


def database_now(connection):
    value = connection.execute(select(func.current_timestamp())).scalar_one()
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def insert_for(connection, table):
    if connection.dialect.name == 'postgresql':
        from sqlalchemy.dialects.postgresql import insert
    elif connection.dialect.name == 'sqlite':
        from sqlalchemy.dialects.sqlite import insert
    else:
        raise RuntimeError('Scheduled ownership requires PostgreSQL or file-backed SQLite')
    return insert(table)


class ExecutionLock:
    def __init__(self, engine, name):
        self.engine, self.name = engine, name
        self.connection = None
        self.fd = None
        self.pid = None
        self.mutex = threading.Lock()
        self.lost = threading.Event()
        self.key = int.from_bytes(hashlib.sha256(('gearcargo-job:' + name).encode()).digest()[:8], 'big', signed=True)

    def acquire(self):
        if self.engine.dialect.name == 'postgresql':
            self.connection = self.engine.connect().execution_options(isolation_level='AUTOCOMMIT')
            if not self.connection.execute(text('SELECT pg_try_advisory_lock(:key)'), {'key': self.key}).scalar_one():
                self.close()
                return False
            self.pid = self.connection.execute(text('SELECT pg_backend_pid()')).scalar_one()
        elif self.engine.dialect.name == 'sqlite':
            database = self.engine.url.database
            if not database or database == ':memory:':
                raise RuntimeError('Scheduler requires file-backed SQLite or PostgreSQL')
            path = Path(database).absolute().with_name(Path(database).name + f'.job-{self.key}.lock')
            self.fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
            try:
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                self.close()
                return False
        else:
            raise RuntimeError('Unsupported scheduler database')
        return True

    def check(self):
        with self.mutex:
            if self.lost.is_set():
                raise LostJobOwnership()
            if self.connection is not None:
                try:
                    if self.connection.execute(text('SELECT pg_backend_pid()')).scalar_one() != self.pid:
                        raise RuntimeError('Reconnected execution lock')
                except Exception:
                    self.lost.set()
                    raise LostJobOwnership() from None

    def close(self):
        with self.mutex:
            self.lost.set()
            if self.connection is not None:
                try:
                    if self.pid is not None:
                        self.connection.execute(text('SELECT pg_advisory_unlock(:key)'), {'key': self.key})
                except Exception:
                    self.connection.invalidate()
                finally:
                    self.connection.close()
                    self.connection = None
            if self.fd is not None:
                os.close(self.fd)
                self.fd = None


@dataclass
class Run:
    name: str
    token: str
    fence: int
    occurrence: datetime
    lock: ExecutionLock
    reported_error: bool = False


@event.listens_for(Session, 'after_begin')
def fence_transaction(session, transaction, connection):
    run = active_run.get()
    if run is None or transaction.nested:
        return
    run.lock.check()
    row = connection.execute(select(JobRun.owner_token, JobRun.fence, JobRun.status)
        .where(JobRun.job_name == run.name).with_for_update()).first()
    if not row or (row.owner_token, row.fence, row.status) != (run.token, run.fence, 'running'):
        raise LostJobOwnership()


@event.listens_for(Session, 'before_commit')
def fence_commit(session):
    run = active_run.get()
    if run:
        run.lock.check()


class JobErrors(logging.Handler):
    def emit(self, record):
        run = active_run.get()
        if run and record.levelno >= logging.ERROR:
            run.reported_error = True


def seed_jobs(app, definitions):
    with app.app_context(), db.engine.begin() as connection:
        now = database_now(connection)
        for definition in definitions.values():
            due = now + timedelta(seconds=definition.start_after) if definition.start_after is not None else definition.next_time(now)
            connection.execute(insert_for(connection, JobRun.__table__).values(job_name=definition.name,
                next_due_at=due, status='idle', attempts=0, fence=0).on_conflict_do_nothing(index_elements=['job_name']))


def claim(connection, definition, lock):
    now = database_now(connection)
    row = connection.execute(select(JobRun.__table__).where(JobRun.job_name == definition.name).with_for_update()).mappings().first()
    if not row or row['status'] == 'failed' or not row['next_due_at'] or row['next_due_at'] > now:
        return None
    if row['status'] == 'running' and row['lease_until'] and row['lease_until'] > now:
        return None
    if row['next_attempt_at'] and row['next_attempt_at'] > now:
        return None
    token = str(uuid4())
    occurrence = row['occurrence_at'] if row['status'] in ('running', 'retry') else row['next_due_at']
    attempts = row['attempts'] + 1 if row['status'] in ('running', 'retry') else 1
    if attempts > MAX_ATTEMPTS:
        connection.execute(update(JobRun).where(JobRun.job_name == definition.name).values(status='failed',
            owner_token=None, lease_until=None, last_error='owner_loss_retry_exhausted', last_error_at=now))
        return None
    connection.execute(update(JobRun).where(JobRun.job_name == definition.name).values(status='running',
        owner_token=token, fence=row['fence'] + 1, occurrence_at=occurrence, attempts=attempts,
        lease_until=now + LEASE, last_started_at=now, next_attempt_at=None))
    return Run(definition.name, token, row['fence'] + 1, occurrence, lock)


def heartbeat(engine, run, stop):
    while not stop.wait(15):
        try:
            run.lock.check()
            with engine.begin() as connection:
                if connection.dialect.name == 'postgresql':
                    connection.execute(text("SET LOCAL lock_timeout = '1s'"))
                connection.execute(update(JobRun).where(JobRun.job_name == run.name,
                    JobRun.owner_token == run.token, JobRun.fence == run.fence)
                    .values(lease_until=database_now(connection) + LEASE))
        except LostJobOwnership:
            return
        except Exception:
            # A fenced business transaction may hold the cursor row. Its
            # execution lock still prevents takeover, even past the lease time.
            continue


def run_due_job(app, name, definitions=None):
    if app.config.get('PROCESS_ROLE') != 'scheduler':
        raise RuntimeError('Scheduled work requires the scheduler process role')
    from app.services.scheduler_registry import job_definitions
    from app.services.restore_transaction import guarded_app_context
    definitions = definitions or job_definitions(app)
    definition = definitions[name]
    with guarded_app_context(app):
        engine = db.engine
        lock = ExecutionLock(engine, name)
        if not lock.acquire():
            return False
        try:
            with engine.begin() as connection:
                run = claim(connection, definition, lock)
            if run is None:
                return False
            stop = threading.Event()
            pulse = threading.Thread(target=heartbeat, args=(engine, run, stop), daemon=True)
            pulse.start()
            context = active_run.set(run)
            errors = JobErrors()
            app.logger.addHandler(errors)
            failed = False
            try:
                definition.function(app)
                db.session.commit()
                lock.check()
                failed = run.reported_error
            except (Exception, LostJobOwnership):
                db.session.rollback()
                failed = True
            finally:
                active_run.reset(context)
                app.logger.removeHandler(errors)
                stop.set()
                pulse.join(timeout=5)
            if lock.lost.is_set():
                return False  # Leave the occurrence for recovery; never acknowledge a lost fence.
            with engine.begin() as connection:
                now = database_now(connection)
                row = connection.execute(select(JobRun.__table__).where(JobRun.job_name == name)).mappings().one()
                values = dict(owner_token=None, lease_until=None, last_finished_at=now)
                if failed:
                    values.update(status='failed' if row['attempts'] >= MAX_ATTEMPTS else 'retry',
                        next_attempt_at=now + timedelta(minutes=min(60, 2 ** (row['attempts'] - 1))),
                        last_error='job_failed', last_error_at=now)
                else:
                    values.update(status='idle', next_due_at=definition.next_time(now), next_attempt_at=None,
                                  last_success_at=now)
                changed = connection.execute(update(JobRun).where(JobRun.job_name == name, JobRun.owner_token == run.token,
                    JobRun.fence == run.fence).values(**values)).rowcount
            return bool(changed) and not failed
        finally:
            lock.close()


def scheduler_status():
    from app.services.scheduler_registry import job_definitions
    from flask import current_app
    enabled = job_definitions(current_app)
    with db.engine.connect() as connection:
        now = database_now(connection)
        rows = connection.execute(select(JobRun.__table__).order_by(JobRun.job_name)).mappings().all()
    return [dict(job=row['job_name'], enabled=row['job_name'] in enabled, status=row['status'], attempts=row['attempts'],
        occurrence_at=row['occurrence_at'].isoformat() if row['occurrence_at'] else None,
        next_due_at=row['next_due_at'].isoformat() if row['next_due_at'] else None,
        last_success_at=row['last_success_at'].isoformat() if row['last_success_at'] else None,
        last_error=row['last_error'], last_error_at=row['last_error_at'].isoformat() if row['last_error_at'] else None,
        lease_until=row['lease_until'].isoformat() if row['lease_until'] else None,
        lag_seconds=max(0, int((now - row['next_due_at']).total_seconds())) if row['next_due_at'] and row['job_name'] in enabled else 0)
        for row in rows]


def register_scheduler_cli(app):
    import click
    from app.services.scheduled_effects import register_delivery_cli
    register_delivery_cli(app)

    @app.cli.command('scheduler-status')
    def status():
        """Show persistent owner-independent job status and lag."""
        from app.services.scheduled_effects import delivery_status
        click.echo(json.dumps(dict(jobs=scheduler_status(), deliveries=delivery_status()), indent=2))

    @app.cli.command('scheduler-retry')
    @click.argument('job_name')
    def retry(job_name):
        """Retry a failed occurrence without replaying completed schedules."""
        with db.engine.begin() as connection:
            count = connection.execute(update(JobRun).where(JobRun.job_name == job_name,
                JobRun.status.in_(['retry', 'failed'])).values(status='retry', attempts=0,
                    next_attempt_at=database_now(connection))).rowcount
        click.echo(f'Queued {count} scheduled occurrence(s).')

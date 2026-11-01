"""Read-only, disposable dependency probe. Secrets arrive on stdin, never argv.

Keep this outside the app package: importing Flask's factory in the child would
initialize the very dependencies this probe must be able to time out safely.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from urllib.parse import quote
from sqlalchemy.pool import NullPool


def timestamp(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


def heartbeat(value, now, max_age):
    seen = timestamp(value)
    age = (now - seen).total_seconds() if seen else None
    return {'status': 'ready' if age is not None and 0 <= age <= max_age else 'stale',
            'last_seen_at': seen.isoformat() if seen else None,
            'stale_after_seconds': max_age}


@contextmanager
def restore_guard(folder):
    root = Path(folder)
    stream = None
    try:
        # Do not create files/directories from a monitoring request.
        if (root / 'lock').exists():
            stream = (root / 'lock').open('rb')
            fcntl.flock(stream, fcntl.LOCK_SH | fcntl.LOCK_NB)
        if (root / 'active.json').exists():
            raise BlockingIOError('maintenance')
        yield
    finally:
        if stream:
            stream.close()


def database_checks(config, checks):
    uri = config['database_url']
    options = {'connect_timeout': 2, 'options': '-c statement_timeout=750 -c lock_timeout=500'} if uri.startswith('postgresql') else {'timeout': .5}
    url = make_url(uri)
    if url.get_backend_name() == 'sqlite':
        if not url.database or url.database == ':memory:':
            raise ValueError('Readiness requires an existing file database')
        filename = url.database if url.database.startswith('file:') else 'file:' + quote(str(Path(url.database).resolve()), safe='/')
        url = url.set(database=filename, query={**url.query, 'mode': 'ro', 'uri': 'true'})
    engine = create_engine(url, poolclass=NullPool, connect_args=options)
    try:
        with engine.connect() as connection:
            connection.execute(text('SELECT 1'))
            if connection.dialect.name == 'postgresql':
                recovery, readonly = connection.execute(text("SELECT pg_is_in_recovery(), current_setting('transaction_read_only')")).one()
                if recovery or readonly == 'on':
                    checks['database'] = {'status': 'read_only'}
                    return
            checks['database'] = {'status': 'ready'}
            try:
                revisions = set(connection.execute(text('SELECT version_num FROM alembic_version LIMIT 8')).scalars())
            except Exception:
                checks['schema'] = {'status': 'unavailable'}
                return
            if revisions != set(config['schema_heads']) or not revisions:
                checks['schema'] = {'status': 'mismatch'}
                return
            checks['schema'] = {'status': 'ready'}
            scheduler_seen = None
            consumers = {}
            if config['scheduler_enabled']:
                scheduler_seen = connection.execute(text("SELECT last_success_at FROM scheduled_job_runs WHERE job_name = 'readiness_heartbeat' LIMIT 1")).scalar()
            if config['ocr_enabled']:
                consumers = dict(connection.execute(text('SELECT id, consumer_seen_at FROM ocr_slots WHERE id IN (1, 2) ORDER BY id')).all())
            # Read the clock after the heartbeats. PostgreSQL CURRENT_TIMESTAMP
            # is transaction-start time and can predate a just-committed pulse.
            clock_sql = 'SELECT clock_timestamp()' if connection.dialect.name == 'postgresql' else 'SELECT CURRENT_TIMESTAMP'
            now = timestamp(connection.execute(text(clock_sql)).scalar_one())
            if config['scheduler_enabled']:
                checks['scheduler'] = heartbeat(scheduler_seen, now, 60)
            if config['ocr_enabled']:
                workers = [dict(slot=slot, **heartbeat(consumers.get(slot), now, 120))
                           for slot in range(1, config['ocr_slots'] + 1)]
                checks['ocr_queue'] = {'status': 'ready' if all(w['status'] == 'ready' for w in workers) else 'stale', 'workers': workers}
    finally:
        engine.dispose()


def redis_checks(config, checks):
    from redis import Redis
    clients = {}
    for name, uri in config['redis_dependencies'].items():
        if not uri or uri == 'memory://':
            checks[name] = {'status': 'disabled'}
            continue
        try:
            if uri not in clients:
                client = Redis.from_url(uri.replace('redis+unix://', 'unix://', 1),
                                        socket_connect_timeout=.3, socket_timeout=.3, retry_on_timeout=False)
                clients[uri] = client
                client.ping()
            checks[name] = {'status': 'ready'}
            if name == 'task_queue':
                from rq.worker_registration import WORKERS_BY_QUEUE_KEY
                client = clients[uri]
                # A bounded sample, never SMEMBERS/KEYS or a queue-length scan.
                keys = client.srandmember(WORKERS_BY_QUEUE_KEY % config['queue_name'], 8)
                with client.pipeline(transaction=False) as pipe:
                    for key in keys:
                        pipe.hget(key, 'last_heartbeat')
                    values = pipe.execute()
                dates = [timestamp(value.decode()) for value in values if value]
                checks[name] = dict(heartbeat(max(dates) if dates else None, datetime.now(timezone.utc), 480),
                                    sampled_workers=len(keys))
        except Exception:
            checks[name] = {'status': 'unavailable'}
            # A failed connection may be reused by another required dependency;
            # that dependency must ping too, not inherit an unverified client.
            client = clients.pop(uri, None)
            if client:
                client.close()
    for client in clients.values():
        client.close()


def probe(config):
    checks = {'database': {'status': 'unknown'}, 'schema': {'status': 'unknown'},
              'restore': {'status': 'ready'},
              'scheduler': {'status': 'unknown' if config['scheduler_enabled'] else 'disabled'},
              'ocr_queue': {'status': 'unknown' if config['ocr_enabled'] else 'disabled'},
              'task_queue': {'status': 'in_process'}}
    try:
        with restore_guard(config['restore_folder']):
            try:
                database_checks(config, checks)
            except Exception:
                checks['database'] = {'status': 'unavailable'}
    except (BlockingIOError, OSError):
        checks['restore'] = {'status': 'maintenance'}
    redis_checks(config, checks)
    required = ['database', 'schema', 'restore', *config['required_redis']]
    ready = all(checks[name]['status'] == 'ready' for name in required)
    degraded = any(item['status'] not in ('ready', 'disabled', 'in_process') for item in checks.values())
    return {'status': ('degraded' if degraded else 'ready') if ready else 'not_ready',
            'ready': ready, 'checked_at': datetime.now(timezone.utc).isoformat(), 'checks': checks}


if __name__ == '__main__':
    try:
        print(json.dumps(probe(json.load(sys.stdin))))
    except Exception:
        # No URI, exception text, tokens, paths, row identifiers or job content.
        print(json.dumps({'status': 'not_ready', 'ready': False,
                          'checked_at': datetime.now(timezone.utc).isoformat(),
                          'checks': {'probe': {'status': 'unavailable'}}}))

"""Dependency-independent liveness and bounded, cached readiness.

A WSGI boundary avoids Flask session, CSRF, limiter and restore hooks. Checking a
broken dependency must not itself require that dependency to open a session.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

from alembic.script import ScriptDirectory
from werkzeug.wrappers import Response

CACHE_SECONDS = 5
PROBE_TIMEOUT = 4
HEALTH_PATHS = frozenset(('/health', '/health/live', '/health/ready'))


def unavailable(reason):
    return {'status': 'not_ready', 'ready': False,
            'checked_at': datetime.now(timezone.utc).isoformat(),
            'checks': {'probe': {'status': reason}}}


class Readiness:
    def __init__(self, app):
        self.app = app
        # Use Flask-SQLAlchemy's resolved URL (notably instance-relative SQLite),
        # without opening a connection or borrowing the application's pool.
        from app import db
        with app.app_context():
            self.database_url = db.engine.url.render_as_string(hide_password=False)
        self.script = Path(app.root_path).parent / 'readiness_probe.py'
        self.heads = ScriptDirectory(str(Path(app.root_path).parent / 'migrations')).get_heads()
        self.pid = None
        self.reset()

    def reset(self):
        self.pid = os.getpid()
        self.lock = threading.Lock()
        self.cached = None
        self.expires = 0

    def specification(self):
        config = self.app.config
        redis = config.get('REDIS_URL')
        dependencies = {'redis_cache': redis}
        required = []
        if config.get('SESSION_TYPE') == 'redis':
            dependencies['browser_sessions'] = redis
            required.append('browser_sessions')
        limiter = config.get('RATELIMIT_STORAGE_URL', redis)
        if config.get('RATELIMIT_ENABLED', True) and limiter != 'memory://':
            dependencies['rate_limiter'] = limiter
            required.append('rate_limiter')
        if config.get('TASK_QUEUE_BACKEND') == 'rq':
            dependencies['task_queue'] = redis
        return dict(database_url=self.database_url, schema_heads=self.heads,
                    restore_folder=str(config.get('RESTORE_STATE_FOLDER') or Path(config['BACKUP_FOLDER']) / '.restore'),
                    scheduler_enabled=config.get('SCHEDULER_ENABLED', True),
                    ocr_enabled=config.get('OCR_WORKER_ENABLED', True),
                    ocr_slots=config.get('OCR_MAX_CONCURRENCY', 2),
                    redis_dependencies=dependencies, required_redis=required,
                    queue_name=config.get('TASK_QUEUE_NAME', 'gearcargo'))

    def check(self):
        # Gunicorn preload must never share a populated cache/lock across forks.
        if self.pid != os.getpid():
            self.reset()
        if self.cached is not None and time.monotonic() < self.expires:
            return self.cached
        if not self.lock.acquire(blocking=False):
            # Never serve an expired green response while another check is stuck.
            return unavailable('checking')
        try:
            if self.cached is not None and time.monotonic() < self.expires:
                return self.cached
            try:
                result = subprocess.run([sys.executable, str(self.script)],
                    input=json.dumps(self.specification()), text=True, stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL, timeout=PROBE_TIMEOUT, check=True)
                payload = json.loads(result.stdout)
                if not isinstance(payload.get('ready'), bool) or 'checks' not in payload:
                    raise ValueError('Invalid probe result')
            except subprocess.TimeoutExpired:
                payload = unavailable('timeout')
            except Exception:
                payload = unavailable('unavailable')
            self.cached = payload
            self.expires = time.monotonic() + CACHE_SECONDS
            return payload
        finally:
            self.lock.release()


class HealthMiddleware:
    def __init__(self, wrapped, app, startup_redis):
        self.wrapped = wrapped
        self.readiness = Readiness(app)
        self.startup_redis = startup_redis

    def __call__(self, environ, start_response):
        path = environ.get('PATH_INFO')
        if path not in HEALTH_PATHS:
            return self.wrapped(environ, start_response)
        headers = {'Cache-Control': 'no-store'}
        if environ.get('REQUEST_METHOD') not in ('GET', 'HEAD'):
            return Response(status=405, headers={**headers, 'Allow': 'GET, HEAD'})(environ, start_response)
        from app.routes.system import _load_build_info
        if path == '/health/ready':
            payload = {**self.readiness.check(), 'cache_seconds': CACHE_SECONDS,
                       'probe_timeout_seconds': PROBE_TIMEOUT}
            status = 200 if payload['ready'] else 503
            if status == 503:
                headers['Retry-After'] = str(CACHE_SECONDS)
        else:
            payload = {'status': 'healthy' if path == '/health' else 'alive'}
            if path == '/health':
                payload['redis_ok'] = self.startup_redis  # Legacy startup field only.
            status = 200
        payload.update(app='GearCargo', version=_load_build_info().get('version', '0.0.0'))
        return Response(json.dumps(payload), status=status, mimetype='application/json', headers=headers)(environ, start_response)


def install_readiness(app, startup_redis):
    middleware = HealthMiddleware(app.wsgi_app, app, startup_redis)
    app.wsgi_app = middleware
    app.extensions['readiness'] = middleware.readiness

# GearCargo - Gunicorn Configuration

import multiprocessing
import os

# Server socket
bind = "0.0.0.0:5000"
backlog = 2048

# Worker processes — capped at 4 by default to stay within the container's
# 1 GB memory budget (each sync worker uses ~50-100 MB).
# Override via GUNICORN_WORKERS env var if you run with more RAM.
workers = int(os.environ.get("GUNICORN_WORKERS", min(multiprocessing.cpu_count() * 2 + 1, 4)))
worker_class = "sync"
worker_connections = 1000
timeout = int(os.environ.get("GUNICORN_TIMEOUT", 360))
keepalive = 5
max_requests = 1000
max_requests_jitter = 50

# Server mechanics
daemon = False
pidfile = None
# I08: umask 0o027 → new files are created as 0o640 (owner rw, group r, others none).
# umask = 0 (the gunicorn default) would leave every temp upload and log file
# world-readable before an explicit chmod is applied, exposing partial file
# content to other processes in the container.
umask = 0o027
user = None
group = None
tmp_upload_dir = None

# Logging
errorlog = "-"
accesslog = "-"
loglevel = os.environ.get("LOG_LEVEL", "info")
# Only trusted route templates and server-generated IDs reach the formatter.
# Queries, referrers, user agents and arbitrary headers are deliberately absent.
logger_class = 'gearcargo_gunicorn_logger.CapabilitySafeLogger'
access_log_format = '%(t)s method=%(m)s route=%(gc_route)s status=%(s)s bytes=%(b)s duration_us=%(D)s request_id=%(gc_request_id)s'

# Process naming
proc_name = "gearcargo"

# Preload shares code objects. Schedules run only in scheduler.py, never in
# the web master or workers. Keep the established post_fork pool disposal:
# preloading still requires workers to discard inherited database connections.
preload_app = True

def _resolve_flask_app(server, worker):
    """Best-effort resolution of the preloaded Flask app from inside a worker.

    With preload_app=True gunicorn loads the WSGI app (our Flask app) in the
    arbiter and workers inherit it as ``worker.app.callable`` (``server`` is the
    arbiter and also carries it). Flask-SQLAlchemy 3.x has NO ``get_app()`` and
    there is no application context in post_fork, so we resolve the app object
    here to obtain one. Returns None if it cannot be found.
    """
    for obj in (worker, server):
        candidate = getattr(getattr(obj, "app", None), "callable", None)
        if candidate is not None:
            return candidate
    return None


def post_fork(server, worker):
    """
    Called in each worker immediately after fork().

    With preload_app=True the master has already called create_app().
    Dispose the SQLAlchemy connection pool: file-descriptors for DB
    connections opened in the master must not be shared across processes or
    queries will corrupt each other's results.
    """
    # 1. Drop the DB connections inherited from the preload master so each
    #    worker lazily opens its OWN — mandatory with preload_app=True.
    #
    #    Two details are critical (regressions here cause the post-restart
    #    PGRES_TUPLES_OK / ResourceClosedError storms):
    #      * FSA 3.x reaches the engine via current_app, so dispose MUST run
    #        inside an application context — the previous bare ``db.engine``
    #        call raised "working outside of application context" and the
    #        ``except: pass`` swallowed it, leaving the pool shared.
    #      * Use ``dispose(close=False)``: drop the pool's references WITHOUT
    #        closing the inherited file descriptors — those sockets are still
    #        in use by the master, and closing them here would corrupt it.
    try:
        from app import db
        flask_app = _resolve_flask_app(server, worker)
        if flask_app is None:
            raise RuntimeError("could not resolve the preloaded Flask app")
        with flask_app.app_context():
            db.engine.dispose(close=False)
        server.log.info("post_fork[pid %s]: disposed inherited DB connection pool", worker.pid)
    except Exception as e:
        # Never swallow silently — a regression here re-introduces the
        # cross-process connection-sharing outage and must be visible.
        server.log.warning(
            "post_fork[pid %s]: DB pool dispose failed (%s) — workers may share "
            "the master's connections", getattr(worker, "pid", "?"), e
        )

    # 2. Defensive cleanup for a stale/third-party preload hook. The normal web
    #    factory starts no scheduler; scheduler.py owns that process role.
    try:
        from app.services import scheduler
        if scheduler.running:
            scheduler.shutdown(wait=False)
    except Exception:
        pass

# SSL (handled by external reverse proxy)
# keyfile = None
# certfile = None

# Hooks
def on_starting(server):
    """Called before the master process is initialized."""
    pass

def on_reload(server):
    """Called before reloading."""
    pass

def worker_int(worker):
    """Called when a worker receives SIGINT or SIGQUIT."""
    pass

def worker_abort(worker):
    """Called when a worker receives SIGABRT."""
    pass

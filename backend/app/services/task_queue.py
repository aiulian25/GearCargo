"""
Background task queue abstraction (IMPROVEMENTS §5 / §1.5 S12).

A single ``enqueue_task()`` entry point so the scattered ``threading.Thread``
call sites no longer hand-roll background execution. Two interchangeable
backends, chosen by ``TASK_QUEUE_BACKEND``:

* ``thread`` (DEFAULT) — fire-and-forget daemon thread inside the web worker,
  exactly the historical behaviour. Nothing changes for existing deployments.
* ``rq`` — enqueue onto **RQ on the existing Redis**, executed by a separate
  ``rq_worker.py`` process. Gives real process isolation for heavy work (OCR)
  off the request workers, and survives web-worker restarts.

The task function and its arguments MUST be import-by-reference and picklable
for the ``rq`` backend (module-level function, primitive args). Both backends
run the task inside a Flask application context, so tasks may use ``db`` and
``current_app`` freely.

If ``rq`` is requested but unavailable (package missing or Redis down), we log
once and fall back to the thread backend so a misconfiguration never silently
drops work.
"""

import logging
import threading

from flask import current_app

logger = logging.getLogger(__name__)

_THREAD = 'thread'
_RQ = 'rq'

# Remember whether we've already warned about an RQ fallback, to avoid log spam.
_warned_rq_fallback = False


def resolve_backend(configured: str, rq_available: bool) -> str:
    """Pure backend selector (unit-testable without an app).

    Returns ``'rq'`` only when explicitly requested AND usable; otherwise
    ``'thread'``.
    """
    if str(configured or '').strip().lower() == _RQ and rq_available:
        return _RQ
    return _THREAD


def _rq_queue():
    """Return an RQ Queue bound to the app's Redis, or None if unavailable."""
    try:
        from redis import Redis
        from rq import Queue
    except Exception:
        return None
    try:
        redis_url = current_app.config.get('REDIS_URL')
        if not redis_url:
            return None
        conn = Redis.from_url(redis_url)
        conn.ping()  # fail fast if Redis is down → caller falls back to thread
        name = current_app.config.get('TASK_QUEUE_NAME', 'gearcargo')
        timeout = int(current_app.config.get('TASK_QUEUE_DEFAULT_TIMEOUT', 600))
        return Queue(name, connection=conn, default_timeout=timeout)
    except Exception as exc:
        logger.warning('Task queue: RQ/Redis unavailable (%s)', type(exc).__name__)
        return None


def _spawn_thread(func, args, kwargs):
    """Run *func* in a daemon thread, inside the current app context."""
    try:
        app = current_app._get_current_object()
    except RuntimeError:
        app = None

    def _runner():
        if app is not None:
            with app.app_context():
                func(*args, **kwargs)
        else:
            func(*args, **kwargs)

    threading.Thread(target=_runner, daemon=True).start()
    return None


def enqueue_task(func, *args, description=None, **kwargs):
    r"""Enqueue ``func(*args, **kwargs)`` for background execution.

    Returns the RQ ``Job`` (rq backend) or ``None`` (thread backend). Callers
    treat the work as fire-and-forget; status, when needed, is tracked in the
    domain model (e.g. ``Attachment.ocr_processed``), not the queue.
    """
    global _warned_rq_fallback

    configured = current_app.config.get('TASK_QUEUE_BACKEND', _THREAD)

    if str(configured or '').strip().lower() == _RQ:
        queue = _rq_queue()
        if queue is not None:
            return queue.enqueue(func, *args, description=description, **kwargs)
        if not _warned_rq_fallback:
            logger.warning(
                'TASK_QUEUE_BACKEND=rq but the queue is unavailable; '
                'falling back to in-process threads.'
            )
            _warned_rq_fallback = True

    return _spawn_thread(func, args, kwargs)


def build_worker(app):
    """Build an RQ worker bound to the app's queue/Redis.

    Used by rq_worker.py. Uses ``SimpleWorker`` (no fork) so the app context
    pushed by the worker entrypoint stays active for every job.
    """
    from redis import Redis
    from rq import Queue, SimpleWorker

    conn = Redis.from_url(app.config['REDIS_URL'])
    name = app.config.get('TASK_QUEUE_NAME', 'gearcargo')
    return SimpleWorker([Queue(name, connection=conn)], connection=conn)

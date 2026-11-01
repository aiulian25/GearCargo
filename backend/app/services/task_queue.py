"""Generic background tasks (OCR uses the durable database queue instead).

The legacy thread backend has two workers and at most 100 waiting tasks per
process. Explicit RQ configuration fails visibly when unavailable; it never
falls back to threads. Importable legacy OCR jobs only admit durable work.
"""

from app.services.restore_transaction import guarded_app_context
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from flask import current_app

logger = logging.getLogger(__name__)

_THREAD = 'thread'
_RQ = 'rq'

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='gearcargo-task')
_capacity = threading.BoundedSemaphore(102)


class QueueUnavailable(RuntimeError):
    pass


def resolve_backend(configured: str, rq_available: bool) -> str:
    """Pure backend selector (unit-testable without an app).

    Explicit RQ unavailability returns 'unavailable', never a thread fallback.
    """
    if str(configured or '').strip().lower() == _RQ:
        return _RQ if rq_available else 'unavailable'
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
        conn.ping()  # Fail fast without changing execution guarantees.
        name = current_app.config.get('TASK_QUEUE_NAME', 'gearcargo')
        timeout = int(current_app.config.get('TASK_QUEUE_DEFAULT_TIMEOUT', 600))
        return Queue(name, connection=conn, default_timeout=timeout)
    except Exception as exc:
        logger.warning('Task queue: RQ/Redis unavailable (%s)', type(exc).__name__)
        return None


def _spawn_thread(func, args, kwargs):
    """Run *func* in the bounded pool, inside the current app context."""
    try:
        app = current_app._get_current_object()
    except RuntimeError:
        app = None

    capacity = _capacity
    if not capacity.acquire(blocking=False):
        raise QueueUnavailable('Background task queue is full')

    def _runner():
        try:
            if app is not None:
                with guarded_app_context(app):
                    func(*args, **kwargs)
            else:
                func(*args, **kwargs)
        finally:
            capacity.release()

    try:
        _executor.submit(_runner)
    except Exception:
        capacity.release()
        raise
    return None


def enqueue_task(func, *args, description=None, **kwargs):
    r"""Enqueue ``func(*args, **kwargs)`` for background execution.

    Returns the RQ ``Job`` (rq backend) or ``None`` (thread backend). Callers
    treat the work as fire-and-forget; status, when needed, is tracked in the
    caller's domain model. OCR admission does not use this generic API.
    """
    configured = current_app.config.get('TASK_QUEUE_BACKEND', _THREAD)

    if str(configured or '').strip().lower() == _RQ:
        queue = _rq_queue()
        if queue is not None:
            return queue.enqueue(func, *args, description=description, **kwargs)
        raise QueueUnavailable('Configured RQ queue is unavailable; no fallback execution was started')

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

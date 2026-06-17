"""Unit tests for the background task queue abstraction.

See app/services/task_queue.py. ``resolve_backend`` is a pure selector; the
thread-execution test uses the app fixture and a short timeout.
"""

import threading

from app.services.task_queue import resolve_backend, enqueue_task


# ── resolve_backend (pure) ─────────────────────────────────────────────────────

def test_default_is_thread():
    assert resolve_backend("thread", rq_available=True) == "thread"
    assert resolve_backend(None, rq_available=True) == "thread"
    assert resolve_backend("", rq_available=True) == "thread"


def test_rq_only_when_requested_and_available():
    assert resolve_backend("rq", rq_available=True) == "rq"
    # Requested but unavailable → safe fallback to thread.
    assert resolve_backend("rq", rq_available=False) == "thread"


def test_backend_value_is_case_insensitive_and_trimmed():
    assert resolve_backend("  RQ  ", rq_available=True) == "rq"
    assert resolve_backend("Thread", rq_available=True) == "thread"


def test_unknown_backend_falls_back_to_thread():
    assert resolve_backend("celery", rq_available=True) == "thread"


# ── enqueue_task thread backend (integration) ──────────────────────────────────

def test_thread_backend_runs_task_in_app_context(app):
    from flask import has_app_context

    done = threading.Event()
    captured = {}

    def task(value):
        captured["value"] = value
        captured["had_context"] = has_app_context()
        done.set()

    with app.app_context():
        # Default config backend is 'thread'.
        result = enqueue_task(task, 42)
        assert result is None  # thread backend returns no job handle

    assert done.wait(timeout=5), "background task did not run"
    assert captured["value"] == 42
    assert captured["had_context"] is True  # task ran inside an app context

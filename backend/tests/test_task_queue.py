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
    # Requested but unavailable must not change execution guarantees.
    assert resolve_backend("rq", rq_available=False) == "unavailable"


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


def test_unavailable_rq_never_starts_a_fallback_thread(app, monkeypatch):
    import pytest
    from app.services import task_queue
    monkeypatch.setattr(task_queue, '_rq_queue', lambda: None)
    monkeypatch.setattr(task_queue, '_spawn_thread', lambda *args: pytest.fail('Unsafe fallback'))
    with app.app_context():
        app.config['TASK_QUEUE_BACKEND'] = 'rq'
        with pytest.raises(RuntimeError):
            enqueue_task(lambda: None)


def test_thread_backend_bounds_running_and_waiting_tasks(monkeypatch):
    import pytest
    from concurrent.futures import ThreadPoolExecutor
    from app.services import task_queue
    release = threading.Event()
    started = threading.Barrier(3)
    count = 0
    mutex = threading.Lock()
    def task():
        nonlocal count
        with mutex:
            count += 1
            position = count
        if position <= 2:
            started.wait(timeout=5)
        release.wait(timeout=5)
    with ThreadPoolExecutor(max_workers=2) as executor:
        monkeypatch.setattr(task_queue, '_executor', executor)
        monkeypatch.setattr(task_queue, '_capacity', threading.BoundedSemaphore(102))
        try:
            for _ in range(102): task_queue._spawn_thread(task, (), {})
            started.wait(timeout=5)
            assert count == 2
            with pytest.raises(task_queue.QueueUnavailable):
                task_queue._spawn_thread(task, (), {})
        finally:
            release.set()
    assert count == 102

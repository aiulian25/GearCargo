"""Dedicated scheduler process: python scheduler.py (never started by create_app)."""
import signal
import threading

from app import create_app
from app.services import init_scheduler, scheduler


def main():
    app = create_app(process_role='scheduler')
    stopped = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stopped.set())
    init_scheduler(app)
    try:
        stopped.wait()
    finally:
        scheduler.shutdown(wait=True)


if __name__ == '__main__':
    main()

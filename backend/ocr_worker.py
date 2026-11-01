"""One supervised OCR slot per process; replicas contend for two fixed slots."""
import argparse
import signal
import threading
import time
from app import create_app
from app.services.ocr_queue import run_one, backfill


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--slot', type=int, choices=(1, 2), required=True)
    slot = parser.parse_args().slot
    app = create_app(process_role='worker')
    stopped = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stopped.set())
    next_backfill = 0
    while not stopped.is_set():
        try:
            if time.monotonic() >= next_backfill:
                from app.services.restore_transaction import guarded_app_context
                with guarded_app_context(app):
                    backfill()
                next_backfill = time.monotonic() + 30
            worked = run_one(app, slot)
        except Exception:
            app.logger.exception('OCR worker could not access the durable queue')
            worked = False
        if not worked:
            stopped.wait(2)


if __name__ == '__main__':
    main()

"""Independent processes used by GC-025 integration acceptance tests."""
import fcntl
import json
import os
from pathlib import Path
import sys
import time
from app import create_app, db
from app.config import TestingConfig
from app.models import Attachment
from app.services.ocr_queue import enqueue_attachment, run_one, compute


def main():
    settings, folder, mode, label = sys.argv[1:]
    app = create_app(type('ProcessConfig', (TestingConfig,), json.loads(Path(settings).read_text())), process_role='worker')
    control = Path(folder)
    (control/f'ready-{label}').touch()
    deadline = time.monotonic() + 45
    while not (control/'start').exists():
        if time.monotonic() > deadline:
            raise RuntimeError('Fixture start timeout')
        time.sleep(.02)
    if mode == 'submit':
        with app.app_context():
            ids = [row.id for row in Attachment.query.order_by(Attachment.id).all()]
            for identity in ids:
                enqueue_attachment(db.session.get(Attachment, identity))
                db.session.commit()
        return
    def measured(work, lock):
        with (control/'events.jsonl').open('a') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            stream.write(json.dumps({'event': 'start', 'pid': os.getpid(), 'attachment': work.attachment_id})+'\n')
        try:
            if mode in ('hold', 'hold2'):
                (control/f'holding-{label}').write_text(str(lock.pid))
                while not (control/f'release-{label}').exists():
                    if time.monotonic() > deadline:
                        raise RuntimeError('Fixture release timeout')
                    time.sleep(.02)
            time.sleep(.15)
            return compute(work, lock)
        finally:
            with (control/'events.jsonl').open('a') as stream:
                fcntl.flock(stream, fcntl.LOCK_EX)
                stream.write(json.dumps({'event': 'end', 'pid': os.getpid(), 'attachment': work.attachment_id})+'\n')
    if mode == 'child':
        print(json.dumps({'ran': run_one(app, 1)}), flush=True)
        return
    if mode in ('hold', 'hold2'):
        print(json.dumps({'ran': run_one(app, 2 if mode == 'hold2' else 1, measured)}), flush=True)
        return
    for _ in range(25):
        if not any(run_one(app, slot, measured) for slot in (1, 2)):
            time.sleep(.05)


if __name__ == '__main__':
    main()

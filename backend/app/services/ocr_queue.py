"""Bounded database OCR queue. Web requests never launch recognition work."""
from dataclasses import dataclass
from datetime import timedelta
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
from tempfile import TemporaryDirectory
from uuid import uuid4

from flask import current_app
from sqlalchemy import select, update, func, or_

from app import db
from app.models import Attachment, OcrSlot
from app.services.scheduler_ownership import ExecutionLock, LostJobOwnership, database_now, insert_for
from app.services.restore_transaction import guarded_app_context

ACTIVE = ('queued', 'running', 'retry')
MAX_ATTEMPTS = 3
JOB_TIMEOUT = 90
# Longer than the independent child deadline, including bounded decoder children.
LEASE = timedelta(seconds=180)


def supported(attachment):
    return bool(attachment.is_image or attachment.is_pdf or attachment.filename.lower().endswith('.pdf'))


def admission():
    connection = db.session.connection()
    for slot in range(3):
        connection.execute(insert_for(connection, OcrSlot.__table__).values(id=slot, revision=0)
            .on_conflict_do_nothing(index_elements=['id']))
    # A write also serializes admission on SQLite, where FOR UPDATE is ignored.
    connection.execute(update(OcrSlot).where(OcrSlot.id == 0).values(revision=OcrSlot.revision + 1))
    return connection


def enqueue_attachment(attachment, *, force=False):
    """Join the caller's transaction; an active attachment has only one intent."""
    if not supported(attachment):
        return None
    if attachment.ocr_state in ACTIVE:
        return attachment.ocr_state
    if attachment.ocr_processed and not force:
        return 'done'
    if not current_app.config.get('OCR_WORKER_ENABLED', True):
        attachment.ocr_state, attachment.ocr_error = 'unavailable', 'worker_disabled'
        return 'unavailable'
    try:
        with db.session.begin_nested():
            connection = admission()
            db.session.refresh(attachment, attribute_names=['revision', 'ocr_state', 'ocr_processed', 'ocr_generation'])
            if attachment.ocr_state in ACTIVE:
                return attachment.ocr_state
            if attachment.ocr_processed and not force:
                return 'done'
            count = connection.execute(select(func.count()).select_from(Attachment)
                .where(Attachment.ocr_state.in_(ACTIVE))).scalar_one()
            if count >= current_app.config.get('OCR_MAX_PENDING', 100):
                attachment.ocr_state, attachment.ocr_error = 'failed', 'queue_full'
                return 'failed'
            attachment.ocr_state = 'queued'
            attachment.ocr_attempts = 0
            attachment.ocr_generation = (attachment.ocr_generation or 0) + 1
            attachment.ocr_owner = attachment.ocr_lease_until = attachment.ocr_error = None
            attachment.ocr_next_attempt_at = database_now(connection)
            attachment.ocr_processed = False
            attachment.ocr_text = None
            db.session.flush()
    except Exception:
        # A failed OCR savepoint must not discard an otherwise valid receipt/expense.
        attachment.ocr_state, attachment.ocr_error = 'unavailable', 'queue_unavailable'
        current_app.logger.warning('OCR admission unavailable', exc_info=True)
    return attachment.ocr_state


def backfill(*, force=False, after_id=0):
    """Admit one bounded page. Never allocate a thread or load all attachments."""
    connection = admission()
    count = connection.execute(select(func.count()).select_from(Attachment)
        .where(Attachment.ocr_state.in_(ACTIVE))).scalar_one()
    room = max(0, current_app.config.get('OCR_MAX_PENDING', 100) - count)
    query = Attachment.query.filter(Attachment.id > after_id,
        or_(Attachment.file_type.like('image/%'), Attachment.file_type == 'application/pdf',
            Attachment.filename.ilike('%.pdf')),
        or_(Attachment.ocr_state.is_(None), ~Attachment.ocr_state.in_(ACTIVE)))
    if not force:
        query = query.filter(Attachment.ocr_processed.isnot(True), Attachment.ocr_state.is_(None))
    rows = query.order_by(Attachment.id).limit(min(100, room)).all() if room else []
    queued = skipped = 0
    for attachment in rows:
        if not Path(attachment.filepath).is_file() and not Path(attachment.filepath + '.tmp').is_file():
            attachment.ocr_state, attachment.ocr_error = 'failed', 'file_missing'
            skipped += 1
            continue
        if enqueue_attachment(attachment, force=force) == 'queued':
            queued += 1
    db.session.commit()
    return dict(queued=queued, skipped_no_file=skipped, capacity_remaining=max(0, room-queued),
                next_after_id=rows[-1].id if rows else after_id, batch_limit=100)


@dataclass
class Claim:
    slot: int
    attachment_id: int
    generation: int
    token: str
    filepath: str
    kind: str
    deadline: object


def claim(slot):
    connection = admission()
    now = database_now(connection)
    owner = db.session.get(OcrSlot, slot, populate_existing=True)
    owner.last_seen_at = owner.consumer_seen_at = now
    if owner.lease_until and owner.lease_until > now:
        db.session.commit()
        return None
    if owner.owner:
        stale = db.session.query(Attachment).filter_by(ocr_owner=owner.owner, ocr_state='running').first()
        if stale:
            stale.ocr_state = 'failed' if stale.ocr_attempts >= MAX_ATTEMPTS else 'retry'
            stale.ocr_error = 'worker_lost'
            stale.ocr_next_attempt_at = now
            stale.ocr_owner = stale.ocr_lease_until = None
        owner.owner = owner.attachment_id = owner.lease_until = None
        db.session.flush()
    row = Attachment.query.filter(Attachment.ocr_state.in_(('queued', 'retry')),
        Attachment.ocr_next_attempt_at <= now, Attachment.ocr_attempts < MAX_ATTEMPTS
        ).order_by(Attachment.ocr_next_attempt_at, Attachment.id).first()
    if not row:
        db.session.commit()
        return None
    token = str(uuid4())
    deadline = now + LEASE
    owner.owner, owner.attachment_id, owner.lease_until = token, row.id, deadline
    row.ocr_owner, row.ocr_lease_until, row.ocr_state = token, deadline, 'running'
    row.ocr_attempts += 1
    result = Claim(slot, row.id, row.ocr_generation, token, row.filepath,
                   'pdf' if row.is_pdf or row.filename.lower().endswith('.pdf') else 'image', deadline)
    db.session.commit()
    db.session.remove()
    return result


def kill_process(process):
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=5)


def compute(work, lock):
    """Bound the whole OCR/PDF operation, including memory and child lifetime."""
    path = Path(work.filepath)
    # Recover a committed upload whose process died before its activation callback.
    if not path.exists() and Path(str(path) + '.tmp').is_file():
        os.replace(str(path) + '.tmp', path)
    if not path.is_file():
        return None, 'file_missing'
    with db.engine.connect() as connection:
        if database_now(connection) + timedelta(seconds=JOB_TIMEOUT + 30) >= work.deadline:
            return None, 'claim_expired'
    lock.check()
    with TemporaryDirectory(prefix='gc-ocr-') as folder:
        output = Path(folder) / 'result.json'
        with output.open('wb') as stream:
            process = subprocess.Popen([sys.executable, '-m', 'app.services.ocr_compute', work.kind, str(path)],
                stdout=stream, stderr=subprocess.DEVNULL, start_new_session=True,
                env={**os.environ, 'GC_OCR_PARENT_PID': str(os.getpid()),
                     'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1'})
            try:
                for _ in range(JOB_TIMEOUT + 2):
                    try:
                        process.wait(timeout=1)
                        break
                    except subprocess.TimeoutExpired:
                        lock.check()
                else:
                    kill_process(process)
                    return None, 'processing_timeout'
            finally:
                # Native children can outlive a crashed/CPU-killed Python parent.
                # Reap the whole group before releasing its processing slot.
                kill_process(process)
        if process.returncode:
            return None, 'processing_failed'
        try:
            if output.stat().st_size > 100_000:
                raise ValueError('Oversized OCR result')
            result = json.loads(output.read_text())
            if not isinstance(result, dict) or not isinstance(result.get('text'), str):
                raise ValueError('Invalid OCR result')
            return result['text'][:10000] or None, None
        except (ValueError, OSError):
            return None, 'processing_failed'


def finish(work, text, error, lock):
    lock.check()
    connection = admission()
    now = database_now(connection)
    row = Attachment.query.filter_by(id=work.attachment_id, ocr_owner=work.token,
        ocr_generation=work.generation, ocr_state='running').first()
    if row:
        row.ocr_owner = row.ocr_lease_until = None
        row.ocr_error = error
        if error:
            row.ocr_state = 'failed' if row.ocr_attempts >= MAX_ATTEMPTS or error == 'file_missing' else 'retry'
            row.ocr_next_attempt_at = now + timedelta(seconds=30 * 2 ** (row.ocr_attempts - 1))
        else:
            row.ocr_state, row.ocr_processed, row.ocr_text = 'done', True, text
            row.ocr_next_attempt_at = None
    db.session.execute(update(OcrSlot).where(OcrSlot.id == work.slot, OcrSlot.owner == work.token)
        .values(owner=None, attachment_id=None, lease_until=None, last_seen_at=now, consumer_seen_at=now))
    lock.check()
    db.session.commit()


def run_one(app, slot, processor=None):
    if app.config.get('PROCESS_ROLE') != 'worker':
        raise RuntimeError('OCR execution requires the worker role')
    if slot not in (1, 2):
        raise ValueError('OCR has exactly two deployment-wide slots')
    if not app.config.get('OCR_WORKER_ENABLED', True) or slot > app.config.get('OCR_MAX_CONCURRENCY', 2):
        return False
    with guarded_app_context(app):
        lock = ExecutionLock(db.engine, f'ocr-slot-{slot}')
        if not lock.acquire():
            return False
        try:
            work = claim(slot)
            if work is None:
                return False
            try:
                text, error = (processor or compute)(work, lock)
            except Exception:
                text, error = None, 'processing_failed'
            finish(work, text, error, lock)
            return True
        except LostJobOwnership:
            db.session.rollback()
            return False  # Lease protects capacity until the bounded child has exited.
        finally:
            lock.close()


def queue_status():
    counts = dict(db.session.query(Attachment.ocr_state, func.count(Attachment.id))
                  .filter(Attachment.ocr_state.isnot(None)).group_by(Attachment.ocr_state).all())
    slots = [{'slot': row.id, 'last_seen_at': row.last_seen_at.isoformat() if row.last_seen_at else None,
              'lease_until': row.lease_until.isoformat() if row.lease_until else None}
             for row in OcrSlot.query.filter(OcrSlot.id.in_((1, 2))).order_by(OcrSlot.id).all()]
    return {'states': counts, 'max_active': current_app.config.get('OCR_MAX_CONCURRENCY', 2),
            'max_pending': current_app.config.get('OCR_MAX_PENDING', 100), 'slots': slots,
            'enabled': current_app.config.get('OCR_WORKER_ENABLED', True)}

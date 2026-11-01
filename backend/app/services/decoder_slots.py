"""Share the OCR capacity with synchronous, security-required upload decoding."""
from contextlib import contextmanager
from datetime import timedelta
from uuid import uuid4
from flask import has_app_context, current_app
from sqlalchemy import select, update
from app import db
from app.models.attachment import OcrSlot
from app.services.scheduler_ownership import ExecutionLock, LostJobOwnership, database_now, insert_for


class DecoderBusy(RuntimeError):
    pass


@contextmanager
def decoder_slot():
    # OCR subprocesses already hold a slot in their supervising worker. Standalone
    # parser tests/tools have no application/database and retain their local limits.
    if not has_app_context():
        yield
        return
    engine = db.engine
    for slot in range(1, current_app.config.get('OCR_MAX_CONCURRENCY', 2) + 1):
        lock = ExecutionLock(engine, f'ocr-slot-{slot}')
        if not lock.acquire():
            continue
        token = str(uuid4())
        try:
            if engine.dialect.name == 'postgresql':
                # Independent of the HTTP mutation transaction. SQLite needs only
                # its OS file lock (no independently losable database session).
                with engine.begin() as connection:
                    connection.execute(insert_for(connection, OcrSlot.__table__).values(id=slot, revision=0)
                        .on_conflict_do_nothing(index_elements=['id']))
                    now = database_now(connection)
                    row = connection.execute(select(OcrSlot.__table__).where(OcrSlot.id == slot)).mappings().one()
                    if row['lease_until'] and row['lease_until'] > now:
                        continue
                    connection.execute(update(OcrSlot).where(OcrSlot.id == slot).values(owner=token,
                        attachment_id=None, lease_until=now + timedelta(seconds=45), last_seen_at=now))
            try:
                lock.check()
                yield
            finally:
                if engine.dialect.name == 'postgresql' and not lock.lost.is_set():
                    lock.check()
                    with engine.begin() as connection:
                        connection.execute(update(OcrSlot).where(OcrSlot.id == slot, OcrSlot.owner == token)
                            .values(owner=None, lease_until=None))
            return
        except LostJobOwnership:
            raise DecoderBusy('Image processing is temporarily unavailable. Please retry shortly.') from None
        finally:
            lock.close()
    raise DecoderBusy('Image processing is busy. Please retry shortly.')

"""Maintenance formerly launched by every application factory.

OCR recovery only admits bounded durable work.
"""
from app.services.restore_transaction import guarded_app_context


def backfill_ocr(app):
    """Admit a bounded page of legacy image/PDF work; workers own execution."""
    from app.services.ocr_queue import backfill
    with guarded_app_context(app):
        backfill()

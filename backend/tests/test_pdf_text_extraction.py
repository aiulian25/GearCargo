"""Tests for F32 — PDF attachments get their text layer extracted into ocr_text.

PDF fixtures are built in-test with reportlab (already a dependency), which
writes a real %PDF header so uploads pass the magic-byte validation.
"""

import io

import pytest

from app import db
from app.models import Attachment

pytest.importorskip('pypdf')
from reportlab.pdfgen import canvas  # noqa: E402

from app.routes.attachments import _extract_pdf_text  # noqa: E402


@pytest.fixture
def queued_tasks(monkeypatch):
    """Capture enqueued background tasks so tests can run them deterministically
    AFTER the request completes (mirrors the async thread backend)."""
    import app.services.task_queue as tq
    tasks = []
    monkeypatch.setattr(tq, 'enqueue_task',
                        lambda fn, *a, **k: tasks.append((fn, a)))
    return tasks


def _pdf_bytes(lines=('GARAGE INVOICE', 'TOTAL 42.50')):
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    y = 750
    for line in lines:
        c.drawString(100, y, line)
        y -= 20
    c.save()
    return buf.getvalue()


def _blank_pdf_bytes():
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.save()  # one empty page — no text layer, like a scanned image-only PDF
    return buf.getvalue()


def _upload(client, auth_headers, user_id, data_bytes, filename):
    return client.post(
        '/api/attachments',
        data={'file': (io.BytesIO(data_bytes), filename), 'category': 'receipt'},
        headers=auth_headers(user_id),
        content_type='multipart/form-data',
    )


def _run_queued(app, tasks):
    with app.app_context():
        for fn, args in tasks:
            fn(*args)
    tasks.clear()


def test_extract_pdf_text_reads_text_layer(tmp_path):
    path = tmp_path / 'invoice.pdf'
    path.write_bytes(_pdf_bytes())
    text = _extract_pdf_text(str(path))
    assert text is not None
    assert 'TOTAL 42.50' in text


def test_extract_pdf_text_handles_no_text_layer_and_garbage(tmp_path):
    blank = tmp_path / 'blank.pdf'
    blank.write_bytes(_blank_pdf_bytes())
    assert _extract_pdf_text(str(blank)) is None

    garbage = tmp_path / 'garbage.pdf'
    garbage.write_bytes(b'%PDF-1.4 not really a pdf')
    assert _extract_pdf_text(str(garbage)) is None  # never raises


def test_pdf_upload_extracts_text_and_serves_ocr(app, client, user, auth_headers, queued_tasks):
    resp = _upload(client, auth_headers, user.id, _pdf_bytes(), 'invoice.pdf')
    assert resp.status_code == 201, resp.get_data(as_text=True)
    assert resp.get_json()['ocr_status'] == 'pending'   # PDFs queue like images
    att_id = resp.get_json()['attachment']['id']
    assert len(queued_tasks) == 1

    _run_queued(app, queued_tasks)

    ocr = client.get(f'/api/attachments/{att_id}/ocr', headers=auth_headers(user.id))
    assert ocr.status_code == 200                       # gate no longer image-only
    body = ocr.get_json()
    assert body['ocr_processed'] is True
    assert body['has_text'] is True
    assert 'TOTAL 42.50' in body['ocr_text']

    with app.app_context():
        assert 'TOTAL 42.50' in db.session.get(Attachment, att_id).ocr_text

    # Global search finds the PDF's contents with a snippet.
    results = client.get('/api/search?q=TOTAL', headers=auth_headers(user.id)).get_json()
    flat = str(results)
    assert 'ocr_snippet' in flat and 'TOTAL 42.50' in flat


def test_scanned_pdf_degrades_to_no_text(app, client, user, auth_headers, queued_tasks):
    resp = _upload(client, auth_headers, user.id, _blank_pdf_bytes(), 'scan.pdf')
    att_id = resp.get_json()['attachment']['id']
    _run_queued(app, queued_tasks)

    body = client.get(f'/api/attachments/{att_id}/ocr',
                      headers=auth_headers(user.id)).get_json()
    assert body['ocr_processed'] is True
    assert body['has_text'] is False


def test_parse_endpoint_accepts_pdf(app, client, user, auth_headers, queued_tasks, monkeypatch):
    resp = _upload(client, auth_headers, user.id, _pdf_bytes(), 'invoice.pdf')
    att_id = resp.get_json()['attachment']['id']
    _run_queued(app, queued_tasks)

    import app.routes.attachments as att_mod
    app.config['OLLAMA_ENABLED'] = True
    app.config['OLLAMA_BASE_URL'] = 'http://localhost:11434'
    try:
        monkeypatch.setattr(att_mod, '_resolve_model', lambda *a, **k: 'test-model')
        monkeypatch.setattr(att_mod, '_ai_cache_get', lambda *a, **k: None)
        monkeypatch.setattr(att_mod, '_ai_cache_set', lambda *a, **k: None)
        monkeypatch.setattr(att_mod, '_ollama_chat', lambda **k: {
            'date': '2026-07-01', 'amount': 42.50, 'vendor': 'Garage Ltd',
            'category': 'service', 'line_items': [],
        })

        parsed = client.post(f'/api/attachments/{att_id}/ocr/parse',
                             headers=auth_headers(user.id))
        assert parsed.status_code == 200, parsed.get_data(as_text=True)
        body = parsed.get_json()
        assert body['amount'] == 42.50
        assert body['vendor'] == 'Garage Ltd'
    finally:
        app.config['OLLAMA_ENABLED'] = False


def test_retry_routes_pdf_to_pdf_task(app, client, user, auth_headers, queued_tasks):
    resp = _upload(client, auth_headers, user.id, _pdf_bytes(), 'invoice.pdf')
    att_id = resp.get_json()['attachment']['id']
    _run_queued(app, queued_tasks)

    retry = client.post(f'/api/attachments/{att_id}/ocr/retry',
                        headers=auth_headers(user.id))
    assert retry.status_code == 202
    assert len(queued_tasks) == 1
    fn, _args = queued_tasks[0]
    assert fn.__name__ == 'run_pdf_text_task'          # not the image OCR task
    _run_queued(app, queued_tasks)

    body = client.get(f'/api/attachments/{att_id}/ocr',
                      headers=auth_headers(user.id)).get_json()
    assert body['has_text'] is True

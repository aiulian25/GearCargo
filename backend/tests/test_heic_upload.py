"""Tests for F9 — HEIC/HEIF/webp receipt uploads (HEIC transcoded to JPEG)."""

import io

import pytest

from app import db
from app.models import Attachment

heif = pytest.importorskip("pillow_heif")
from PIL import Image  # noqa: E402


@pytest.fixture(autouse=True)
def _no_ocr(monkeypatch):
    """OCR runs fire-and-forget in a background thread; stub the enqueue so tests
    stay deterministic and don't touch the DB after teardown."""
    import app.services.task_queue as tq
    monkeypatch.setattr(tq, 'enqueue_task', lambda *a, **k: None)


def _heic_bytes(color=(200, 50, 50), size=(32, 24)):
    heif.register_heif_opener()
    im = Image.new('RGB', size, color)
    buf = io.BytesIO()
    im.save(buf, format='HEIF')
    return buf.getvalue()


def _webp_bytes(color=(30, 160, 90), size=(32, 24)):
    im = Image.new('RGB', size, color)
    buf = io.BytesIO()
    im.save(buf, format='WEBP')
    return buf.getvalue()


def _jpeg_bytes(color=(20, 40, 200), size=(32, 24)):
    im = Image.new('RGB', size, color)
    buf = io.BytesIO()
    im.save(buf, format='JPEG')
    return buf.getvalue()


def _upload(client, auth_headers, user_id, data_bytes, filename):
    return client.post(
        '/api/attachments',
        data={'file': (io.BytesIO(data_bytes), filename), 'category': 'receipt'},
        headers=auth_headers(user_id),
        content_type='multipart/form-data',
    )


def test_heic_uploads_and_transcodes_to_jpeg(app, client, user, auth_headers):
    resp = _upload(client, auth_headers, user.id, _heic_bytes(), 'receipt.heic')
    assert resp.status_code == 201, resp.get_data(as_text=True)
    att = resp.get_json()['attachment']

    # Stored as JPEG; original HEIC name kept for display.
    assert att['file_type'] == 'image/jpeg'
    assert att['filename'].endswith('.jpg')
    assert att['original_filename'] == 'receipt.heic'
    assert att['is_image'] is True

    # The stored file is a real, decodable JPEG that OCR could read.
    with app.app_context():
        row = db.session.get(Attachment, att['id'])
        with Image.open(row.filepath) as im:
            assert im.format == 'JPEG'
            assert im.size == (32, 24)


def test_heic_is_viewable_inline(app, client, auth_headers, user):
    resp = _upload(client, auth_headers, user.id, _heic_bytes(), 'photo.heic')
    aid = resp.get_json()['attachment']['id']
    view = client.get(f'/api/attachments/{aid}/view', headers=auth_headers(user.id))
    assert view.status_code == 200
    assert view.mimetype == 'image/jpeg'


def test_webp_accepted_and_stored_as_webp(app, client, user, auth_headers):
    resp = _upload(client, auth_headers, user.id, _webp_bytes(), 'scan.webp')
    assert resp.status_code == 201, resp.get_data(as_text=True)
    att = resp.get_json()['attachment']
    assert att['file_type'] == 'image/webp'
    assert att['filename'].endswith('.webp')
    assert att['is_image'] is True


def test_existing_jpeg_still_works(app, client, user, auth_headers):
    resp = _upload(client, auth_headers, user.id, _jpeg_bytes(), 'legacy.jpg')
    assert resp.status_code == 201
    assert resp.get_json()['attachment']['file_type'] == 'image/jpeg'


def test_spoofed_heic_extension_rejected(app, client, user, auth_headers):
    # JPEG bytes wearing a .heic extension must fail the magic-byte check.
    resp = _upload(client, auth_headers, user.id, _jpeg_bytes(), 'fake.heic')
    assert resp.status_code == 400


def test_webp_magic_required(app, client, user, auth_headers):
    # Random bytes as .webp must be rejected (not a real RIFF/WEBP container).
    resp = _upload(client, auth_headers, user.id, b'not-a-real-webp-file', 'x.webp')
    assert resp.status_code == 400


def _odf_bytes(mimetype):
    """Minimal valid OpenDocument container: a ZIP whose first entry is an
    uncompressed 'mimetype' member (matches how LibreOffice writes ODF)."""
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        zf.writestr('mimetype', mimetype, compress_type=zipfile.ZIP_STORED)
        zf.writestr('content.xml', '<?xml version="1.0"?><doc/>')
    return buf.getvalue()


@pytest.mark.parametrize('ext,mimetype', [
    ('odt', 'application/vnd.oasis.opendocument.text'),
    ('ods', 'application/vnd.oasis.opendocument.spreadsheet'),
    ('odp', 'application/vnd.oasis.opendocument.presentation'),
])
def test_opendocument_accepted(app, client, user, auth_headers, ext, mimetype):
    resp = _upload(client, auth_headers, user.id, _odf_bytes(mimetype), f'doc.{ext}')
    assert resp.status_code == 201, resp.get_data(as_text=True)
    att = resp.get_json()['attachment']
    assert att['filename'].endswith(f'.{ext}')
    assert att['original_filename'] == f'doc.{ext}'
    # Not an image → no OCR, forced-download MIME.
    assert att['is_image'] is False


def test_odt_served_as_download_not_inline(app, client, user, auth_headers):
    aid = _upload(client, auth_headers, user.id,
                  _odf_bytes('application/vnd.oasis.opendocument.text'),
                  'notes.odt').get_json()['attachment']['id']
    view = client.get(f'/api/attachments/{aid}/view', headers=auth_headers(user.id))
    assert view.status_code == 200
    # ODF is not inline-safe → octet-stream + attachment disposition.
    assert view.mimetype == 'application/octet-stream'
    assert 'attachment' in view.headers.get('Content-Disposition', '')


def test_odf_extension_needs_zip_magic(app, client, user, auth_headers):
    # A bare XML flat-ODF (no ZIP magic) as .odt is rejected by the magic check.
    resp = _upload(client, auth_headers, user.id,
                   b'<?xml version="1.0"?><office/>', 'flat.odt')
    assert resp.status_code == 400

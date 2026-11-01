"""Normal image compatibility and safe limit checks; no advisory exploit samples."""
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import struct
import time
import zlib

import pytest
from PIL import Image, ImageDraw, ImageFont, PngImagePlugin

from app import db
from app.models import Attachment
from app.services import image_decoder as decoder


@pytest.fixture(autouse=True)
def no_background_ocr(monkeypatch):
    monkeypatch.setattr('app.services.task_queue.enqueue_task', lambda *a, **k: None)


def image_bytes(format='PNG', *, orientation=None, size=(40, 24)):
    if format == 'HEIF':
        from pillow_heif import register_heif_opener
        register_heif_opener()
    image = Image.new('RGB', size, (25, 100, 150))
    options = {}
    if orientation:
        exif = Image.Exif(); exif[274] = orientation
        # HEIF's encoder needs encoded EXIF bytes to create its rotation box.
        options['exif'] = exif.tobytes()
    result = BytesIO(); image.save(result, format=format, **options)
    return result.getvalue()


def upload(client, user, auth_headers, data, extension='png'):
    return client.post('/api/attachments', headers=auth_headers(user.id),
                       data={'file': (BytesIO(data), 'receipt.' + extension), 'category': 'receipt'},
                       content_type='multipart/form-data')


@pytest.mark.parametrize('format,extension', [('PNG','png'), ('GIF','gif'), ('JPEG','jpg'), ('WEBP','webp'), ('HEIF','heic')])
def test_normal_image_uploads_still_work(app, client, user, auth_headers, format, extension):
    response = upload(client, user, auth_headers, image_bytes(format), extension)
    assert response.status_code == 201, response.json
    row = db.session.get(Attachment, response.json['attachment']['id'])
    assert Path(row.filepath).exists()
    with Image.open(row.filepath) as image:
        assert image.size == (40, 24)
        assert image.format == ('JPEG' if format == 'HEIF' else format)


@pytest.mark.parametrize('format,extension', [('PNG','png'), ('JPEG','jpg'), ('HEIF','heic')])
def test_rotated_metadata_upload_and_decode(app, client, user, auth_headers, format, extension, tmp_path):
    response = upload(client, user, auth_headers, image_bytes(format, orientation=6), extension)
    assert response.status_code == 201, response.json
    row = db.session.get(Attachment, response.json['attachment']['id'])
    # HEIF is oriented at transcode time; other formats retain original bytes
    # and are oriented inside the isolated decoder before OCR.
    assert decoder.validate_image(row.filepath)['size'] == [24, 40]
    with decoder.image_for_ocr(row.filepath) as image:
        assert image.mode == 'RGB' and image.width < image.height
        assert image.width * image.height <= decoder.MAX_OCR_PIXELS


def huge_dimension_header():
    """A tiny header only: the guard rejects dimensions before any pixel load."""
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind+data))
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 6000, 4000, 8, 2, 0, 0, 0)) + chunk(b'IEND', b'')


@pytest.mark.parametrize('kind', ['dimensions', 'metadata', 'frames', 'corrupt'])
def test_rejected_image_never_creates_record_or_leaves_temp_file(app, client, user, auth_headers, kind):
    extension = 'png'
    if kind == 'dimensions':
        data = huge_dimension_header()
    elif kind == 'metadata':
        info = PngImagePlugin.PngInfo(); info.add_text('Comment', 'x' * (300 * 1024))
        buffer = BytesIO(); Image.new('RGB', (8, 8)).save(buffer, format='PNG', pnginfo=info)
        data = buffer.getvalue()
    elif kind == 'frames':
        frames = [Image.new('RGB', (2, 2), (index, 0, 0)) for index in range(101)]
        buffer = BytesIO(); frames[0].save(buffer, format='GIF', save_all=True,
            append_images=frames[1:], duration=10, optimize=False)
        data, extension = buffer.getvalue(), 'gif'
    else:
        data = b'\x89PNG\r\n\x1a\nnot an image'
    response = upload(client, user, auth_headers, data, extension)
    assert response.status_code == 400, response.json
    assert Attachment.query.filter_by(user_id=user.id).count() == 0
    assert not list(Path(app.config['UPLOAD_FOLDER']).rglob('*.tmp'))
    assert not [p for p in Path(app.config['UPLOAD_FOLDER']).rglob('*') if p.is_file()]


def test_normal_animated_gif_keeps_original_frames(app, client, user, auth_headers):
    buffer = BytesIO()
    Image.new('RGB', (8, 8), 'red').save(buffer, format='GIF', save_all=True,
        append_images=[Image.new('RGB', (8, 8), 'blue')], duration=50)
    response = upload(client, user, auth_headers, buffer.getvalue(), 'gif')
    assert response.status_code == 201, response.json
    row = db.session.get(Attachment, response.json['attachment']['id'])
    with Image.open(row.filepath) as image:
        assert image.n_frames == 2


def test_narrow_image_cannot_expand_into_unbounded_ocr_buffer(tmp_path):
    path = tmp_path / 'narrow.png'; path.write_bytes(image_bytes(size=(1, 8000)))
    with decoder.image_for_ocr(path) as image:
        assert min(image.size) >= 1 and max(image.size) <= 4096
        assert image.width * image.height <= decoder.MAX_OCR_PIXELS


@pytest.mark.parametrize('format', ['JPEG', 'HEIF'])
def test_phone_resolution_image_fits_decoder_budget(tmp_path, format):
    path = tmp_path / 'phone'; path.write_bytes(image_bytes(format, size=(4032, 3024)))
    assert decoder.validate_image(path)['size'] == [4032, 3024]


@pytest.mark.parametrize('format', ['BMP', 'TIFF'])
def test_decoder_cannot_open_unapproved_plugins(tmp_path, format):
    path = tmp_path / 'unapproved'; path.write_bytes(image_bytes(format))
    with pytest.raises(decoder.ImageDecodeError):
        decoder.validate_image(path)


def test_timeout_kills_and_reaps_decoder(tmp_path, monkeypatch):
    worker = tmp_path / 'slow_worker.py'; pidfile = tmp_path / 'pid'
    worker.write_text('import os,time\nfrom pathlib import Path\n'
                      f'Path({str(pidfile)!r}).write_text(str(os.getpid()))\ntime.sleep(30)\n')
    monkeypatch.setattr(decoder, '_WORKER', worker)
    monkeypatch.setattr(decoder, 'DECODE_TIMEOUT_SECONDS', .3)
    started = time.monotonic()
    with pytest.raises(decoder.ImageDecodeError, match='resource or time limit'):
        decoder.validate_image(tmp_path / 'not-used')
    assert time.monotonic() - started < 3
    with pytest.raises(ProcessLookupError):
        os.kill(int(pidfile.read_text()), 0)


def test_resource_limits_are_active_before_image_open(tmp_path, monkeypatch):
    library = tmp_path / 'library'; (library/'PIL').mkdir(parents=True)
    limits = tmp_path / 'limits.json'
    (library/'PIL/__init__.py').write_text('''import json,resource
from types import SimpleNamespace
class BombWarning(Warning): pass
def image_open(*args, **kwargs):
    values = {name: resource.getrlimit(getattr(resource, name)) for name in
              ['RLIMIT_AS','RLIMIT_CPU','RLIMIT_FSIZE','RLIMIT_CORE']}
    from pathlib import Path
    Path(''' + repr(str(limits)) + ''').write_text(json.dumps(values))
    raise OSError('probe complete')
Image = SimpleNamespace(open=image_open, DecompressionBombWarning=BombWarning)
ImageOps = SimpleNamespace()
''')
    (library/'pillow_heif.py').write_text('def register_heif_opener(**kwargs): pass\n')
    monkeypatch.setenv('PYTHONPATH', str(library))
    source = tmp_path / 'source'; source.write_bytes(b'probe')
    with pytest.raises(decoder.ImageDecodeError):
        decoder.validate_image(source)
    values = json.loads(limits.read_text())
    assert 0 < values['RLIMIT_AS'][1] <= 512*1024*1024
    assert 0 < values['RLIMIT_CPU'][1] <= 8
    assert 0 < values['RLIMIT_FSIZE'][1] <= 64*1024*1024
    assert values['RLIMIT_CORE'] == [0, 0]


def test_legacy_oversized_image_is_not_sent_to_tesseract(app, user, tmp_path, monkeypatch):
    from app.services.ocr_queue import enqueue_attachment, run_one
    import pytesseract
    path = tmp_path / 'legacy.png'; path.write_bytes(huge_dimension_header())
    row = Attachment(user_id=user.id, filename=path.name, filepath=str(path), file_type='image/png')
    db.session.add(row); db.session.commit(); aid = row.id
    def must_not_run(*args, **kwargs):
        pytest.fail('Rejected image reached Tesseract')
    monkeypatch.setattr(pytesseract, 'image_to_osd', must_not_run)
    monkeypatch.setattr(pytesseract, 'image_to_data', must_not_run)
    enqueue_attachment(row); db.session.commit()
    app.config['PROCESS_ROLE'] = 'worker'
    assert run_one(app, 1)
    db.session.expire_all()
    assert db.session.get(Attachment, aid).ocr_state == 'retry'
    assert not db.session.get(Attachment, aid).ocr_processed
    assert db.session.get(Attachment, aid).ocr_text is None


@pytest.mark.skipif(shutil.which('tesseract') is None, reason='Native Tesseract integration requires runtime image')
def test_normal_receipt_runs_real_native_ocr(app, user, tmp_path):
    from app.services.ocr_queue import enqueue_attachment, run_one
    image = Image.new('RGB', (1400, 1000), 'white')
    draw = ImageDraw.Draw(image); font = ImageFont.load_default(size=38)
    for index, text in enumerate(['GARAGE INVOICE', 'SERVICE RECEIPT', 'TOTAL 42.50',
                                  'VEHICLE MAINTENANCE', 'PAYMENT COMPLETE']):
        draw.text((70, 80 + index * 120), text, font=font, fill='black')
    path = tmp_path / 'receipt.png'; image.save(path)
    row = Attachment(user_id=user.id, filename=path.name, filepath=str(path), file_type='image/png')
    db.session.add(row); db.session.commit(); aid = row.id
    enqueue_attachment(row); db.session.commit()
    app.config['PROCESS_ROLE'] = 'worker'
    assert run_one(app, 1)
    db.session.expire_all(); row = db.session.get(Attachment, aid)
    assert row.ocr_processed and 'TOTAL' in (row.ocr_text or '')

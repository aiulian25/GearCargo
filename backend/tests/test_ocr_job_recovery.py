"""GC-025: durable admission, bounded execution and independent OCR failures."""
from datetime import datetime
from pathlib import Path
import io
import json
import os
import subprocess
import sys
import time
import pytest
from sqlalchemy import update, text
from app import db
from app.models import Attachment, OcrSlot, ServiceEntry, Vehicle
from app.utils.timeutils import utc_naive_now
from app.services.ocr_queue import enqueue_attachment, run_one, backfill, ACTIVE, MAX_ATTEMPTS


def attachment(user, tmp_path, name='receipt.pdf'):
    path = tmp_path / name
    path.write_bytes(b'%PDF-1.4 invalid fixture')
    row = Attachment(user_id=user.id, filename=name, filepath=str(path), file_type='application/pdf')
    db.session.add(row); db.session.commit()
    return row


def test_admission_is_durable_idempotent_and_bounded(app, user, tmp_path, monkeypatch):
    import threading
    monkeypatch.setattr(threading.Thread, 'start', lambda *_: pytest.fail('OCR started a web thread'))
    app.config['OCR_MAX_PENDING'] = 1
    first = attachment(user, tmp_path)
    assert enqueue_attachment(first) == 'queued'
    db.session.commit(); generation = first.ocr_generation
    assert enqueue_attachment(first, force=True) == 'queued'
    db.session.commit(); assert first.ocr_generation == generation
    second = attachment(user, tmp_path, 'second.pdf')
    assert enqueue_attachment(second) == 'failed'
    db.session.commit()
    assert second.ocr_error == 'queue_full' and Path(second.filepath).is_file()
    assert Attachment.query.filter(Attachment.ocr_state.in_(ACTIVE)).count() == 1


def test_worker_disabled_keeps_receipt_and_reports_unavailable(app, user, tmp_path):
    row = attachment(user, tmp_path)
    app.config['OCR_WORKER_ENABLED'] = False
    assert enqueue_attachment(row) == 'unavailable'
    db.session.commit()
    assert row.ocr_error == 'worker_disabled' and Path(row.filepath).exists()


def test_poisoned_work_exhausts_retries_without_touching_expense(app, user, tmp_path):
    row = attachment(user, tmp_path)
    vehicle = Vehicle(user_id=user.id, name='Saved expense')
    db.session.add(vehicle); db.session.flush()
    expense = ServiceEntry(user_id=user.id, vehicle_id=vehicle.id, title='Keep', amount=25,
                           date=datetime.now().date(), service_type='oil_change')
    db.session.add(expense); db.session.commit(); expense_id = expense.id
    enqueue_attachment(row); db.session.commit(); row_id = row.id
    app.config['PROCESS_ROLE'] = 'worker'
    for _ in range(MAX_ATTEMPTS):
        assert run_one(app, 1)
        db.session.expire_all()
        db.session.get(Attachment, row_id).ocr_next_attempt_at = datetime(2000, 1, 1)
        db.session.commit()
    assert not run_one(app, 1)
    db.session.expire_all()
    row = db.session.get(Attachment, row_id)
    assert row.ocr_state == 'failed' and row.ocr_attempts == MAX_ATTEMPTS and not row.ocr_processed
    assert db.session.get(ServiceEntry, expense_id).amount == 25
    assert enqueue_attachment(row, force=True) == 'queued'
    db.session.commit()
    assert row.ocr_attempts == 0 and row.ocr_generation == 2


def test_backfill_bounds_legacy_images_and_pdfs_and_preserves_completed(app, user, tmp_path):
    app.config['OCR_MAX_PENDING'] = 2
    for i in range(5):
        attachment(user, tmp_path, f'{i}.pdf')
    done = attachment(user, tmp_path, 'done.pdf')
    done.ocr_processed, done.ocr_text = True, 'Preserved'
    db.session.commit(); done_id = done.id
    result = backfill()
    assert result['queued'] == 2
    assert Attachment.query.filter_by(ocr_state='queued').count() == 2
    assert backfill()['queued'] == 0
    assert db.session.get(Attachment, done_id).ocr_text == 'Preserved'


def test_worker_rejects_web_role_and_slots_beyond_two(app):
    with pytest.raises(RuntimeError):
        run_one(app, 1)
    app.config['PROCESS_ROLE'] = 'worker'
    with pytest.raises(ValueError):
        run_one(app, 3)


def test_stale_result_cannot_overwrite_replacement_generation(app, user, tmp_path):
    row = attachment(user, tmp_path)
    enqueue_attachment(row); db.session.commit(); row_id = row.id
    app.config['PROCESS_ROLE'] = 'worker'
    def stale(work, lock):
        with db.engine.begin() as connection:
            connection.execute(update(Attachment).where(Attachment.id == row_id).values(
                ocr_owner=None, ocr_state='done', ocr_generation=work.generation + 1,
                ocr_text='New result', ocr_processed=True))
        return 'Old result', None
    assert run_one(app, 1, stale)
    db.session.expire_all()
    assert db.session.get(Attachment, row_id).ocr_text == 'New result'
    assert db.session.get(OcrSlot, 1).owner is None


def test_committed_upload_temp_file_is_recovered(app, client, user, auth_headers, tmp_path):
    from reportlab.pdfgen import canvas
    stream = io.BytesIO(); page = canvas.Canvas(stream); page.drawString(20, 700, 'RECOVERED RECEIPT'); page.save()
    response = client.post('/api/attachments', data={'file': (io.BytesIO(stream.getvalue()), 'receipt.pdf')},
                           headers=auth_headers(user.id))
    assert response.status_code == 201
    row_id = response.json['attachment']['id']
    row = db.session.get(Attachment, row_id); path = Path(row.filepath)
    path.rename(str(path) + '.tmp')
    app.config['PROCESS_ROLE'] = 'worker'
    assert run_one(app, 1)
    db.session.expire_all(); row = db.session.get(Attachment, row_id)
    assert row.ocr_state == 'done' and 'RECOVERED RECEIPT' in row.ocr_text
    assert path.is_file() and not Path(str(path) + '.tmp').exists()


@pytest.fixture
def processes(app, user, tmp_path):
    settings = {key: app.config[key] for key in ('SQLALCHEMY_DATABASE_URI', 'VOLUMES_PATH', 'UPLOAD_FOLDER',
        'BACKUP_FOLDER', 'SECRET_KEY', 'JWT_SECRET_KEY', 'SESSION_TYPE', 'SESSION_FILE_DIR')}
    settings['OCR_MAX_PENDING'] = 8
    config = tmp_path/'config.json'; config.write_text(json.dumps(settings))
    script = Path(__file__).with_name('ocr_process_fixture.py')
    children = []
    logs = Path(os.environ.get('GC_SCHEDULER_LOG_DIR', str(tmp_path))) / tmp_path.name
    logs.mkdir(parents=True, exist_ok=True)
    def start(mode, label):
        log = logs/f'{label}.txt'
        with log.open('w') as stream:
            child = subprocess.Popen([sys.executable, str(script), str(config), str(tmp_path), mode, label],
                                     stdout=stream, stderr=subprocess.STDOUT)
        children.append(child)
        return child, log
    yield tmp_path, start
    for child in children:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=10)


def wait_path(path, child, log):
    deadline = time.monotonic() + 30
    while not path.exists():
        assert child.poll() is None, log.read_text()
        assert time.monotonic() < deadline, log.read_text()
        time.sleep(.02)


def test_many_submitters_and_consumers_never_exceed_two_native_jobs(app, user, processes):
    from PIL import Image, ImageDraw
    from reportlab.pdfgen import canvas
    folder, start = processes
    for index in range(24):
        is_pdf = index % 2 == 0
        name = f'{index}.pdf' if is_pdf else f'{index}.png'
        path = folder/name
        if is_pdf:
            page = canvas.Canvas(str(path)); page.drawString(20, 700, 'TOTAL 42.50'); page.save()
        else:
            image = Image.new('RGB', (300, 200), 'white')
            ImageDraw.Draw(image).text((20, 20), 'RECEIPT TOTAL', fill='black'); image.save(path)
        db.session.add(Attachment(user_id=user.id, filename=name, filepath=str(path),
                                  file_type='application/pdf' if is_pdf else 'image/png'))
    db.session.commit()
    submitters = [start('submit', f'submit-{i}') for i in range(4)]
    for i, (child, log) in enumerate(submitters):
        wait_path(folder/f'ready-submit-{i}', child, log)
    (folder/'start').touch()
    for child, log in submitters:
        assert child.wait(timeout=35) == 0, log.read_text()
    db.session.remove()
    assert Attachment.query.filter_by(ocr_state='queued').count() == 8
    assert Attachment.query.filter_by(ocr_error='queue_full').count() == 16
    db.session.remove()
    workers = [start('drain', f'worker-{i}') for i in range(6)]
    for child, log in workers:
        assert child.wait(timeout=60) == 0, log.read_text()
    db.session.remove()
    assert Attachment.query.filter_by(ocr_state='done').count() == 8
    events = [json.loads(line) for line in (folder/'events.jsonl').read_text().splitlines()]
    active = maximum = 0
    seen = []
    for event in events:
        active += 1 if event['event'] == 'start' else -1
        maximum = max(maximum, active)
        assert 0 <= active <= 2
        if event['event'] == 'start': seen.append(event['attachment'])
    assert active == 0 and maximum == 2 and len(seen) == len(set(seen)) == 8


def fake_pdf_module(folder, monkeypatch, *, wait=False):
    module = folder/'library'; module.mkdir()
    probe = folder/'probe.json'
    code = """import json,os,resource,time
from pathlib import Path
class Page:
    def extract_text(self):
        Path(PROBE).write_text(json.dumps({'pid': os.getpid(), 'memory': resource.getrlimit(resource.RLIMIT_AS),
            'cpu': resource.getrlimit(resource.RLIMIT_CPU)}))
        while WAIT and not Path(RELEASE).exists(): time.sleep(.05)
        return 'RECOVERED'
class PdfReader:
    def __init__(self, path): self.pages=[Page()]
"""
    (module/'pypdf.py').write_text('PROBE='+repr(str(probe))+'\nRELEASE='+repr(str(folder/'release'))+
                                  '\nWAIT='+repr(wait)+'\n'+code)
    monkeypatch.setenv('PYTHONPATH', str(module)+':'+os.environ.get('PYTHONPATH', ''))
    return probe


def test_worker_loss_kills_child_and_recovers_same_attachment(app, user, processes, monkeypatch):
    folder, start = processes
    row = attachment(user, folder); enqueue_attachment(row); db.session.commit(); identity = row.id
    probe = fake_pdf_module(folder, monkeypatch, wait=True)
    (folder/'start').touch()
    parent, log = start('child', 'lost')
    wait_path(probe, parent, log)
    limits = json.loads(probe.read_text()); pid = limits['pid']
    assert limits['memory'] == [768*1024**2]*2 and limits['cpu'] == [60, 60]
    parent.kill(); parent.wait(timeout=10)
    deadline = time.monotonic()+5
    while Path(f'/proc/{pid}/stat').exists():
        if Path(f'/proc/{pid}/stat').read_text().split()[2] == 'Z': break
        assert time.monotonic() < deadline, 'Orphaned OCR child survived its worker'
        time.sleep(.02)
    (folder/'release').touch()
    db.session.remove()
    with db.engine.begin() as connection:
        connection.execute(update(OcrSlot).where(OcrSlot.id == 1).values(lease_until=datetime(2000, 1, 1)))
    recovered, log = start('child', 'recovered')
    assert recovered.wait(timeout=30) == 0, log.read_text()
    db.session.remove(); row = db.session.get(Attachment, identity)
    assert row.ocr_state == 'done' and row.ocr_text == 'RECOVERED' and row.ocr_attempts == 2


def test_live_worker_is_not_displaced_by_expired_lease(app, user, processes):
    folder, start = processes
    row = attachment(user, folder); enqueue_attachment(row); db.session.commit()
    (folder/'start').touch()
    first, log = start('hold', 'first')
    wait_path(folder/'holding-first', first, log)
    db.session.remove()
    with db.engine.begin() as connection:
        connection.execute(update(OcrSlot).where(OcrSlot.id == 1).values(lease_until=datetime(2000, 1, 1)))
    second, other_log = start('child', 'second')
    assert second.wait(timeout=20) == 0, other_log.read_text()
    assert '"ran": false' in other_log.read_text()
    (folder/'release-first').touch()
    assert first.wait(timeout=20) == 0, log.read_text()


def test_upload_decoder_cannot_bypass_two_busy_ocr_slots(app, user, processes):
    from app.services.decoder_slots import decoder_slot, DecoderBusy
    folder, start = processes
    for name in ('first.pdf', 'second.pdf'):
        row = attachment(user, folder, name); enqueue_attachment(row); db.session.commit()
    (folder/'start').touch()
    first, first_log = start('hold', 'first')
    second, second_log = start('hold2', 'second')
    wait_path(folder/'holding-first', first, first_log)
    wait_path(folder/'holding-second', second, second_log)
    with pytest.raises(DecoderBusy):
        with decoder_slot():
            pytest.fail('Third decoder admitted')
    (folder/'release-first').touch(); (folder/'release-second').touch()
    assert first.wait(timeout=20) == 0, first_log.read_text()
    assert second.wait(timeout=20) == 0, second_log.read_text()


def test_lost_database_lock_does_not_release_capacity_before_child_deadline(app, user, processes):
    if db.engine.dialect.name != 'postgresql':
        pytest.skip('PostgreSQL session-lock loss')
    folder, start = processes
    row = attachment(user, folder); enqueue_attachment(row); db.session.commit(); identity = row.id
    (folder/'start').touch()
    first, log = start('hold', 'first')
    wait_path(folder/'holding-first', first, log)
    pid = int((folder/'holding-first').read_text())
    db.session.remove()
    with db.engine.begin() as connection:
        assert connection.execute(text('SELECT pg_terminate_backend(:pid)'), {'pid': pid}).scalar_one()
    second, second_log = start('child', 'second')
    assert second.wait(timeout=20) == 0, second_log.read_text()
    assert '"ran": false' in second_log.read_text()
    (folder/'release-first').touch()
    assert first.wait(timeout=20) == 0, log.read_text()
    assert '"ran": false' in log.read_text()
    db.session.remove()
    assert db.session.get(Attachment, identity).ocr_state == 'running'


def test_ocr_timeout_kills_child_and_reports_retry(app, user, tmp_path, monkeypatch):
    from app.services import ocr_queue
    row = attachment(user, tmp_path); enqueue_attachment(row); db.session.commit(); identity = row.id
    probe = fake_pdf_module(tmp_path, monkeypatch, wait=True)
    monkeypatch.setattr(ocr_queue, 'JOB_TIMEOUT', 3)
    app.config['PROCESS_ROLE'] = 'worker'
    assert run_one(app, 1)
    pid = json.loads(probe.read_text())['pid']
    assert not Path(f'/proc/{pid}').exists()
    db.session.expire_all(); row = db.session.get(Attachment, identity)
    assert row.ocr_state == 'retry' and row.ocr_error == 'processing_timeout'


def test_ocr_migration_preserves_finished_results_and_downgrades():
    import importlib.util
    from sqlalchemy import create_engine, inspect
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    path = Path(__file__).parents[1]/'migrations/versions/gc025_attachment_processing.py'
    spec = importlib.util.spec_from_file_location('ocr_migration', path)
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE attachments (id INTEGER PRIMARY KEY, ocr_processed BOOLEAN, ocr_text TEXT)'))
        connection.execute(text("INSERT INTO attachments VALUES (1, true, 'Preserve'), (2, false, NULL)"))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        assert connection.execute(text('SELECT ocr_state FROM attachments ORDER BY id')).scalars().all() == ['done', None]
        assert connection.execute(text('SELECT count(*) FROM ocr_slots')).scalar_one() == 3
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
        assert inspect(connection).get_table_names() == ['attachments']
        assert connection.execute(text('SELECT ocr_text FROM attachments WHERE id=1')).scalar_one() == 'Preserve'
    engine.dispose()


def test_admission_failure_does_not_roll_back_saved_expense(app, user, tmp_path, monkeypatch):
    from app.services import ocr_queue
    row = attachment(user, tmp_path)
    vehicle = Vehicle(user_id=user.id, name='Receipt owner')
    db.session.add(vehicle); db.session.flush()
    expense = ServiceEntry(user_id=user.id, vehicle_id=vehicle.id, title='Keep', amount=25,
                           date=datetime.now().date(), service_type='oil_change')
    db.session.add(expense)
    original = ocr_queue.admission
    def unavailable():
        original()
        raise RuntimeError('Queue admission fault')
    monkeypatch.setattr(ocr_queue, 'admission', unavailable)
    assert enqueue_attachment(row) == 'unavailable'
    db.session.commit(); identity = expense.id; row_id = row.id
    db.session.expire_all()
    assert db.session.get(ServiceEntry, identity).amount == 25
    assert db.session.get(Attachment, row_id).ocr_error == 'queue_unavailable'
    assert Path(row.filepath).is_file()


def test_upload_decoder_reports_lost_lock_without_releasing_lease(app, user):
    from app.services.decoder_slots import decoder_slot, DecoderBusy
    if db.engine.dialect.name != 'postgresql':
        pytest.skip('PostgreSQL session-lock loss')
    with pytest.raises(DecoderBusy):
        with decoder_slot():
            with db.engine.begin() as connection:
                pid = connection.execute(text("SELECT pid FROM pg_locks WHERE locktype='advisory' AND granted")).scalar_one()
                assert connection.execute(text('SELECT pg_terminate_backend(:pid)'), {'pid': pid}).scalar_one()
    db.session.expire_all()
    assert db.session.get(OcrSlot, 1).lease_until > utc_naive_now()


def test_lost_upload_capacity_cleans_transcoded_temp(app, client, user, auth_headers, monkeypatch):
    from app.services import image_decoder
    from app.services.decoder_slots import DecoderBusy
    def lost_lock(source, target):
        Path(target).write_bytes(b'partial jpeg')
        raise DecoderBusy('Temporarily unavailable')
    monkeypatch.setattr(image_decoder, 'transcode_jpeg', lost_lock)
    response = client.post('/api/attachments', data={'file': (io.BytesIO(b'\x00\x00\x00\x18ftypheic'), 'receipt.heic')},
                           headers=auth_headers(user.id))
    assert response.status_code == 503
    assert Attachment.query.count() == 0
    assert list(Path(app.config['UPLOAD_FOLDER']).rglob('*.tmp')) == []


def test_scan_overflow_and_disabled_api_keep_upload(app, client, user, auth_headers, tmp_path):
    app.config['OCR_MAX_PENDING'] = 1
    queued = attachment(user, tmp_path); enqueue_attachment(queued); db.session.commit()
    response = client.post('/api/attachments', data={'file': (io.BytesIO(b'%PDF-1.4'), 'receipt.pdf')},
                           headers=auth_headers(user.id))
    assert response.status_code == 201
    row_id = response.json['attachment']['id']
    assert response.json['attachment']['ocr_error'] == 'queue_full'
    retry = client.post(f'/api/attachments/{row_id}/ocr/retry', headers=auth_headers(user.id))
    assert retry.status_code == 429 and retry.json['ocr_error'] == 'queue_full'
    app.config['OCR_WORKER_ENABLED'] = False
    retry = client.post(f'/api/attachments/{row_id}/ocr/retry', headers=auth_headers(user.id))
    assert retry.status_code == 503 and retry.json['ocr_state'] == 'unavailable'
    assert Path(db.session.get(Attachment, row_id).filepath).is_file()
    assert client.get('/api/admin/ocr', headers=auth_headers(user.id)).status_code == 403
    user.is_admin = True; db.session.commit()
    status = client.get('/api/admin/ocr', headers=auth_headers(user.id))
    assert status.status_code == 200 and status.json['max_pending'] == 1
    assert status.json['states']['queued'] == 1 and status.json['states']['unavailable'] == 1
    assert 'filepath' not in status.json and 'owner' not in status.json


def test_decoder_has_independent_wall_deadline(tmp_path):
    import signal
    library = tmp_path/'library'; library.mkdir()
    (library/'PIL.py').write_text('import time; time.sleep(60)')
    worker = Path(__file__).parents[1]/'app/services/image_decoder_worker.py'
    started = time.monotonic()
    child = subprocess.Popen([sys.executable, str(worker), 'unused', '-', 'check'],
                             env={**os.environ, 'PYTHONPATH': str(library), 'GC_DECODER_PARENT_PID': str(os.getpid())},
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        assert child.wait(timeout=20) == -signal.SIGALRM
        assert time.monotonic() - started < 20
    finally:
        if child.poll() is None: child.kill(); child.wait(timeout=5)


def test_crashed_ocr_child_cannot_leave_native_descendants_running(app, user, tmp_path, monkeypatch):
    row = attachment(user, tmp_path); enqueue_attachment(row); db.session.commit()
    library = tmp_path/'library'; library.mkdir()
    probe = tmp_path/'native-pid'
    (library/'pypdf.py').write_text("import subprocess,sys\nfrom pathlib import Path\nclass PdfReader:\n"
        "    def __init__(self, path):\n"
        "        child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'])\n"
        f"        Path({str(probe)!r}).write_text(str(child.pid))\n"
        "        raise RuntimeError('Native pipeline failure')\n")
    monkeypatch.setenv('PYTHONPATH', str(library)+':'+os.environ.get('PYTHONPATH',''))
    app.config['PROCESS_ROLE'] = 'worker'
    assert run_one(app, 1)
    pid = int(probe.read_text()); deadline = time.monotonic()+5
    while Path(f'/proc/{pid}/stat').exists():
        if Path(f'/proc/{pid}/stat').read_text().split()[2] == 'Z': break
        assert time.monotonic()<deadline, 'Native child survived slot release'
        time.sleep(.02)


def test_legacy_rq_entrypoint_respects_restore_and_admits_only_once(app, user, tmp_path):
    from app.routes.attachments import run_ocr_task, run_pdf_text_task
    from app.services.restore_transaction import state_root, RestoreBusy
    row = attachment(user, tmp_path); identity, filepath = row.id, row.filepath
    root = state_root(); root.mkdir(parents=True, exist_ok=True)
    pending = root/'active.json'; pending.write_text('{}')
    try:
        with pytest.raises(RestoreBusy): run_pdf_text_task(identity, filepath)
    finally:
        pending.unlink()
    db.session.expire_all()
    assert db.session.get(Attachment, identity).ocr_state is None
    run_pdf_text_task(identity, filepath)
    run_ocr_task(identity, filepath)
    db.session.expire_all(); row = db.session.get(Attachment, identity)
    assert row.ocr_state == 'queued' and row.ocr_generation == 1

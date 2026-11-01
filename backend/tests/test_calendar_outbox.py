"""GC-023: durable calendar convergence independent of ordinary save requests."""
from datetime import date, datetime, timedelta
import pytest
from app import db
from app.models import Vehicle, User, ServiceEntry
from app.services.calendar_service import CalendarService, set_user_calendar_sources, encrypt_password


def configure(user, count=1):
    set_user_calendar_sources(user, [dict(id=f'source-{i}', name=f'Calendar {i}', provider='caldav',
        url=f'https://calendar-{i}.example.invalid/dav', username='fixture', password=encrypt_password('fixture-secret'),
        calendar_id='main', enabled=True) for i in range(count)])
    db.session.commit()


def test_entry_save_does_not_contact_calendar(app, client, user, auth_headers, monkeypatch):
    configure(user)
    vehicle = Vehicle(user_id=user.id, name='Calendar car')
    db.session.add(vehicle)
    db.session.commit()
    calls = []
    monkeypatch.setattr(CalendarService, 'create_event', lambda *args, **kwargs: (calls.append(kwargs) or True, 'fixture'))
    response = client.post('/api/services', headers=auth_headers(user.id), json={
        'vehicle_id': vehicle.id, 'date': '2028-01-01', 'service_type': 'oil_change', 'amount': 50, 'currency': 'GBP'})
    assert response.status_code == 201, response.json
    assert calls == [], 'An ordinary save still waits for remote calendar work'


@pytest.fixture
def dav(monkeypatch):
    """A loopback DAV event store using actual caldav REPORT/PUT/DELETE calls."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    from xml.sax.saxutils import escape
    import caldav
    from icalendar import Calendar
    state = {'events': {}, 'calls': [], 'offline': set(), 'put_then_fail': False}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def respond(self, code, body=b'', content='application/xml'):
            self.send_response(code); self.send_header('Content-Type', content); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
        def unavailable(self):
            if self.path.split('/')[1] in state['offline']:
                self.respond(503); return True
            return False
        def do_REPORT(self):
            from xml.etree import ElementTree
            request = ElementTree.fromstring(self.rfile.read(int(self.headers.get('Content-Length', 0))))
            match = request.find('.//{urn:ietf:params:xml:ns:caldav}text-match')
            uid = match.text if match is not None else None
            state['calls'].append(('REPORT', self.path))
            if self.unavailable(): return
            rows = []
            for path, data in state['events'].items():
                event = next(component for component in Calendar.from_ical(data).walk() if component.name == 'VEVENT')
                if path.startswith(self.path) and (not uid or str(event['uid']) == uid):
                    rows.append(f'<d:response><d:href>{escape(path)}</d:href><d:propstat><d:prop><c:calendar-data>{escape(data)}</c:calendar-data><d:getetag>"fixture"</d:getetag></d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>')
            self.respond(207, ('<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'+''.join(rows)+'</d:multistatus>').encode())
        def do_PUT(self):
            data = self.rfile.read(int(self.headers.get('Content-Length', 0))).decode()
            state['calls'].append(('PUT', self.path))
            if self.unavailable(): return
            Calendar.from_ical(data)
            state['events'][self.path] = data
            if state['put_then_fail']:
                state['put_then_fail'] = False; self.respond(503)
            else: self.respond(201)
        def do_DELETE(self):
            state['calls'].append(('DELETE', self.path))
            if self.unavailable(): return
            state['events'].pop(self.path, None); self.respond(204)
        def do_GET(self):
            self.respond(200, state['events'][self.path].encode(), 'text/calendar')
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    def connect(service):
        service.client = caldav.DAVClient(url=base, timeout=1)
        service.calendar = caldav.Calendar(client=service.client, url=f'{base}/{service.source["id"]}/')
        service._connected = True
        return True, 'fixture'
    monkeypatch.setattr(CalendarService, 'connect', connect)
    yield state
    server.shutdown(); server.server_close(); thread.join(timeout=5)


def service_entry(user, **changes):
    vehicle = Vehicle(user_id=user.id, name='Calendar car')
    db.session.add(vehicle); db.session.flush()
    row = ServiceEntry(user_id=user.id, vehicle_id=vehicle.id, date=date(2028, 1, 1),
        service_type='oil_change', amount=50, next_due_date=date(2028, 6, 1), **changes)
    db.session.add(row); db.session.commit()
    return row


def test_create_edit_date_move_delete_converges_one_uid(app, user, dav):
    from app.models import CalendarOutbox
    from app.services.calendar_outbox import process_calendar_outbox
    configure(user)
    entry = service_entry(user)
    assert CalendarOutbox.query.count() == 1 and dav['calls'] == []
    process_calendar_outbox(app)
    assert len(dav['events']) == 1
    db.session.refresh(user)
    assert user.calendar_last_sync is not None
    path = next(iter(dav['events']))
    assert '20280601' in dav['events'][path]
    entry.next_due_date = date(2028, 7, 1); db.session.commit()
    process_calendar_outbox(app)
    assert list(dav['events']) == [path] and '20280701' in dav['events'][path]
    assert not any(method == 'DELETE' for method, _ in dav['calls'])
    db.session.delete(entry); db.session.commit()
    assert CalendarOutbox.query.one().operation == 'delete'
    process_calendar_outbox(app)
    assert dav['events'] == {} and CalendarOutbox.query.one().status == 'synced'


def test_provider_failure_retry_and_sources_are_independent(app, user, dav, monkeypatch):
    from app.models import CalendarOutbox
    from app.services import calendar_outbox as queue
    configure(user, 2)
    service_entry(user)
    dav['offline'].add('source-0')
    # Jobs were created at the runtime date, so move the clock forward instead.
    now = queue.utc_naive_now() + timedelta(seconds=1)
    monkeypatch.setattr(queue, 'utc_naive_now', lambda: now)
    queue.process_calendar_outbox(app)
    states = {job.source_id: job.status for job in CalendarOutbox.query.all()}
    assert states == {'source-0': 'retry', 'source-1': 'synced'}
    calls = len(dav['calls']); queue.process_calendar_outbox(app)
    assert len(dav['calls']) == calls
    dav['offline'].clear(); now += timedelta(minutes=2)
    queue.process_calendar_outbox(app)
    assert len(dav['events']) == 2
    assert {job.status for job in CalendarOutbox.query.all()} == {'synced'}


def test_transport_acceptance_then_failure_reuses_uid(app, user, dav, monkeypatch):
    from app.services import calendar_outbox as queue
    configure(user); service_entry(user)
    now = queue.utc_naive_now() + timedelta(seconds=1)
    monkeypatch.setattr(queue, 'utc_naive_now', lambda: now)
    dav['put_then_fail'] = True
    queue.process_calendar_outbox(app)
    assert len(dav['events']) == 1
    now += timedelta(minutes=2)
    queue.process_calendar_outbox(app)
    assert len(dav['events']) == 1


def test_existing_uid_at_provider_href_is_reconciled_and_duplicates_removed(app, user, dav):
    from app.services.calendar_outbox import process_calendar_outbox
    from icalendar import Calendar, Event
    configure(user); entry = service_entry(user)
    def event_data(uid):
        calendar = Calendar(); event = Event()
        event.add('uid', uid); event.add('dtstart', date(2020, 1, 1)); event.add('summary', 'Old event')
        calendar.add_component(event)
        return calendar.to_ical().decode()
    uid = f'gearcargo-service-{entry.id}@gearcargo.local'
    first = '/source-0/provider-assigned-resource.ics'
    duplicate = '/source-0/old-duplicate.ics'
    unrelated = '/source-0/personal-event.ics'
    dav['events'].update({first: event_data(uid), duplicate: event_data(uid), unrelated: event_data('unrelated')})
    untouched = dav['events'][unrelated]
    process_calendar_outbox(app)
    assert set(dav['events']) == {first, unrelated}
    assert '20280601' in dav['events'][first] and dav['events'][unrelated] == untouched
    mutations = [(method, path) for method, path in dav['calls'] if method in ('PUT', 'DELETE')]
    assert mutations == [('PUT', first), ('DELETE', duplicate)]


def test_failed_remote_delete_keeps_tombstone_until_acknowledged(app, user, dav, monkeypatch):
    from app.models import CalendarOutbox
    from app.services import calendar_outbox as queue
    configure(user); entry = service_entry(user)
    queue.process_calendar_outbox(app)
    db.session.delete(entry); db.session.commit()
    dav['offline'].add('source-0')
    now = queue.utc_naive_now() + timedelta(seconds=1)
    monkeypatch.setattr(queue, 'utc_naive_now', lambda: now)
    queue.process_calendar_outbox(app)
    job = CalendarOutbox.query.one()
    assert job.operation == 'delete' and job.status == 'retry' and job.payload is None
    assert len(dav['events']) == 1 and ServiceEntry.query.count() == 0
    dav['offline'].clear(); now += timedelta(minutes=2)
    queue.process_calendar_outbox(app)
    # The consumer uses its own session, just like the production worker.
    db.session.refresh(job)
    assert dav['events'] == {} and job.status == 'synced'


def test_settings_disable_resume_and_destination_change(client, user, auth_headers, app, dav):
    from app.models import CalendarOutbox
    from app.services import calendar_outbox as queue
    from app.services.calendar_service import get_user_calendar_sources, decrypt_password
    configure(user); service_entry(user); headers = auth_headers(user.id)
    source = get_user_calendar_sources(user)[0]
    source['enabled'] = False
    assert client.put('/api/calendar/settings', headers=headers, json={'sources': [source]}).status_code == 200
    queue.process_calendar_outbox(app)
    assert dav['calls'] == [] and CalendarOutbox.query.one().status == 'paused'
    source['enabled'] = True
    assert client.put('/api/calendar/settings', headers=headers, json={'sources': [source]}).status_code == 200
    queue.process_calendar_outbox(app)
    assert CalendarOutbox.query.one().status == 'synced'
    source['url'] = 'https://replacement.example.invalid/dav'
    assert client.put('/api/calendar/settings', headers=headers, json={'sources': [source]}).status_code == 200
    assert sorted(job.status for job in CalendarOutbox.query.all()) == ['cancelled', 'pending']
    db.session.refresh(user)
    secret = get_user_calendar_sources(user, include_secrets=True)[0]['password']
    assert secret != 'fixture-secret' and decrypt_password(secret) == 'fixture-secret'


def test_rollback_and_idempotent_replay_do_not_create_extra_intents(app, client, user, auth_headers):
    from app.models import CalendarOutbox
    configure(user)
    entry = service_entry(user)
    prior = CalendarOutbox.query.one().payload_hash
    entry.next_due_date = date(2029, 1, 1); db.session.flush(); db.session.rollback()
    assert CalendarOutbox.query.one().payload_hash == prior
    headers = {**auth_headers(user.id), 'Idempotency-Key': 'gc023-operation-replay-0001', 'X-GearCargo-Mutation-Version': '1', 'If-Match': f'"{entry.revision}"'}
    payload = {'next_due_date': '2029-02-01'}
    first = client.put(f'/api/services/{entry.id}', headers=headers, json=payload)
    assert first.status_code == 200, first.json
    generation = CalendarOutbox.query.one().generation
    again = client.put(f'/api/services/{entry.id}', headers=headers, json=payload)
    assert again.status_code == 200 and again.headers['Idempotent-Replay'] == 'true'
    assert CalendarOutbox.query.one().generation == generation


def test_edit_and_delete_during_claim_are_not_lost(app, user):
    from app.models import CalendarOutbox
    from app.services import calendar_outbox as queue
    configure(user); entry = service_entry(user)
    job = CalendarOutbox.query.one()
    first = queue.claim(job.id, queue.utc_naive_now())
    assert first
    entry.next_due_date = date(2029, 1, 1); db.session.commit()
    assert queue.claim(job.id, queue.utc_naive_now()) is None
    queue.finish(first, True, queue.utc_naive_now())
    second = queue.claim(job.id, queue.utc_naive_now())
    assert second['payload']['start'].startswith('2029-01-01')
    db.session.delete(entry); db.session.commit()
    queue.finish(second, True, queue.utc_naive_now())
    third = queue.claim(job.id, queue.utc_naive_now())
    assert third['operation'] == 'delete'
    queue.finish(third, True, queue.utc_naive_now())
    assert CalendarOutbox.query.one().status == 'synced'


def test_expired_claim_recovers_and_old_worker_cannot_ack(app, user):
    from app.models import CalendarOutbox
    from app.services import calendar_outbox as queue
    configure(user); service_entry(user); job = CalendarOutbox.query.one()
    now = queue.utc_naive_now()
    first = queue.claim(job.id, now)
    second = queue.claim(job.id, now + queue.LEASE)
    assert first and second and first['token'] != second['token']
    queue.finish(first, True, now + queue.LEASE)
    assert CalendarOutbox.query.one().status == 'sending'
    queue.finish(second, True, now + queue.LEASE)
    assert CalendarOutbox.query.one().status == 'synced'


@pytest.mark.parametrize('delete', [False, True])
def test_late_expired_transport_reconciles_newer_edit_or_delete(app, user, dav, monkeypatch, delete):
    from app.models import CalendarOutbox
    from app.services import calendar_outbox as queue
    configure(user); entry = service_entry(user)
    now = queue.utc_naive_now() + timedelta(seconds=1)
    monkeypatch.setattr(queue, 'utc_naive_now', lambda: now)
    old = queue.claim(CalendarOutbox.query.one().id, now)
    if delete:
        db.session.delete(entry)
    else:
        entry.next_due_date = date(2029, 7, 1)
    db.session.commit()
    now += queue.LEASE + timedelta(seconds=1)
    queue.process_calendar_outbox(app)  # New worker acknowledges the newest state.
    # The suspended old worker resumes and writes its old snapshot afterward.
    old_payload = {**old['payload'], 'start': datetime.fromisoformat(old['payload']['start'])}
    assert CalendarService(user, old['source']).update_event(old['uid'], **old_payload)[0]
    assert '20280601' in next(iter(dav['events'].values()))
    queue.finish(old, False, now)  # Even a lost response must trigger reconciliation.
    assert CalendarOutbox.query.one().status == 'pending'
    queue.process_calendar_outbox(app)
    assert dav['events'] == {} if delete else '20290701' in next(iter(dav['events'].values()))
    assert CalendarOutbox.query.one().status == 'synced'


def test_removed_source_cancels_work_and_status_hides_urls_and_secrets(app, client, user, auth_headers):
    from app.models import CalendarOutbox
    configure(user); service_entry(user)
    assert client.get('/api/calendar/sync/job-status', headers=auth_headers(user.id)).json['sources'][0]['pending'] == 1
    response = client.post('/api/calendar/settings', headers=auth_headers(user.id), json={'sources': [], 'enabled': False})
    assert response.status_code == 200
    assert CalendarOutbox.query.one().status == 'cancelled'
    body = client.get('/api/calendar/sync/job-status', headers=auth_headers(user.id)).get_data(as_text=True)
    assert 'example.invalid' not in body and 'fixture-secret' not in body


@pytest.mark.parametrize('kind,path,payload,change,key', [
    ('fuel','fuel',{'date':'2028-01-01','liters':20,'price_per_liter':2,'total_price':40,'odometer':1000,'fuel_type':'petrol'}, {'date':'2028-02-01'}, 'entry'),
    ('service','services',{'date':'2028-01-01','service_type':'oil_change','amount':50}, {'next_due_date':'2028-02-01'}, 'entry'),
    ('repair','repairs',{'date':'2028-01-01','repair_type':'brakes','description':'Pads','amount':50}, {'date':'2028-02-01'}, 'entry'),
    ('tax','taxes',{'date':'2028-01-01','tax_type':'road_tax','amount':50,'due_date':'2028-01-31'}, {'due_date':'2028-02-01'}, 'entry'),
    ('parking','parking',{'date':'2028-01-01','parking_type':'hourly','amount':50}, {'date':'2028-02-01'}, 'entry'),
    ('insurance','insurance',{'provider':'Fixture','start_date':'2028-01-01','end_date':'2028-01-31','premium':50,'policy_type':'comprehensive'}, {'end_date':'2028-02-01'}, 'policy'),
    ('reminder','reminders',{'title':'Oil','due_date':'2028-01-01'}, {'due_date':'2028-02-01'}, 'reminder'),
])
def test_every_supported_http_lifecycle_is_durable(client, user, auth_headers, kind, path, payload, change, key):
    from app.models import CalendarOutbox
    configure(user)
    vehicle = Vehicle(user_id=user.id, name='Lifecycle car'); db.session.add(vehicle); db.session.commit()
    headers = auth_headers(user.id)
    response = client.post(f'/api/{path}', headers=headers, json={**payload, 'vehicle_id':vehicle.id})
    assert response.status_code == 201, response.json
    entry_id = response.json[key]['id']
    job = CalendarOutbox.query.filter_by(entry_type=kind, entry_id=entry_id).one()
    assert job.operation == 'upsert'
    assert client.put(f'/api/{path}/{entry_id}', headers=headers, json=change).status_code == 200
    db.session.refresh(job)
    assert job.payload['start'].startswith('2028-02-01')
    assert client.delete(f'/api/{path}/{entry_id}', headers=headers).status_code == 200
    db.session.refresh(job)
    assert job.operation == 'delete' and job.payload is None


def test_completed_recurring_reminder_deletes_old_event_and_queues_successor(client, user, auth_headers):
    from app.models import CalendarOutbox, Reminder
    configure(user)
    row = Reminder(user_id=user.id, title='Monthly', due_date=date(2028, 1, 31), recurring=True, frequency='monthly')
    db.session.add(row); db.session.commit()
    result = client.post(f'/api/reminders/{row.id}/complete', headers=auth_headers(user.id))
    assert result.status_code == 200
    successor = Reminder.query.filter_by(completed_from_id=row.id).one()
    assert CalendarOutbox.query.filter_by(entry_id=row.id, entry_type='reminder').one().operation == 'delete'
    job = CalendarOutbox.query.filter_by(entry_id=successor.id, entry_type='reminder').one()
    assert job.operation == 'upsert' and job.payload['start'].startswith('2028-02-29')


def test_archive_pauses_and_restore_resumes_without_altering_history(app, client, user, auth_headers, dav):
    from app.models import CalendarOutbox
    from app.services.calendar_outbox import process_calendar_outbox
    configure(user); entry = service_entry(user); headers = auth_headers(user.id)
    assert client.post(f'/api/vehicles/{entry.vehicle_id}/archive', headers=headers).status_code == 200
    process_calendar_outbox(app)
    assert dav['calls'] == [] and CalendarOutbox.query.one().status == 'paused'
    assert client.post(f'/api/vehicles/{entry.vehicle_id}/unarchive', headers=headers).status_code == 200
    process_calendar_outbox(app)
    assert len(dav['events']) == 1
    assert db.session.get(ServiceEntry, entry.id).next_due_date == date(2028, 6, 1)


def test_vehicle_delete_keeps_tombstones_and_account_delete_cancels_them(app, user, dav):
    from app.models import CalendarOutbox
    from app.services.calendar_outbox import process_calendar_outbox
    from app.services.deletion import delete_owned_data
    configure(user); entry = service_entry(user); vehicle_id = entry.vehicle_id; user_id = user.id
    process_calendar_outbox(app)
    delete_owned_data(user_id, vehicle_id=vehicle_id)
    assert CalendarOutbox.query.one().operation == 'delete'
    process_calendar_outbox(app)
    assert dav['events'] == {}
    delete_owned_data(user_id)
    assert CalendarOutbox.query.count() == 0


def test_bounded_retries_redaction_manual_retry_and_owner_isolation(app, client, user, auth_headers, monkeypatch, caplog):
    from app.models import CalendarOutbox
    from app.services import calendar_outbox as queue
    configure(user); service_entry(user)
    def failed(*args, **kwargs): raise RuntimeError('https://fixture:fixture-secret@calendar-0.example.invalid/dav')
    monkeypatch.setattr(CalendarService, 'update_event', failed)
    now = queue.utc_naive_now() + timedelta(seconds=1)
    monkeypatch.setattr(queue, 'utc_naive_now', lambda: now)
    for _ in range(queue.MAX_ATTEMPTS):
        queue.process_calendar_outbox(app); now += timedelta(hours=2)
    job = CalendarOutbox.query.one()
    assert job.status == 'failed' and job.attempts == queue.MAX_ATTEMPTS
    queue.process_calendar_outbox(app)
    assert CalendarOutbox.query.one().attempts == queue.MAX_ATTEMPTS
    other = User(username='calendar-other', email='calendar-other@example.invalid', is_active=True)
    other.set_password('FixturePassword123!'); db.session.add(other); db.session.commit()
    assert client.post('/api/calendar/sync/retry', headers=auth_headers(other.id), json={'source_id':'source-0'}).json['pending'] == 0
    state = client.get('/api/calendar/sync/job-status', headers=auth_headers(user.id)).get_data(as_text=True)
    assert 'fixture-secret' not in state + caplog.text and 'example.invalid' not in state + caplog.text
    assert client.post('/api/calendar/sync/retry', headers=auth_headers(user.id), json={'source_id':'source-0'}).json['pending'] == 1
    assert CalendarOutbox.query.one().status == 'pending'


def test_manual_sync_enqueues_and_survives_session_restart(client, user, auth_headers, monkeypatch):
    from app.models import CalendarOutbox
    configure(user); service_entry(user)
    monkeypatch.setattr(CalendarService, 'connect', lambda *args: pytest.fail('Manual sync called the provider'))
    result = client.post('/api/calendar/sync', headers=auth_headers(user.id))
    assert result.status_code == 202 and result.json['queued'] is True
    user_id = user.id; db.session.remove()
    assert CalendarOutbox.query.filter_by(user_id=user_id).one().status == 'pending'


def test_concurrent_workers_claim_one_generation(app, user, dav):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from app.services.calendar_outbox import process_calendar_outbox
    if db.engine.dialect.name != 'postgresql': pytest.skip('Production-engine worker concurrency')
    configure(user); service_entry(user)
    barrier = Barrier(2)
    def work(): barrier.wait(timeout=10); return process_calendar_outbox(app)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: work(), range(2)))
    assert sum(results) == 1
    assert sum(method == 'PUT' for method, _ in dav['calls']) == 1


def test_calendar_outbox_migration_upgrade_and_downgrade():
    import importlib.util
    from pathlib import Path
    from sqlalchemy import create_engine, text, inspect
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    path = Path(__file__).parents[1] / 'migrations/versions/gc023_calendar_outbox.py'
    spec = importlib.util.spec_from_file_location('calendar_migration', path)
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE users (id INTEGER PRIMARY KEY)'))
        with Operations.context(MigrationContext.configure(conn)): migration.upgrade()
        assert 'calendar_outbox' in inspect(conn).get_table_names()
        assert {index['name'] for index in inspect(conn).get_indexes('calendar_outbox')} == {'ix_calendar_outbox_user_id','ix_calendar_outbox_due'}
        with Operations.context(MigrationContext.configure(conn)): migration.downgrade()
        assert 'calendar_outbox' not in inspect(conn).get_table_names()
    engine.dispose()

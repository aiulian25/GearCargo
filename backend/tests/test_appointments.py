"""Workshop proposal 4: manual scheduling, safe links and repeat-safe completion."""
from datetime import date, datetime, timedelta
from io import BytesIO
import copy
import uuid
import pytest
from app import db
from app.models import Vehicle, User, Reminder, Todo, ServiceEntry, RepairEntry


@pytest.fixture
def car(user):
    row = Vehicle(user_id=user.id, name='Workshop car', distance_unit='km', current_mileage=20000)
    db.session.add(row); db.session.commit()
    return row


def headers(auth_headers, user, record=None, key=None):
    return {**auth_headers(user.id), 'Idempotency-Key': key or uuid.uuid4().hex,
        'X-GearCargo-Mutation-Version': '1', **({'If-Match': f'"{record["revision"]}"'} if record else {})}


def create(client, user, car, auth_headers, **extra):
    payload = dict(vehicle_id=car.id, title='Annual service', shop_name='Local garage',
        time_zone='Europe/London', start_local='2027-06-15T09:30', end_local='2027-06-15T17:00',
        notify_push=True, tasks=[{'title': 'Bring wheel key', 'done': False}])
    payload.update(extra)
    response = client.post('/api/appointments', json=payload, headers=headers(auth_headers, user))
    assert response.status_code == 201, response.json
    return response.json


def action(client, user, auth_headers, record, kind, data=None, key=None):
    return client.post(f'/api/appointments/{record["id"]}/{kind}', headers=headers(auth_headers, user, record, key), json=data or {})


def ready(client, user, car, auth_headers, **extra):
    record = create(client, user, car, auth_headers, **extra)
    record = action(client, user, auth_headers, record, 'confirm', {'arranged_externally': True}).json
    return action(client, user, auth_headers, record, 'dropoff').json


def test_create_request_and_correct_calendar_local_time(client, user, car, auth_headers):
    record = create(client, user, car, auth_headers)
    assert record['status'] == 'requested' and record['confirmed_at'] is None
    assert record['start_at'] == '2027-06-15T08:30:00Z' and record['start_local'] == '2027-06-15T09:30'
    response = client.get('/api/calendar/entries?start_date=2027-06-15&end_date=2027-06-15', headers=auth_headers(user.id))
    appointment = next(e for e in response.json['entries'] if e['type'] == 'appointment')
    assert appointment['date'] == '2027-06-15' and appointment['details']['time_zone'] == 'Europe/London'
    assert appointment['status'] == 'requested'
    assert not [e for e in response.json['entries'] if e['type'] == 'reminder']
    assert action(client, user, auth_headers, record, 'confirm').status_code == 400


@pytest.mark.parametrize('values,key', [
    ({'start_local': '2027-03-28T01:30', 'end_local': '2027-03-28T03:30'}, 'nonexistentTime'),
    ({'start_local': '2027-10-31T01:30', 'end_local': '2027-10-31T03:30'}, 'ambiguousTime'),
    ({'time_zone': 'bad/zone'}, 'invalid'),
    ({'end_local': '2027-06-15T08:00'}, 'invalid'),
    ({'prepare_minutes': -1}, 'validation.invalidNumber'),
    ({'status': 'confirmed'}, 'invalid'),
])
def test_invalid_schedule_is_atomic(client, user, car, auth_headers, values, key):
    payload = dict(vehicle_id=car.id, title='Check', time_zone='Europe/London', start_local='2027-06-15T09:30', end_local='2027-06-15T17:00', **{})
    payload.update(values)
    response = client.post('/api/appointments', json=payload, headers=headers(auth_headers, user))
    assert response.status_code == 400, response.json
    assert response.json['message_key'] == (key if key.startswith('validation.') else 'appointments.' + key)
    from app.models import Appointment
    assert Appointment.query.count() == Reminder.query.count() == 0


@pytest.mark.parametrize('fold,expected', [(0, '00:30'), (1, '01:30')])
def test_repeated_hour_requires_explicit_choice(client, user, car, auth_headers, fold, expected):
    record = create(client, user, car, auth_headers, start_local='2027-10-31T01:30', end_local='2027-10-31T03:30', start_fold=fold)
    assert record['start_at'] == f'2027-10-31T{expected}:00Z' and record['start_fold'] == fold


def test_reschedule_single_calendar_uid_and_cancel_reminders(app, client, user, car, auth_headers, monkeypatch):
    from tests.test_calendar_outbox import configure
    from app.models import CalendarOutbox
    from app.services.reminder_delivery import eligibility, occurrence_key
    from app.services.calendar_outbox import process_calendar_outbox
    from app.services.calendar_service import CalendarService
    configure(user)
    remote = {}
    monkeypatch.setattr(CalendarService, 'update_event', lambda self, uid, **data: (remote.update({uid: data}) is None, 'ok'))
    monkeypatch.setattr(CalendarService, 'delete_event', lambda self, uid: (remote.pop(uid, None) is not False, 'ok'))
    record = create(client, user, car, auth_headers)
    process_calendar_outbox(app)
    assert len(remote) == 1 and list(remote.values())[0]['reminder_minutes'] == 0
    reminder = db.session.get(Reminder, record['preparation_reminder_id']); old_occurrence = occurrence_key(reminder)
    assert not eligibility(reminder, user, datetime(2027, 6, 15), 'date')
    record = action(client, user, auth_headers, record, 'confirm', {'arranged_externally': True}).json
    reminder = db.session.get(Reminder, record['preparation_reminder_id'])
    assert eligibility(reminder, user, datetime(2027, 6, 15), 'date')
    assert not eligibility(reminder, user, datetime(2027, 6, 13), 'date')
    changed = client.put(f'/api/appointments/{record["id"]}', headers=headers(auth_headers, user, record), json={
        'time_zone': 'Europe/London', 'start_local': '2027-07-15T09:30', 'end_local': '2027-07-15T17:00'})
    assert changed.status_code == 200, changed.json
    record = changed.json
    assert record['status'] == 'requested' and record['confirmed_at'] is None
    reminder = db.session.get(Reminder, record['preparation_reminder_id'])
    assert occurrence_key(reminder) != old_occurrence
    process_calendar_outbox(app)
    assert len(remote) == 1 and list(remote.values())[0]['start'].month == 7
    assert CalendarOutbox.query.filter_by(entry_type='appointment').count() == 1
    record = action(client, user, auth_headers, record, 'confirm', {'arranged_externally': True}).json
    record = action(client, user, auth_headers, record, 'cancel').json
    assert not eligibility(db.session.get(Reminder, record['preparation_reminder_id']), user, datetime(2027, 7, 15), 'date')
    process_calendar_outbox(app); assert remote == {}


def test_completion_links_cost_once_and_resolves_only_selected_work(client, user, car, auth_headers):
    from app.models import AppointmentExpense
    service = ServiceEntry(user_id=user.id, vehicle_id=car.id, date=date(2026, 1, 1), amount=100, currency='GBP', service_type='inspection', title='Invoice')
    task = Todo(user_id=user.id, vehicle_id=car.id, title='Check brakes', due_date=date(2026, 1, 1), recurring=True, frequency='monthly', frequency_value=1)
    other = Todo(user_id=user.id, vehicle_id=car.id, title='Check coolant')
    db.session.add_all([service, task, other]); db.session.commit()
    record = ready(client, user, car, auth_headers, tasks=[{'title': task.title, 'todo_id': task.id}, {'title': other.title, 'todo_id': other.id}])
    key = uuid.uuid4().hex; data = {'entry_ids': [service.id], 'resolved_task_ids': [record['tasks'][0]['id']]}
    response = action(client, user, auth_headers, record, 'complete', data, key)
    assert response.status_code == 200, response.json
    replay = action(client, user, auth_headers, record, 'complete', data, key)
    assert replay.status_code == 200 and replay.headers['Idempotent-Replay'] == 'true'
    assert response.json['status'] == 'completed' and response.json['pickup_at']
    assert AppointmentExpense.query.count() == ServiceEntry.query.count() == 1
    assert db.session.get(Todo, task.id).completed and not db.session.get(Todo, other.id).completed
    assert Todo.query.filter_by(completed_from_id=task.id).one().due_date == date(2026, 2, 1)
    next_visit = ready(client, user, car, auth_headers)
    assert action(client, user, auth_headers, next_visit, 'complete', {'entry_ids': [service.id]}).status_code == 400


def test_stale_work_rejects_whole_completion_and_owner_boundaries(client, user, car, auth_headers):
    task = Todo(user_id=user.id, vehicle_id=car.id, title='Original work')
    db.session.add(task); db.session.commit()
    record = ready(client, user, car, auth_headers, tasks=[{'title': task.title, 'todo_id': task.id}])
    task.title = 'Changed work'; db.session.commit()
    result = action(client, user, auth_headers, record, 'complete', {'no_cost': True, 'resolved_task_ids': [record['tasks'][0]['id']]})
    assert result.status_code == 400 and result.json['message_key'] == 'appointments.changedTask'
    assert not db.session.get(Todo, task.id).completed
    other = User(username='workshop-other', email='other@workshop.invalid'); other.set_password('Test123456!')
    db.session.add(other); db.session.commit()
    assert client.get(f'/api/appointments/{record["id"]}', headers=auth_headers(other.id)).status_code == 404
    assert action(client, other, auth_headers, record, 'cancel').status_code in (404, 409)
    car.archived = True; db.session.commit()
    assert action(client, user, auth_headers, record, 'cancel').status_code == 400


def test_work_and_backup_roundtrip_remaps_every_link(app, client, user, car, auth_headers, tmp_path, monkeypatch):
    from app.models import Appointment, AppointmentTask, AppointmentExpense, Attachment
    from app.routes import backup
    from app.services.backup_schema import prepare_backup, BackupSchemaError
    monkeypatch.setattr(backup, 'get_uploads_folder', lambda: str(tmp_path/'photos'))
    task = Todo(user_id=user.id, vehicle_id=car.id, title='Due task', due_date=date(2020, 1, 1))
    entry = RepairEntry(user_id=user.id, vehicle_id=car.id, title='Repair', date=date(2026, 1, 1), amount=230, currency='EUR', repair_type='brakes')
    db.session.add_all([task, entry]); db.session.commit()
    work = client.get(f'/api/appointments/work?vehicle_id={car.id}', headers=auth_headers(user.id)).json['work']
    assert work == [{'title': 'Due task', 'todo_id': task.id}]
    record = ready(client, user, car, auth_headers, tasks=work)
    result = action(client, user, auth_headers, record, 'complete', {'entry_ids': [entry.id], 'resolved_task_ids': [record['tasks'][0]['id']]})
    assert result.status_code == 200, result.json
    receipt = tmp_path/'receipt.txt'; receipt.write_text('synthetic receipt')
    db.session.add(Attachment(user_id=user.id, vehicle_id=car.id, entry_id=entry.id, filename='receipt.txt', original_filename='receipt.txt', filepath=str(receipt), file_type='text/plain', file_size=17)); db.session.commit()
    archive, payload = backup.create_backup_zip(user)
    assert payload['version'] == '4.7' and len(payload['appointment_expenses']) == 1
    damaged = copy.deepcopy(payload); damaged['appointments'][0]['end_at'] = damaged['appointments'][0]['start_at']
    with pytest.raises(BackupSchemaError): prepare_backup(damaged)
    target = User(username='visit-restore', email='visit-restore@example.invalid'); target.set_password('Test123456!')
    db.session.add(target); db.session.commit()
    with app.test_request_context(): response = backup.restore_from_zip(target, BytesIO(archive.getvalue()))
    assert response.status_code == 200, response.json
    restored = Appointment.query.filter_by(user_id=target.id).one()
    assert restored.status == 'completed' and restored.time_zone == 'Europe/London'
    restored_task = AppointmentTask.query.filter_by(user_id=target.id).one()
    assert restored_task.appointment_id == restored.id and restored_task.todo_id == Todo.query.filter_by(user_id=target.id).one().id
    link = AppointmentExpense.query.filter_by(user_id=target.id).one()
    assert link.appointment_id == restored.id and link.entry_id == RepairEntry.query.filter_by(user_id=target.id).one().id
    assert Attachment.query.filter_by(user_id=target.id).one().entry_id == link.entry_id
    assert db.session.get(Reminder, restored.preparation_reminder_id).completed
    with app.test_request_context(): response = backup.restore_from_zip(target, BytesIO(archive.getvalue()))
    assert response.status_code == 200 and AppointmentExpense.query.filter_by(user_id=target.id).count() == 1
    for version in ('4.4', '4.5'):
        old = copy.deepcopy(payload); old['version'] = version
        for kind in ('appointments','appointment_tasks','appointment_expenses'): old.pop(kind)
        if version == '4.4':
            for kind in ('tire_sets','tires','tire_fitments','tread_readings'): old.pop(kind)
        assert prepare_backup(old).records['appointments'] == []


def test_preparation_delivery_once_per_reschedule_and_cancel(app, client, user, car, auth_headers, monkeypatch):
    from app.services import reminder_delivery as delivery
    user.notifications_enabled = True; db.session.commit()
    record = create(client, user, car, auth_headers, start_local='2026-01-01T09:00', end_local='2026-01-01T17:00')
    sends = []
    monkeypatch.setattr(delivery, 'send', lambda *args: sends.append(args[2]) or True)
    delivery.dispatch_reminders(app, 'date'); assert sends == []
    record = action(client, user, auth_headers, record, 'confirm', {'arranged_externally': True}).json
    delivery.dispatch_reminders(app, 'date'); delivery.dispatch_reminders(app, 'date')
    assert sends == ['push']
    # Re-read: dispatch updates the Reminder revision, not the Appointment revision.
    record = client.put(f'/api/appointments/{record["id"]}', headers=headers(auth_headers, user, record), json={
        'time_zone': 'Europe/London', 'start_local': '2026-01-02T10:00', 'end_local': '2026-01-02T17:00'}).json
    record = action(client, user, auth_headers, record, 'confirm', {'arranged_externally': True}).json
    delivery.dispatch_reminders(app, 'date'); assert sends == ['push', 'push']
    record = action(client, user, auth_headers, record, 'cancel').json
    delivery.dispatch_reminders(app, 'date'); assert sends == ['push', 'push']


def test_stale_revision_and_new_keys_cannot_repeat_completion(client, user, car, auth_headers):
    record = create(client, user, car, auth_headers)
    confirmed = action(client, user, auth_headers, record, 'confirm', {'arranged_externally': True}).json
    assert action(client, user, auth_headers, record, 'cancel').status_code == 409
    dropped = action(client, user, auth_headers, confirmed, 'dropoff').json
    result = action(client, user, auth_headers, dropped, 'complete', {'no_cost': True})
    assert result.status_code == 200
    assert action(client, user, auth_headers, result.json, 'complete', {'no_cost': True}).status_code == 400


def test_deletion_removes_all_workshop_rows(client, user, car, auth_headers):
    from app.models import Appointment, AppointmentTask, AppointmentExpense
    record = ready(client, user, car, auth_headers)
    assert action(client, user, auth_headers, record, 'complete', {'no_cost': True}).status_code == 200
    result = client.delete(f'/api/vehicles/{car.id}?hard=true', headers=auth_headers(user.id))
    assert result.status_code == 200, result.json
    assert all(model.query.filter_by(user_id=user.id).count() == 0 for model in (Appointment, AppointmentTask, AppointmentExpense, Reminder))


def test_recurring_reminder_and_service_resolution(client, user, car, auth_headers):
    reminder = Reminder(user_id=user.id, vehicle_id=car.id, title='Recurring oil', due_date=date(2026, 1, 1),
        due_mileage=10000, recurring=True, frequency='yearly', repeat_mileage=10000)
    service = ServiceEntry(user_id=user.id, vehicle_id=car.id, date=date(2025, 1, 1), amount=100, currency='EUR',
        service_type='oil_change', title='Old oil service', next_due_date=date(2026, 1, 1), next_due_mileage=10000)
    db.session.add_all([reminder, service]); db.session.commit()
    record = ready(client, user, car, auth_headers, tasks=[{'title': reminder.title, 'reminder_id': reminder.id}, {'title': service.title, 'service_id': service.id}])
    response = action(client, user, auth_headers, record, 'complete', {'no_cost': True, 'resolved_task_ids': [t['id'] for t in record['tasks']]})
    assert response.status_code == 200, response.json
    successor = Reminder.query.filter_by(completed_from_id=reminder.id).one()
    assert successor.due_date == date(2027, 1, 1) and successor.due_mileage == 30000
    assert db.session.get(ServiceEntry, service.id).next_due_date is None
    assert db.session.get(ServiceEntry, service.id).next_due_mileage is None


def test_calendar_day_is_named_zone_day_not_utc_day(client, user, car, auth_headers):
    record = create(client, user, car, auth_headers, time_zone='Asia/Tokyo', start_local='2027-06-15T00:30', end_local='2027-06-15T02:30')
    assert record['start_at'] == '2027-06-14T15:30:00Z'
    events = client.get('/api/calendar/entries?start_date=2027-06-15&end_date=2027-06-15', headers=auth_headers(user.id)).json['entries']
    assert next(e for e in events if e['type'] == 'appointment')['date'] == '2027-06-15'


def test_linked_work_cannot_be_checked_as_preparation_or_silently_rebased(client, user, car, auth_headers):
    task = Todo(user_id=user.id, vehicle_id=car.id, title='Original work')
    db.session.add(task); db.session.commit()
    record = ready(client, user, car, auth_headers, tasks=[{'title': task.title, 'todo_id': task.id}])
    row = record['tasks'][0]
    result = client.put(f'/api/appointments/{record["id"]}', headers=headers(auth_headers, user, record), json={'tasks': [{**row, 'done': True}]})
    assert result.status_code == 400 and not db.session.get(Todo, task.id).completed
    task.title = 'New work'; db.session.commit()
    response = client.put(f'/api/appointments/{record["id"]}', headers=headers(auth_headers, user, record), json={'notes': 'Minor change', 'tasks': [row]})
    assert response.status_code == 200
    result = action(client, user, auth_headers, response.json, 'complete', {'no_cost': True, 'resolved_task_ids': [row['id']]})
    assert result.status_code == 400 and result.json['message_key'] == 'appointments.changedTask'


@pytest.mark.parametrize('ident', [{}, [], True, 0, -1, '1'])
def test_malformed_task_identity_is_rejected_without_writes(client, user, car, auth_headers, ident):
    record = create(client, user, car, auth_headers)
    response = client.put(f'/api/appointments/{record["id"]}', headers=headers(auth_headers, user, record), json={'tasks': [{'id': ident, 'title': 'Bad identity'}]})
    assert response.status_code == 400
    saved = client.get(f'/api/appointments/{record["id"]}', headers=auth_headers(user.id)).json
    assert saved['tasks'] == record['tasks'] and saved['revision'] == record['revision']

"""GC-018: archive pauses activity while preserving every obligation field."""
import copy
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import inspect

from app import db
from app.models import (Vehicle, InsurancePolicy, TaxEntry, ParkingEntry, Reminder,
                        Todo, ServiceEntry, Attachment, ConsumableEntry, PredictionAlert)
from app.services import (check_due_reminders, process_auto_renew_insurance,
    process_recurring_tax_entries, process_recurring_parking_entries,
    check_consumables_due, check_warranty_expiry, check_document_expiry,
    process_due_services, dedupe_duplicate_reminders, send_daily_email_alerts)
from app.services.due import build_due_items
from app.services.email_service import get_all_alerts_for_user
from app.services.vehicle_archive import scan_archive_history, create_archive_review_app


MODELS = (InsurancePolicy, TaxEntry, ParkingEntry, Reminder, Todo, ServiceEntry,
          Attachment, ConsumableEntry, PredictionAlert)
JOBS = (check_due_reminders, process_auto_renew_insurance, process_recurring_tax_entries,
        process_recurring_parking_entries, check_consumables_due, check_warranty_expiry,
        check_document_expiry, process_due_services, dedupe_duplicate_reminders,
        send_daily_email_alerts)


def snapshot(vehicle_id):
    db.session.expire_all()
    return {model.__name__: {row.id: {attr.key: copy.deepcopy(getattr(row, attr.key))
        for attr in inspect(model).column_attrs}
        for row in model.query.filter_by(vehicle_id=vehicle_id).all()} for model in MODELS}


@pytest.fixture()
def obligations(app, user):
    today = date.today()
    vehicle = Vehicle(user_id=user.id, name='Archived fixture', current_mileage=2000)
    db.session.add(vehicle); db.session.flush()
    base = {'user_id': user.id, 'vehicle_id': vehicle.id}
    policy = InsurancePolicy(**base, provider='Renewal', premium=120, auto_renew=True,
        start_date=today-timedelta(days=366), end_date=today-timedelta(days=1), status='active')
    current = InsurancePolicy(**base, provider='Current', premium=150, auto_renew=True,
        start_date=today-timedelta(days=360), end_date=today+timedelta(days=5), status='active')
    tax = TaxEntry(**base, date=today-timedelta(days=30), amount=20, title='Road tax',
        tax_type='road_tax', recurring=True, recurrence_type='monthly', next_due_date=today,
        due_date=today, status='paid')
    parking = ParkingEntry(**base, date=today-timedelta(days=7), amount=10, title='Permit',
        parking_type='permit', recurring=True, recurrence_type='weekly', next_due_date=today,
        permit_expires=today)
    reminder = Reminder(**base, title='Due reminder', due_date=today-timedelta(days=1),
        due_mileage=1000, repeat_mileage=1000, recurring=True, frequency='daily', frequency_value=7,
        notify_push=True, notify_email=True, calendar_sync=True)
    todo = Todo(**base, title='Due task', due_date=today, recurring=True,
        frequency='daily', frequency_value=7)
    service = ServiceEntry(**base, date=today-timedelta(days=30), amount=25,
        title='Oil service', service_type='oil_change', next_due_date=today,
        warranty_expires=today+timedelta(days=5))
    consumable = ConsumableEntry(**base, date=today, amount=30, consumable_type='tire',
        install_odometer=0, expected_lifespan_km=1000)
    prediction = PredictionAlert(**base, title='Mileage alert', alert_type='maintenance',
        predicted_mileage=1000, source_data={})
    db.session.add_all([policy,current,tax,parking,reminder,todo,service,consumable,prediction])
    db.session.flush()
    path = Path(app.config['UPLOAD_FOLDER'])/'archive-receipt.pdf'
    path.write_bytes(b'%PDF-1.4\nPreserved receipt\n%%EOF')
    receipt = Attachment(**base, entry_id=service.id, filename=path.name, filepath=str(path),
                         expires_at=today+timedelta(days=5))
    db.session.add(receipt); db.session.commit()
    return {'vehicle': vehicle, 'policy': policy, 'current': current, 'tax': tax,
            'parking': parking, 'reminder': reminder, 'todo': todo, 'file': path}


@pytest.mark.parametrize('method', ['archive', 'soft_delete'])
def test_archive_restore_keeps_all_obligation_columns_and_receipt_bytes(client, user, auth_headers, obligations, method):
    vid = obligations['vehicle'].id
    before = snapshot(vid)
    content = obligations['file'].read_bytes()
    auth = auth_headers(user.id)
    response = (client.post(f'/api/vehicles/{vid}/archive', headers=auth) if method == 'archive'
                else client.delete(f'/api/vehicles/{vid}', headers=auth))
    assert response.status_code == 200, response.json
    assert snapshot(vid) == before
    assert obligations['file'].read_bytes() == content
    assert client.post(f'/api/vehicles/{vid}/unarchive', headers=auth).status_code == 200
    assert snapshot(vid) == before
    assert obligations['file'].read_bytes() == content


def test_jobs_pause_without_advancing_or_notifying_then_resume(app, client, user, auth_headers, obligations, monkeypatch):
    vid = obligations['vehicle'].id
    # Both missing dates and duplicate templates must remain untouched while
    # archived: the repair/consolidation passes are also automatic writers.
    db.session.add(TaxEntry(user_id=user.id, vehicle_id=vid, date=date.today(), amount=1,
        tax_type='road_tax', recurring=True, recurrence_type='monthly', next_due_date=None))
    db.session.add(ParkingEntry(user_id=user.id, vehicle_id=vid, date=date.today(), amount=1,
        parking_type='permit', recurring=True, recurrence_type='weekly', next_due_date=None))
    old_service = ServiceEntry(user_id=user.id, vehicle_id=vid,
        date=date.today()-timedelta(days=365), amount=10, service_type='oil_change')
    db.session.add(old_service); db.session.flush()
    db.session.add(Reminder(user_id=user.id, vehicle_id=vid, title='Superseded service',
        due_date=date.today(), source_service_id=old_service.id))
    for _ in range(2):
        db.session.add(Reminder(user_id=user.id, vehicle_id=vid,
            title='Duplicate historical reminder', due_date=date.today()))
    db.session.commit()
    push, email = [], []
    monkeypatch.setattr('app.routes.push.send_push_to_user', lambda *a, **kw: push.append(kw) or 1)
    monkeypatch.setattr('app.services.email_service.EmailService.send_alert_notification',
                        lambda *a, **kw: email.append(a) or True)
    app.config['MAIL_ENABLED'] = True
    auth = auth_headers(user.id)
    assert client.post(f'/api/vehicles/{vid}/archive', headers=auth).status_code == 200
    before = snapshot(vid)
    for job in JOBS:
        job(app)
    assert snapshot(vid) == before
    assert push == email == []
    assert client.post(f'/api/vehicles/{vid}/unarchive', headers=auth).status_code == 200
    for job in JOBS:
        job(app)
    db.session.expire_all()
    assert push and email
    assert InsurancePolicy.query.filter_by(renewed_from_id=obligations['policy'].id).count() == 1
    assert obligations['policy'].end_date == date.today()-timedelta(days=1)
    assert obligations['tax'].next_due_date > date.today()
    assert obligations['parking'].next_due_date > date.today()
    assert obligations['reminder'].mileage_notified is True


def test_due_views_exclude_archived_but_keep_standalone_tasks_and_history(client, user, auth_headers, obligations):
    vid = obligations['vehicle'].id
    # An active second car prevents the aggregator's no-vehicles early return
    # from masking unfiltered archived insurance/documents.
    db.session.add(Vehicle(user_id=user.id, name='Active control'))
    standalone = Reminder(user_id=user.id, title='Standalone reminder', due_date=date.today(), calendar_sync=True)
    task = Todo(user_id=user.id, title='Standalone task', due_date=date.today())
    db.session.add_all([standalone,task]); db.session.commit()
    auth = auth_headers(user.id)
    before = {(item['kind'],item['ref_id']) for item in build_due_items(user.id)}
    assert ('insurance',obligations['current'].id) in before
    assert client.post(f'/api/vehicles/{vid}/archive', headers=auth).status_code == 200
    items = build_due_items(user.id)
    assert {(item['kind'],item['ref_id']) for item in items} == {('reminder',standalone.id),('todo',task.id)}
    assert not any(get_all_alerts_for_user(user.id).values())
    for url,key in [('/api/insurance/expiring','policies'),('/api/taxes/expiring','entries'),
                    ('/api/services/upcoming','entries'),('/api/parking/permits','permits'),
                    ('/api/attachments/expiring','attachments'),('/api/reminders/overdue','reminders'),
                    (f'/api/reminders/by-mileage?vehicle_id={vid}','reminders')]:
        response = client.get(url, headers=auth)
        assert response.status_code == 200, (url,response.json)
        assert response.json[key] == [], (url,response.json)
    for url in ('/api/reminders/upcoming','/api/reminders?status=pending'):
        assert [row['id'] for row in client.get(url,headers=auth).json['reminders']] == [standalone.id]
    stats = client.get('/api/reminders/stats',headers=auth).json
    assert (stats['total'],stats['pending'],stats['overdue']) == (2,1,0)
    assert [row['id'] for row in client.get('/api/todos?status=pending',headers=auth).json['todos']] == [task.id]
    assert client.get(f'/api/insurance/{obligations["current"].id}',headers=auth).status_code == 200
    assert client.get(f'/api/reminders/{obligations["reminder"].id}',headers=auth).status_code == 200
    calendar = client.get('/api/calendar/entries',headers=auth)
    assert calendar.status_code == 200, calendar.json
    assert all(row['vehicle_id'] != vid for row in calendar.json['entries'])
    token = client.post('/api/calendar/feed-token',headers=auth).json['token']
    for url in ('/api/calendar/export',f'/api/calendar/feed/{token}'):
        response = client.get(url,headers=auth)
        assert response.status_code == 200
        assert b'Standalone reminder' in response.data and b'Due reminder' not in response.data
    assert client.post(f'/api/vehicles/{vid}/unarchive',headers=auth).status_code == 200
    assert {(item['kind'],item['ref_id']) for item in build_due_items(user.id)} == before
    stats = client.get('/api/reminders/stats',headers=auth).json
    assert (stats['total'],stats['pending'],stats['overdue']) == (2,2,1)


@pytest.mark.parametrize('kind', ['reminder','todo'])
def test_recurring_completion_waits_for_restore(client,user,auth_headers,obligations,kind):
    vid = obligations['vehicle'].id
    row = obligations[kind]
    auth = auth_headers(user.id)
    assert client.post(f'/api/vehicles/{vid}/archive',headers=auth).status_code == 200
    before = snapshot(vid)
    response = client.post(f'/api/{kind}s/{row.id}/complete',headers=auth)
    assert response.status_code == 409 and response.json['code'] == 'VEHICLE_ARCHIVED'
    assert snapshot(vid) == before
    assert client.post(f'/api/vehicles/{vid}/unarchive',headers=auth).status_code == 200
    assert client.post(f'/api/{kind}s/{row.id}/complete',headers=auth).status_code == 200
    assert type(row).query.filter_by(completed_from_id=row.id).count() == 1


def test_explicit_cancellation_survives_archive_restore(client,user,auth_headers,obligations):
    auth = auth_headers(user.id)
    for kind,key in [('insurance','current'),('taxes','tax'),('parking','parking')]:
        response = client.post(f'/api/{kind}/{obligations[key].id}/cancel',headers=auth)
        assert response.status_code == 200, response.json
    before = snapshot(obligations['vehicle'].id)
    assert obligations['current'].status == 'cancelled'
    assert obligations['current'].auto_renew is False
    assert not obligations['tax'].recurring and not obligations['parking'].recurring
    vid = obligations['vehicle'].id
    assert client.post(f'/api/vehicles/{vid}/archive',headers=auth).status_code == 200
    assert client.post(f'/api/vehicles/{vid}/unarchive',headers=auth).status_code == 200
    assert snapshot(vid) == before


def test_legacy_review_flags_candidates_without_repairing(app,user,obligations):
    vehicle = obligations['vehicle']
    vehicle.archived = True
    vehicle.archived_at = datetime.now()
    obligations['current'].status = 'cancelled'
    obligations['current'].end_date = date.today()
    obligations['current'].auto_renew = False
    obligations['tax'].recurring = False
    obligations['tax'].next_due_date = None
    db.session.commit()
    before = snapshot(vehicle.id)
    with db.engine.connect() as connection:
        report = scan_archive_history(connection)
    assert report['read_only'] and report['issue_count'] == 1
    assert report['issues'][0]['insurance_ids'] == [obligations['current'].id]
    assert report['issues'][0]['tax_ids'] == [obligations['tax'].id]
    cli = create_archive_review_app(app.config['SQLALCHEMY_DATABASE_URI'])
    result = cli.test_cli_runner().invoke(args=['check-archive-history'])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == report
    assert snapshot(vehicle.id) == before


def test_widget_and_bulk_calendar_settings_pause_archived_records(client,user,auth_headers,obligations,monkeypatch):
    monkeypatch.setattr('app.services.fuel_price_service.get_prices', lambda *a, **kw: None)
    vid = obligations['vehicle'].id
    obligations['reminder'].calendar_sync = False
    standalone = Reminder(user_id=user.id, title='Standalone control', due_date=date.today(), calendar_sync=False)
    fine = ParkingEntry(user_id=user.id, vehicle_id=vid, date=date.today(), amount=60,
                        parking_type='fine', fine_status='pending')
    db.session.add_all([standalone,fine]); db.session.commit()
    auth = auth_headers(user.id)
    key = client.post('/api/widget/api-key',headers=auth).json['raw_key']
    assert client.post(f'/api/vehicles/{vid}/archive',headers=auth).status_code == 200
    response = client.post('/api/calendar/sync-all',headers=auth)
    assert response.status_code == 200 and response.json['updated'] == 1
    db.session.expire_all()
    assert standalone.calendar_sync is True
    assert obligations['reminder'].calendar_sync is False
    widget = client.get('/api/widget/v1/homepage',headers={'X-API-Key':key})
    assert widget.status_code == 200
    assert widget.json['reminders'] == 1 and widget.json['vehicles'] == 0
    assert widget.json['fines_owed'].startswith('0.00 ')
    assert client.post(f'/api/vehicles/{vid}/unarchive',headers=auth).status_code == 200
    assert client.post('/api/calendar/sync-all',headers=auth).status_code == 200
    db.session.expire_all()
    assert obligations['reminder'].calendar_sync is True
    widget = client.get('/api/widget/v1/homepage',headers={'X-API-Key':key}).json
    assert widget['reminders'] == 2 and widget['vehicles'] == 1
    assert widget['fines_owed'].startswith('60.00 ')

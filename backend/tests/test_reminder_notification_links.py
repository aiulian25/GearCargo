"""GC-022: emitted Web Push links resolve to owner-scoped reminder reads."""
from datetime import date
import json
import pytest
from app import db
from app.models import Reminder, Vehicle, User, PushSubscription
from app.services.reminder_delivery import send


@pytest.mark.parametrize('trigger,kind', [('date', 'reminder'), ('mileage', 'reminder_mileage')])
def test_actual_push_envelope_contains_owner_fetchable_reminder_link(app, client, user, auth_headers, monkeypatch, trigger, kind):
    from app.routes import push
    vehicle = Vehicle(user_id=user.id, name='Linked vehicle', current_mileage=15000, distance_unit='miles')
    db.session.add(vehicle)
    db.session.flush()
    reminder = Reminder(user_id=user.id, vehicle_id=vehicle.id, title='Linked reminder', due_date=date(2028, 2, 29), due_mileage=12000)
    subscription = PushSubscription(user_id=user.id, endpoint='https://push.example.invalid/fixture', p256dh_key='fixture', auth_key='fixture', active=True)
    db.session.add_all([reminder, subscription])
    db.session.commit()
    payloads = []
    monkeypatch.setattr(push, 'webpush', lambda **kwargs: payloads.append(json.loads(kwargs['data'])))
    monkeypatch.setattr(push, '_vapid_privkey_to_pem', lambda value: 'fixture-only')
    app.config['VAPID_PRIVATE_KEY'] = 'fixture-only'
    assert send(reminder, user, 'push', trigger)
    payload = payloads[0]['data']
    assert payload == {'type': kind, 'reminder_id': reminder.id, 'vehicle_id': vehicle.id, 'url': f'/reminders/{reminder.id}'}
    response = client.get('/api' + payload['url'], headers=auth_headers(user.id))
    assert response.status_code == 200
    assert response.json['id'] == reminder.id and response.json['vehicle_name'] == vehicle.name
    stranger = User(username='link-stranger', email='link-stranger@example.invalid', is_active=True)
    stranger.set_password('FixturePassword123!')
    db.session.add(stranger)
    db.session.commit()
    denied = client.get('/api' + payload['url'], headers=auth_headers(stranger.id))
    assert denied.status_code == 404 and 'title' not in denied.json
    reminder.completed = True
    db.session.commit()
    assert client.get('/api' + payload['url'], headers=auth_headers(user.id)).json['completed'] is True
    db.session.delete(reminder)
    db.session.commit()
    assert client.get('/api' + payload['url'], headers=auth_headers(user.id)).status_code == 404

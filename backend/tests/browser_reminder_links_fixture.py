"""Opt-in GC-022 browser fixture; real API and push envelopes, no transports."""
from datetime import date
import json
from flask import jsonify, request
from tests.browser_queue_fixture import app
from app import db
from app.models import Reminder, Vehicle, User, PushSubscription
from app.routes import push
from app.services.reminder_delivery import send

payloads = []
push.webpush = lambda **kwargs: payloads.append(json.loads(kwargs['data']))
push._vapid_privkey_to_pem = lambda value: 'fixture-only'
app.config['VAPID_PRIVATE_KEY'] = 'fixture-only'
with app.app_context():
    user = User.query.filter_by(username='queue_A').one()
    vehicle = Vehicle(user_id=user.id, name='Notification vehicle', distance_unit='miles', current_mileage=15000)
    db.session.add(vehicle)
    db.session.flush()
    rows = [Reminder(user_id=user.id, vehicle_id=vehicle.id, title=title, description='Private maintenance details',
                     due_date=date(2028, 2, 29), due_mileage=12000)
            for title in ('Date notification reminder', 'Mileage notification reminder')]
    db.session.add_all(rows + [PushSubscription(user_id=user.id, endpoint='https://push.example.invalid/browser',
                                               p256dh_key='fixture', auth_key='fixture', active=True)])
    db.session.commit()
    for reminder, trigger in zip(rows, ('date', 'mileage')):
        assert send(reminder, user, 'push', trigger)


@app.route('/api/__gc022/payloads')
def notification_payloads():
    assert request.headers.get('X-GC022-Fixture') == 'disposable-browser-only'
    return jsonify(payloads)

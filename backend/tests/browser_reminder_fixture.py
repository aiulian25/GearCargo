"""GC-021 opt-in browser fixture: real app/API, deterministic clock, no transports."""
from datetime import date, datetime, timedelta, timezone
from flask import jsonify, request
from tests.browser_queue_fixture import app
from app import db
from app.models import Reminder, Vehicle, User
from app.routes import reminders as routes, push
from app.services import reminder_delivery
from app.services.email_service import EmailService
from app.services import check_due_reminders

clock = [datetime(2028, 2, 22, 12)]
sent = []
class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return clock[0].replace(tzinfo=timezone.utc) if tz else clock[0]

routes.datetime = Clock
routes.utc_today = lambda: clock[0].date()
reminder_delivery.utc_naive_now = lambda: clock[0]
push.send_push_to_user = lambda uid, title, *args, **kwargs: sent.append({'channel': 'push', 'title': title.removeprefix('Reminder: ')}) or 1
EmailService.send_alert_notification = staticmethod(lambda user, alerts, *args, **kwargs: sent.append({'channel': 'email', 'title': alerts[0]['title']}) or True)
EmailService.send_email = staticmethod(lambda *args, **kwargs: False)
app.config['MAIL_ENABLED'] = True
with app.app_context():
    user = User.query.filter_by(username='queue_A').one()
    vehicle = Vehicle(user_id=user.id, name='Miles car', distance_unit='miles', current_mileage=12000)
    db.session.add(vehicle)
    db.session.flush()
    db.session.add_all([
        Reminder(user_id=user.id, vehicle_id=vehicle.id, title='Lead reminder', reminder_type='custom',
                 due_date=date(2028, 2, 29), due_mileage=15000, notify_days_before=3),
        Reminder(user_id=user.id, vehicle_id=vehicle.id, title='Legacy mileage', reminder_type='custom',
                 due_date=date(2028, 3, 30), due_mileage=10000, recurring=True, frequency='monthly', frequency_value=1,
                 notify_push=False, notify_email=False),
    ])
    db.session.commit()


@app.route('/api/__gc021/tick', methods=['POST'])
def tick():
    assert request.headers.get('X-GC021-Fixture') == 'disposable-browser-only'
    clock[0] += timedelta(days=(request.get_json() or {}).get('advance_days', 0))
    check_due_reminders(app)
    return jsonify({'now': clock[0].isoformat(), 'sent': sent})

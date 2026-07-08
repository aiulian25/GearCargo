"""Tests for F5 — auto-generate a maintenance reminder from a service's
next_due_date / next_due_mileage."""

from datetime import date, timedelta

from app import db
from app.models import User, Vehicle, ServiceEntry, Reminder
from app.services import process_due_services


def _mk_vehicle(user_id, name='Focus', mileage=10000):
    v = Vehicle(user_id=user_id, name=name, make='Ford', model='Focus',
                current_mileage=mileage)
    db.session.add(v)
    db.session.commit()
    db.session.refresh(v)
    return v


def test_past_due_date_creates_one_reminder_and_is_idempotent(app):
    with app.app_context():
        u = User(email='s1@example.com', username='svc1', is_active=True)
        u.set_password('Str0ng!Passw0rd')
        db.session.add(u)
        db.session.commit()
        v = _mk_vehicle(u.id)
        svc = ServiceEntry(user_id=u.id, vehicle_id=v.id, date=date.today() - timedelta(days=200),
                           title='Oil & filter', amount=90,
                           next_due_date=date.today() - timedelta(days=1))
        db.session.add(svc)
        db.session.commit()
        sid, uid, vid = svc.id, u.id, v.id

    process_due_services(app)

    with app.app_context():
        rems = Reminder.query.filter_by(source_service_id=sid).all()
        assert len(rems) == 1
        r = rems[0]
        assert r.reminder_type == 'maintenance'
        assert r.title == 'Oil & filter'
        assert r.user_id == uid and r.vehicle_id == vid
        assert r.due_date == date.today() - timedelta(days=1)

    # Second run must not create a duplicate.
    process_due_services(app)
    with app.app_context():
        assert Reminder.query.filter_by(source_service_id=sid).count() == 1


def test_future_due_date_does_not_trigger(app):
    with app.app_context():
        u = User(email='s2@example.com', username='svc2', is_active=True)
        u.set_password('Str0ng!Passw0rd')
        db.session.add(u)
        db.session.commit()
        v = _mk_vehicle(u.id)
        svc = ServiceEntry(user_id=u.id, vehicle_id=v.id, date=date.today(),
                           title='Future', amount=50,
                           next_due_date=date.today() + timedelta(days=30))
        db.session.add(svc)
        db.session.commit()
        sid = svc.id

    process_due_services(app)
    with app.app_context():
        assert Reminder.query.filter_by(source_service_id=sid).count() == 0


def test_mileage_past_next_due_triggers(app):
    with app.app_context():
        u = User(email='s3@example.com', username='svc3', is_active=True)
        u.set_password('Str0ng!Passw0rd')
        db.session.add(u)
        db.session.commit()
        # Odometer 22,000 already past the 20,000 service point; no date set.
        v = _mk_vehicle(u.id, mileage=22000)
        svc = ServiceEntry(user_id=u.id, vehicle_id=v.id, date=date.today(),
                           service_type='brake_fluid', amount=60,
                           next_due_mileage=20000)
        db.session.add(svc)
        db.session.commit()
        sid = svc.id

    process_due_services(app)
    with app.app_context():
        rems = Reminder.query.filter_by(source_service_id=sid).all()
        assert len(rems) == 1
        # No next_due_date → reminder is due today so the standard pipeline notifies.
        assert rems[0].due_date == date.today()
        assert rems[0].due_mileage == 20000
        assert rems[0].title == 'Brake fluid'   # humanized service_type


def test_mileage_below_next_due_does_not_trigger(app):
    with app.app_context():
        u = User(email='s4@example.com', username='svc4', is_active=True)
        u.set_password('Str0ng!Passw0rd')
        db.session.add(u)
        db.session.commit()
        v = _mk_vehicle(u.id, mileage=15000)   # below the 20,000 point
        svc = ServiceEntry(user_id=u.id, vehicle_id=v.id, date=date.today(),
                           service_type='brake_fluid', amount=60, next_due_mileage=20000)
        db.session.add(svc)
        db.session.commit()
        sid = svc.id

    process_due_services(app)
    with app.app_context():
        assert Reminder.query.filter_by(source_service_id=sid).count() == 0


def test_service_next_due_fields_preserved(app):
    """Non-destructive: the service keeps its next_due_* after materializing."""
    with app.app_context():
        u = User(email='s5@example.com', username='svc5', is_active=True)
        u.set_password('Str0ng!Passw0rd')
        db.session.add(u)
        db.session.commit()
        v = _mk_vehicle(u.id)
        due = date.today() - timedelta(days=2)
        svc = ServiceEntry(user_id=u.id, vehicle_id=v.id, date=date.today(),
                           title='Coolant', amount=40, next_due_date=due, next_due_mileage=30000)
        db.session.add(svc)
        db.session.commit()
        sid = svc.id

    process_due_services(app)
    with app.app_context():
        svc = db.session.get(ServiceEntry, sid)
        assert svc.next_due_date == due
        assert svc.next_due_mileage == 30000

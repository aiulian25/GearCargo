"""Tests for F7 — mileage-based reminders fire when the odometer crosses due_mileage."""

from datetime import date, timedelta

from app import db
from app.models import User, Vehicle, Reminder
from app.services import _check_mileage_reminders


def _mk_user(email, username):
    u = User(email=email, username=username, is_active=True)
    u.set_password('Str0ng!Passw0rd')
    db.session.add(u)
    db.session.commit()
    return u


def _mk_vehicle(user_id, mileage):
    v = Vehicle(user_id=user_id, name='Focus', make='Ford', model='Focus',
                current_mileage=mileage, distance_unit='km')
    db.session.add(v)
    db.session.commit()
    db.session.refresh(v)
    return v


def _mk_reminder(user_id, vehicle_id, due_mileage, due_date=None):
    # due_date is NOT NULL on the model; use a far-future date so the date path
    # never fires — isolating the mileage trigger.
    r = Reminder(user_id=user_id, vehicle_id=vehicle_id, title='Change oil',
                 due_mileage=due_mileage,
                 due_date=due_date or (date.today() + timedelta(days=3650)),
                 reminder_type='maintenance')
    db.session.add(r)
    db.session.commit()
    db.session.refresh(r)
    return r


def test_crossing_due_mileage_pushes_once(app, monkeypatch):
    import app.routes.push as push_mod
    calls = []
    monkeypatch.setattr(push_mod, 'send_push_to_user',
                        lambda *a, **k: calls.append((a, k)) or 1)

    with app.app_context():
        u = _mk_user('m1@example.com', 'mil1')
        v = _mk_vehicle(u.id, mileage=1200)          # already past 1000
        r = _mk_reminder(u.id, v.id, due_mileage=1000)
        rid = r.id

    _check_mileage_reminders(app)
    assert len(calls) == 1
    with app.app_context():
        assert db.session.get(Reminder, rid).mileage_notified is True

    # Second tick must not re-push.
    _check_mileage_reminders(app)
    assert len(calls) == 1


def test_below_threshold_does_not_push(app, monkeypatch):
    import app.routes.push as push_mod
    calls = []
    monkeypatch.setattr(push_mod, 'send_push_to_user', lambda *a, **k: calls.append(1) or 1)

    with app.app_context():
        u = _mk_user('m2@example.com', 'mil2')
        v = _mk_vehicle(u.id, mileage=800)           # below 1000
        _mk_reminder(u.id, v.id, due_mileage=1000)

    _check_mileage_reminders(app)
    assert calls == []


def test_completed_or_dismissed_ignored(app, monkeypatch):
    import app.routes.push as push_mod
    calls = []
    monkeypatch.setattr(push_mod, 'send_push_to_user', lambda *a, **k: calls.append(1) or 1)

    with app.app_context():
        u = _mk_user('m3@example.com', 'mil3')
        v = _mk_vehicle(u.id, mileage=1500)
        r1 = _mk_reminder(u.id, v.id, due_mileage=1000)
        r1.completed = True
        r2 = _mk_reminder(u.id, v.id, due_mileage=1000)
        r2.dismissed = True
        db.session.commit()

    _check_mileage_reminders(app)
    assert calls == []


def test_mileage_only_reminder_far_future_date_still_fires(app, monkeypatch):
    """A mileage reminder whose date is far off still fires on the odometer crossing."""
    import app.routes.push as push_mod
    calls = []
    monkeypatch.setattr(push_mod, 'send_push_to_user', lambda *a, **k: calls.append(1) or 1)

    with app.app_context():
        u = _mk_user('m4@example.com', 'mil4')
        v = _mk_vehicle(u.id, mileage=90500)
        _mk_reminder(u.id, v.id, due_mileage=90000,
                     due_date=date.today() + timedelta(days=365))

    _check_mileage_reminders(app)
    assert len(calls) == 1

"""Parking calendar events show their cost in the title, like fuel events.

`get_event_data_for_entry` is a pure formatter (attribute access via getattr),
so a lightweight stub entry is enough — no DB needed.
"""

from datetime import date
from types import SimpleNamespace

from app.services.calendar_service import get_event_data_for_entry


def test_parking_event_title_includes_cost():
    entry = SimpleNamespace(
        amount=70.0, location='NCP Reading', parking_type='hourly',
        date=date(2026, 7, 10), notes=None)
    ev = get_event_data_for_entry('parking', entry, 'Nissan Qashqai')
    assert ev is not None
    # Cost shown in the title, mirroring the fuel event convention.
    assert '(70.00)' in ev['title']
    assert 'Parking: Nissan Qashqai @ NCP Reading' in ev['title']


def test_parking_event_title_without_cost_is_unchanged():
    entry = SimpleNamespace(
        amount=None, location='Driveway', parking_type=None,
        date=date(2026, 7, 10), notes=None)
    ev = get_event_data_for_entry('parking', entry, 'Focus')
    assert ev['title'] == '🅿️ Parking: Focus @ Driveway'


def test_fuel_event_title_still_includes_volume_and_cost():
    entry = SimpleNamespace(
        liters=46.1, total_price=70.0, amount=70.0, fuel_type='diesel',
        station='Costco', date=date(2026, 7, 10), notes=None)
    ev = get_event_data_for_entry('fuel', entry, 'Nissan Qashqai')
    assert '46.1L' in ev['title']
    assert '70.00' in ev['title']


# ── R4-08: the formatter read attributes the models do not have ──────────────
# `getattr`/`hasattr` guards made every one of these fail SILENTLY (a missing
# line in the event) or, for `vehicle.nickname`, crash the whole sync. Real model
# instances are used below — a SimpleNamespace stub would only prove the stub has
# the attributes the code asks for, which is exactly the bug.

from datetime import timedelta

from app import db
from app.models import Reminder, ServiceEntry, User, Vehicle
from app.services.calendar_service import CalendarService, sync_entry_to_calendar
from app.utils.timeutils import utc_today


def test_service_event_uses_next_due_date_and_odometer():
    """A "Service Due" event must land on the NEXT due date, not the date the
    past service was carried out, and must carry the odometer reading."""
    done_on = date(2026, 3, 1)
    due_on = date(2026, 9, 1)
    entry = ServiceEntry(date=done_on, next_due_date=due_on, odometer=12345,
                         service_type='oil_change', notes='Synthetic 5W-30')

    event = get_event_data_for_entry('service', entry, 'Golf')

    assert event['start'].date() == due_on          # was: done_on
    assert 'Mileage: 12345' in event['description']  # was: absent entirely
    assert 'Service: oil_change' in event['description']
    assert 'Synthetic 5W-30' in event['description']


def test_service_event_falls_back_to_the_entry_date():
    entry = ServiceEntry(date=date(2026, 3, 1), next_due_date=None, odometer=None)
    event = get_event_data_for_entry('service', entry, 'Golf')
    assert event['start'].date() == date(2026, 3, 1)
    assert 'Mileage:' not in event['description']


def test_service_event_omits_an_unset_service_type():
    """`hasattr` is True for a column holding None — the description used to
    read "Service: None"."""
    entry = ServiceEntry(date=date(2026, 3, 1), service_type=None)
    event = get_event_data_for_entry('service', entry, 'Golf')
    assert 'None' not in event['description']


def test_reminder_event_includes_its_description():
    """Reminder stores free text in `description`; the formatter asked for
    `notes`, which the model has never had, so the text was dropped."""
    reminder = Reminder(title='MOT', due_date=date(2026, 9, 1),
                        description='Bring the logbook')
    event = get_event_data_for_entry('reminder', reminder, 'Golf')
    assert 'Bring the logbook' in event['description']


def _user_with_calendar(email):
    user = User(username=email.split('@')[0], email=email, is_active=True,
                calendar_enabled=True, calendar_provider='caldav',
                calendar_url='https://cal.example.com/dav', calendar_username='u',
                calendar_password='encrypted-placeholder', calendar_id='primary')
    user.set_password('StrongPass123!')
    db.session.add(user)
    db.session.commit()
    return user


def _capture_created_event(monkeypatch):
    captured = {}

    def _create_event(self, **kwargs):
        captured.update(kwargs)
        return True, kwargs.get('uid', 'ok')

    monkeypatch.setattr(CalendarService, 'create_event', _create_event)
    return captured


def test_sync_labels_the_event_with_the_vehicle_name(app, monkeypatch):
    """A vehicle with no `make` used to crash the whole sync on the phantom
    `vehicle.nickname`, so nothing reached the calendar at all."""
    captured = _capture_created_event(monkeypatch)

    with app.app_context():
        user = _user_with_calendar('nomake@example.com')
        vehicle = Vehicle(user_id=user.id, name='Daily', make=None, model=None)
        db.session.add(vehicle)
        db.session.commit()
        entry = ServiceEntry(user_id=user.id, vehicle_id=vehicle.id,
                             date=utc_today(), service_type='inspection', amount=0)
        db.session.add(entry)
        db.session.commit()

        success, message = sync_entry_to_calendar(user, 'service', entry)

    assert success, message
    assert 'nickname' not in message
    assert 'Daily' in captured['title']


def test_sync_never_renders_none_in_the_vehicle_label(app, monkeypatch):
    """`f"{make} {model}"` printed "Ford None" whenever the model was unset."""
    captured = _capture_created_event(monkeypatch)

    with app.app_context():
        user = _user_with_calendar('nomodel@example.com')
        vehicle = Vehicle(user_id=user.id, name='Runabout', make='Ford',
                          model=None, year=2019)
        db.session.add(vehicle)
        db.session.commit()
        entry = ServiceEntry(user_id=user.id, vehicle_id=vehicle.id,
                             date=utc_today(), service_type='inspection', amount=0)
        db.session.add(entry)
        db.session.commit()

        assert sync_entry_to_calendar(user, 'service', entry)[0]

    assert 'None' not in captured['title']
    assert 'Ford' in captured['title']

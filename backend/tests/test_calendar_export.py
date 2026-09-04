"""Regression tests for R4-03: ``GET /api/calendar/export`` filtered on
``Reminder.status``, a column that does not exist (the model has ``completed`` /
``dismissed`` — models/reminder.py:34-37), so the .ics download 500'd every time.

Also pinned here:
  * owner scoping — the export must never contain another user's reminders;
  * RFC 5545 conformance — for an all-day event DTEND is EXCLUSIVE and must be
    LATER than DTSTART (§3.8.2.2). Emitting DTEND == DTSTART produces a
    zero-length event that strict calendar clients reject outright.
"""

from datetime import timedelta

from app import db
from app.models import Reminder, User, Vehicle
from app.utils.timeutils import utc_today


def _make_user(email):
    user = User(username=email.split('@')[0], email=email, is_active=True)
    user.set_password('StrongPass123!')
    db.session.add(user)
    db.session.commit()
    return user


def _make_reminder(user, title, vehicle=None, **flags):
    reminder = Reminder(
        user_id=user.id,
        vehicle_id=vehicle.id if vehicle else None,
        title=title,
        due_date=flags.pop('due_date', utc_today() + timedelta(days=7)),
        reminder_type='maintenance',
        priority=flags.pop('priority', 'medium'),
        completed=flags.pop('completed', False),
        dismissed=flags.pop('dismissed', False),
    )
    db.session.add(reminder)
    db.session.commit()
    return reminder


def _export(client, headers, query=''):
    return client.get(f'/api/calendar/export{query}', headers=headers)


def test_export_returns_ics_with_only_actionable_reminders(app, client, auth_headers):
    with app.app_context():
        user = _make_user('export@example.com')
        _make_reminder(user, 'MOT due')
        _make_reminder(user, 'Already done', completed=True)
        _make_reminder(user, 'Not interested', dismissed=True)
        headers = auth_headers(user.id)

    response = _export(client, headers)

    assert response.status_code == 200
    assert response.headers['Content-Type'].startswith('text/calendar')
    assert 'gearcargo_reminders.ics' in response.headers.get('Content-Disposition', '')

    body = response.get_data(as_text=True)
    assert body.count('BEGIN:VEVENT') == 1
    assert 'MOT due' in body
    assert 'Already done' not in body
    assert 'Not interested' not in body


def test_export_is_scoped_to_the_authenticated_user(app, client, auth_headers):
    with app.app_context():
        owner = _make_user('owner@example.com')
        stranger = _make_user('stranger@example.com')
        _make_reminder(owner, 'My service')
        _make_reminder(stranger, 'Their service')
        headers = auth_headers(owner.id)

    body = _export(client, headers).get_data(as_text=True)
    assert 'My service' in body
    assert 'Their service' not in body


def test_export_filters_by_vehicle_and_labels_the_summary(app, client, auth_headers):
    with app.app_context():
        user = _make_user('pervehicle@example.com')
        golf = Vehicle(user_id=user.id, name='Golf')
        focus = Vehicle(user_id=user.id, name='Focus')
        db.session.add_all([golf, focus])
        db.session.commit()
        _make_reminder(user, 'Tyres', vehicle=golf)
        _make_reminder(user, 'Brakes', vehicle=focus)
        headers, golf_id = auth_headers(user.id), golf.id

    body = _export(client, headers, f'?vehicle_id={golf_id}').get_data(as_text=True)
    assert body.count('BEGIN:VEVENT') == 1
    # The vehicle name is appended to the event summary (may be folded across
    # lines by the iCalendar 75-octet rule, so compare on the unfolded body).
    assert 'Tyres - Golf' in body.replace('\r\n ', '')
    assert 'Brakes' not in body


def test_export_all_day_events_end_the_following_day(app, client, auth_headers):
    """RFC 5545 §3.8.2.2: DTEND must be later than DTSTART. For VALUE=DATE the
    end is exclusive, so a one-day event ends on the NEXT day."""
    with app.app_context():
        user = _make_user('allday@example.com')
        due = utc_today() + timedelta(days=3)
        _make_reminder(user, 'Insurance renewal', due_date=due)
        headers = auth_headers(user.id)

    body = _export(client, headers).get_data(as_text=True)
    assert f"DTSTART;VALUE=DATE:{due:%Y%m%d}" in body
    assert f"DTEND;VALUE=DATE:{due + timedelta(days=1):%Y%m%d}" in body

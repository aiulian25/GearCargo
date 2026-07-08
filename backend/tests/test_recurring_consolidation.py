"""Root-cause tests: recurring template multiplication + duplicate reminders.

Covers the fixes for the "Coming up" duplicate flood:
- generated recurring tax/parking occurrences must be plain booked rows,
  never new templates;
- _consolidate_recurring_templates demotes historical duplicate templates;
- dedupe_duplicate_reminders dismisses exact-duplicate active reminders;
- process_due_services skips superseded next-due pointers and dismisses
  previously created stale auto-reminders.
"""

from datetime import date, timedelta

from app import db
from app.models import Vehicle, TaxEntry, ParkingEntry, Reminder, ServiceEntry
from app.services import (
    process_recurring_tax_entries,
    process_recurring_parking_entries,
    dedupe_duplicate_reminders,
    process_due_services,
)

TODAY = date.today()


def _mk_vehicle(user_id, name='Qashqai'):
    v = Vehicle(user_id=user_id, name=name, make='Nissan', model='Qashqai')
    db.session.add(v)
    db.session.commit()
    db.session.refresh(v)
    return v


def _mk_recurring_tax(user_id, vehicle_id, entry_date, next_due):
    tx = TaxEntry(
        user_id=user_id, vehicle_id=vehicle_id, date=entry_date, amount=15,
        tax_type='road_tax', title='Road Tax', status='paid',
        recurring=True, recurrence_type='monthly', next_due_date=next_due,
    )
    db.session.add(tx)
    return tx


def test_generated_tax_occurrence_is_not_a_template(app, user):
    """A backfilled occurrence must be a plain paid row (recurring=False)."""
    with app.app_context():
        v = _mk_vehicle(user.id)
        _mk_recurring_tax(user.id, v.id, TODAY - timedelta(days=40),
                          next_due=TODAY - timedelta(days=10))
        db.session.commit()

        process_recurring_tax_entries(app)

        rows = TaxEntry.query.filter_by(vehicle_id=v.id).order_by(TaxEntry.id).all()
        assert len(rows) >= 2  # template + at least one generated occurrence
        template, generated = rows[0], rows[1:]
        assert template.recurring is True
        assert template.next_due_date > TODAY  # advanced into the future
        for g in generated:
            assert g.recurring is False
            assert g.next_due_date is None


def test_duplicate_tax_templates_consolidated(app, client, user, auth_headers):
    """Pre-fix data: N templates for one series → one survives, feed shows one."""
    with app.app_context():
        v = _mk_vehicle(user.id)
        # Five historical occurrences, ALL wrongly recurring with the same
        # next_due_date (the exact state observed in production).
        next_due = TODAY + timedelta(days=1)
        for months_ago in range(5):
            _mk_recurring_tax(user.id, v.id,
                              TODAY - timedelta(days=30 * (months_ago + 1)),
                              next_due=next_due)
        db.session.commit()

        process_recurring_tax_entries(app)

        recurring = TaxEntry.query.filter(
            TaxEntry.vehicle_id == v.id, TaxEntry.recurring == True,  # noqa: E712
        ).all()
        assert len(recurring) == 1  # exactly one template survives

    body = client.get('/api/due', headers=auth_headers(user.id)).get_json()
    tax_items = [it for it in body['items'] if it['kind'] == 'tax']
    assert len(tax_items) == 1  # the feed shows the series once


def test_duplicate_parking_templates_consolidated(app, user):
    with app.app_context():
        v = _mk_vehicle(user.id)
        for months_ago in range(3):
            db.session.add(ParkingEntry(
                user_id=user.id, vehicle_id=v.id, amount=30,
                date=TODAY - timedelta(days=30 * (months_ago + 1)),
                parking_type='permit', location='Downtown', title='Monthly permit',
                recurring=True, recurrence_type='monthly',
                next_due_date=TODAY + timedelta(days=2),
                permit_expires=TODAY + timedelta(days=2),
            ))
        db.session.commit()

        process_recurring_parking_entries(app)

        recurring = ParkingEntry.query.filter(
            ParkingEntry.vehicle_id == v.id,
            ParkingEntry.recurring == True,  # noqa: E712
        ).all()
        assert len(recurring) == 1


def test_dedupe_duplicate_reminders(app, client, user, auth_headers):
    """Exact duplicates (importer artifacts) collapse to one active reminder."""
    with app.app_context():
        v = _mk_vehicle(user.id)
        for _ in range(3):
            db.session.add(Reminder(
                user_id=user.id, vehicle_id=v.id, title='MOT',
                due_date=TODAY - timedelta(days=10), reminder_type='inspection'))
        # A DIFFERENT due date is a legitimate separate occurrence — kept.
        db.session.add(Reminder(
            user_id=user.id, vehicle_id=v.id, title='MOT',
            due_date=TODAY + timedelta(days=300), reminder_type='inspection'))
        db.session.commit()

        dedupe_duplicate_reminders(app)

        active = Reminder.query.filter(
            Reminder.vehicle_id == v.id,
            Reminder.dismissed == False,  # noqa: E712
        ).all()
        assert len(active) == 2  # one per distinct due date
        assert Reminder.query.filter_by(vehicle_id=v.id, dismissed=True).count() == 2

    # The feed reflects the cleanup (the far-future one is outside the window).
    body = client.get('/api/due', headers=auth_headers(user.id)).get_json()
    assert sum(1 for it in body['items'] if it['title'] == 'MOT') == 1


def test_superseded_service_pointer_not_materialized(app, user):
    """An old service's next-due is obsolete once a newer same-type service exists."""
    with app.app_context():
        v = _mk_vehicle(user.id)
        old = ServiceEntry(
            user_id=user.id, vehicle_id=v.id, amount=100,
            date=TODAY - timedelta(days=400), service_type='inspection',
            title='MOT', next_due_date=TODAY - timedelta(days=35))
        newer = ServiceEntry(
            user_id=user.id, vehicle_id=v.id, amount=100,
            date=TODAY - timedelta(days=30), service_type='inspection',
            title='MOT', next_due_date=TODAY + timedelta(days=335))
        db.session.add_all([old, newer])
        # A stale auto-reminder previously created from the old pointer.
        db.session.add(Reminder(
            user_id=user.id, vehicle_id=v.id, title='MOT',
            reminder_type='maintenance', due_date=TODAY - timedelta(days=35),
            source_service_id=None))
        db.session.commit()
        old_id = old.id
        db.session.add(Reminder(
            user_id=user.id, vehicle_id=v.id, title='MOT (auto)',
            reminder_type='maintenance', due_date=TODAY - timedelta(days=35),
            source_service_id=old_id))
        db.session.commit()

        process_due_services(app)

        # No NEW reminder for the superseded old pointer…
        assert Reminder.query.filter_by(source_service_id=old_id).count() == 1
        # …and the pre-existing stale auto-reminder was dismissed.
        stale = Reminder.query.filter_by(source_service_id=old_id).first()
        assert stale.dismissed is True


def test_due_feed_skips_superseded_service_and_paid_tax(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        # Superseded service pointer (newer same-type service exists).
        db.session.add(ServiceEntry(
            user_id=user.id, vehicle_id=v.id, amount=100,
            date=TODAY - timedelta(days=400), service_type='inspection',
            next_due_date=TODAY - timedelta(days=35)))
        db.session.add(ServiceEntry(
            user_id=user.id, vehicle_id=v.id, amount=100,
            date=TODAY - timedelta(days=30), service_type='inspection'))
        # A settled one-time tax with a past due date must not nag.
        db.session.add(TaxEntry(
            user_id=user.id, vehicle_id=v.id, amount=15, date=TODAY - timedelta(days=60),
            tax_type='road_tax', status='paid', due_date=TODAY - timedelta(days=60)))
        db.session.commit()

    body = client.get('/api/due', headers=auth_headers(user.id)).get_json()
    assert body['count'] == 0

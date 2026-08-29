"""Step 1 — hardening of the recurring generators themselves.

Template-multiplication and due-feed behaviour live in
``test_recurring_consolidation.py``. This file covers what the generators write
and how far they go:

- the generated occurrence must inherit the template's CURRENCY (it used to
  fall back to the Entry.currency default 'EUR', booking every non-EUR
  recurring tax in the wrong currency);
- an ancient template must not fabricate unbounded history — the tax loop now
  honours _MAX_RECURRING_BACKFILL like the parking loop already did;
- the template's advanced next_due_date must be COMMITTED even when the run
  created nothing, otherwise the series stays past-due and nags forever.
"""

from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from app import db
from app.models import Vehicle, TaxEntry, ParkingEntry
from app.services import (
    _MAX_RECURRING_BACKFILL,
    process_recurring_parking_entries,
    process_recurring_tax_entries,
)

TODAY = date.today()


def _vehicle(user_id, name='Qashqai'):
    vehicle = Vehicle(user_id=user_id, name=name, make='Nissan', model='Qashqai')
    db.session.add(vehicle)
    db.session.commit()
    db.session.refresh(vehicle)
    return vehicle


def _recurring_tax(user_id, vehicle_id, entry_date, next_due, **kwargs):
    fields = dict(
        user_id=user_id, vehicle_id=vehicle_id, date=entry_date, amount=15,
        tax_type='road_tax', title='Road Tax', status='paid',
        recurring=True, recurrence_type='monthly', next_due_date=next_due,
    )
    fields.update(kwargs)
    tax = TaxEntry(**fields)
    db.session.add(tax)
    db.session.commit()
    db.session.refresh(tax)
    return tax


# --- currency ------------------------------------------------------------------

def test_generated_tax_occurrence_inherits_template_currency(app, user):
    """A RON template must not book its occurrences in EUR."""
    with app.app_context():
        vehicle = _vehicle(user.id)
        template = _recurring_tax(
            user.id, vehicle.id,
            entry_date=TODAY - relativedelta(months=4),
            next_due=TODAY - relativedelta(months=3),
            currency='RON',
        )
        template_id = template.id

    process_recurring_tax_entries(app)

    with app.app_context():
        generated = TaxEntry.query.filter(
            TaxEntry.vehicle_id == TaxEntry.query.get(template_id).vehicle_id,
            TaxEntry.id != template_id,
        ).all()
        assert generated, 'expected backfilled occurrences'
        assert {entry.currency for entry in generated} == {'RON'}


def test_generated_parking_occurrence_inherits_template_currency(app, user):
    """Parking already did this — pinned so it cannot regress alongside tax."""
    with app.app_context():
        vehicle = _vehicle(user.id, name='Golf')
        template = ParkingEntry(
            user_id=user.id, vehicle_id=vehicle.id,
            date=TODAY - relativedelta(months=3),
            amount=40, currency='RON', parking_type='permit',
            title='City Permit', location='City Centre',
            recurring=True, recurrence_type='monthly',
            next_due_date=TODAY - relativedelta(months=2),
        )
        db.session.add(template)
        db.session.commit()
        template_id = template.id

    process_recurring_parking_entries(app)

    with app.app_context():
        generated = ParkingEntry.query.filter(ParkingEntry.id != template_id).all()
        assert generated
        assert {entry.currency for entry in generated} == {'RON'}


# --- backfill cap --------------------------------------------------------------

def test_ancient_tax_template_is_capped_but_still_settles(app, user):
    """20 years of monthly periods must not become 240 fabricated rows."""
    with app.app_context():
        vehicle = _vehicle(user.id)
        template = _recurring_tax(
            user.id, vehicle.id,
            entry_date=TODAY - relativedelta(years=20),
            next_due=TODAY - relativedelta(years=20) + relativedelta(months=1),
        )
        template_id = template.id

    process_recurring_tax_entries(app)

    with app.app_context():
        created = TaxEntry.query.filter(TaxEntry.id != template_id).count()
        assert created <= _MAX_RECURRING_BACKFILL, f'{created} rows fabricated'

        # Capped or not, the series must reach the future so it settles.
        template = db.session.get(TaxEntry, template_id)
        assert template.next_due_date > TODAY


def test_capped_run_does_not_regenerate_forever(app, user):
    """A second run must not keep adding rows once the template is in the future."""
    with app.app_context():
        vehicle = _vehicle(user.id)
        template = _recurring_tax(
            user.id, vehicle.id,
            entry_date=TODAY - relativedelta(years=20),
            next_due=TODAY - relativedelta(years=20) + relativedelta(months=1),
        )
        template_id = template.id

    process_recurring_tax_entries(app)
    with app.app_context():
        after_first = TaxEntry.query.filter(TaxEntry.id != template_id).count()

    process_recurring_tax_entries(app)
    with app.app_context():
        assert TaxEntry.query.filter(TaxEntry.id != template_id).count() == after_first


# --- advancement is committed even with nothing created ------------------------

def test_advancement_persists_when_every_occurrence_is_deduped(app, user):
    """The regression the unconditional commit fixes.

    Pre-create the only missed occurrence so the generator's dedup skips it.
    created_count stays 0, so the old `if created_count: commit()` threw away
    the advanced next_due_date and the template stayed past-due forever.
    """
    with app.app_context():
        vehicle = _vehicle(user.id)
        # Exactly one due occurrence: today. (Anything earlier would leave a
        # second, genuinely-missing period for the generator to create.)
        missed = TODAY
        template = _recurring_tax(
            user.id, vehicle.id,
            entry_date=TODAY - relativedelta(months=1),
            next_due=missed,
        )
        template_id = template.id

        # The occurrence the generator would have created already exists.
        db.session.add(TaxEntry(
            user_id=user.id, vehicle_id=vehicle.id, date=missed, amount=15,
            currency=template.currency, tax_type='road_tax', title='Road Tax',
            status='paid', recurring=False,
        ))
        db.session.commit()
        before = TaxEntry.query.count()

    process_recurring_tax_entries(app)

    with app.app_context():
        assert TaxEntry.query.count() == before, 'dedup should have created nothing'
        template = db.session.get(TaxEntry, template_id)
        assert template.next_due_date > TODAY, 'advancement was rolled back'


def test_parking_advancement_persists_when_deduped(app, user):
    """Same commit fix on the parking generator."""
    with app.app_context():
        vehicle = _vehicle(user.id, name='Golf')
        missed = TODAY          # exactly one due occurrence — see the tax case
        template = ParkingEntry(
            user_id=user.id, vehicle_id=vehicle.id,
            date=TODAY - timedelta(days=7), amount=40, parking_type='permit',
            title='City Permit', recurring=True, recurrence_type='weekly',
            next_due_date=missed,
        )
        db.session.add(template)
        db.session.add(ParkingEntry(
            user_id=user.id, vehicle_id=vehicle.id, date=missed, amount=40,
            parking_type='permit', title='City Permit', recurring=False,
        ))
        db.session.commit()
        template_id = template.id
        before = ParkingEntry.query.count()

    process_recurring_parking_entries(app)

    with app.app_context():
        assert ParkingEntry.query.count() == before
        template = db.session.get(ParkingEntry, template_id)
        assert template.next_due_date > TODAY


# --- recurrence steps ----------------------------------------------------------

def test_quarterly_tax_template_advances_by_three_months(app, user):
    """_recurrence_step now drives the tax job — quarterly must mean 3 months."""
    with app.app_context():
        vehicle = _vehicle(user.id)
        next_due = TODAY - relativedelta(months=1)
        template = _recurring_tax(
            user.id, vehicle.id,
            entry_date=TODAY - relativedelta(months=4),
            next_due=next_due,
            recurrence_type='quarterly',
        )
        template_id = template.id

    process_recurring_tax_entries(app)

    with app.app_context():
        template = db.session.get(TaxEntry, template_id)
        assert template.next_due_date == next_due + relativedelta(months=3)

"""Step 3 — PUT /taxes/<id> must handle recurrence transitions.

`recurring` and `recurrence_type` are plain columns, but `next_due_date` is what
actually drives both the daily generator and the "Coming up" due feed. Editing
one without the other produced the two symptoms this file pins:

- switching recurring OFF in the form left next_due_date set. The due feed's tax
  branch filters on next_due_date alone (services/due.py) and the generator only
  advances `recurring == True` rows, so the item nagged forever and could not be
  cleared from the UI.
- switching recurring ON left next_due_date NULL, so the 6 AM job seeded it to
  `entry.date + step` and then backfilled every missed period as a booked,
  `status='paid'` entry — fabricating history from a checkbox.

The recompute deliberately advances to the first FUTURE occurrence, matching
create_tax_entry. An edit never backfills (report decision A2).
"""

from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from app import db
from app.models import Vehicle, TaxEntry
from app.services import process_recurring_tax_entries

TODAY = date.today()
TAXES_URL = '/api/taxes'


def _vehicle(user_id, name='Qashqai'):
    vehicle = Vehicle(user_id=user_id, name=name, make='Nissan', model='Qashqai')
    db.session.add(vehicle)
    db.session.commit()
    db.session.refresh(vehicle)
    return vehicle


def _tax(user_id, vehicle_id, **kwargs):
    fields = dict(
        user_id=user_id, vehicle_id=vehicle_id,
        date=TODAY - relativedelta(months=1), amount=15, currency='EUR',
        tax_type='road_tax', title='Road Tax', status='paid',
        recurring=False, recurrence_type=None, next_due_date=None,
    )
    fields.update(kwargs)
    tax = TaxEntry(**fields)
    db.session.add(tax)
    db.session.commit()
    db.session.refresh(tax)
    return tax


def _reload(app, tax_id):
    with app.app_context():
        db.session.remove()
        return db.session.get(TaxEntry, tax_id)


# --- switching OFF -------------------------------------------------------------

def test_turning_recurring_off_clears_next_due_date(app, client, user, auth_headers):
    """The due-feed ghost: recurring off must settle next_due_date too."""
    with app.app_context():
        vehicle = _vehicle(user.id)
        tax = _tax(user.id, vehicle.id, recurring=True, recurrence_type='monthly',
                   next_due_date=TODAY + relativedelta(months=1))
        tax_id = tax.id

    resp = client.put(f'{TAXES_URL}/{tax_id}', json={'recurring': False},
                      headers=auth_headers(user.id))
    assert resp.status_code == 200, resp.data[:200]
    assert resp.get_json()['entry']['next_due_date'] is None

    assert _reload(app, tax_id).next_due_date is None


def test_turning_recurring_off_matches_the_cancel_endpoint(app, client, user, auth_headers):
    """PUT {recurring: false} and POST /cancel must leave the same state."""
    with app.app_context():
        vehicle = _vehicle(user.id)
        via_put = _tax(user.id, vehicle.id, recurring=True, recurrence_type='annual',
                       next_due_date=TODAY + relativedelta(months=2))
        via_cancel = _tax(user.id, vehicle.id, tax_type='registration',
                          title='Registration', recurring=True,
                          recurrence_type='annual',
                          next_due_date=TODAY + relativedelta(months=2))
        put_id, cancel_id = via_put.id, via_cancel.id

    client.put(f'{TAXES_URL}/{put_id}', json={'recurring': False},
               headers=auth_headers(user.id))
    client.post(f'{TAXES_URL}/{cancel_id}/cancel', headers=auth_headers(user.id))

    with app.app_context():
        db.session.remove()
        put_entry = db.session.get(TaxEntry, put_id)
        cancel_entry = db.session.get(TaxEntry, cancel_id)
        assert (put_entry.recurring, put_entry.next_due_date) == \
               (cancel_entry.recurring, cancel_entry.next_due_date) == (False, None)


def test_string_false_is_not_truthy(app, client, user, auth_headers):
    """bool() coercion — an API client sending "false" must not stay recurring."""
    with app.app_context():
        vehicle = _vehicle(user.id)
        tax = _tax(user.id, vehicle.id, recurring=True, recurrence_type='monthly',
                   next_due_date=TODAY + relativedelta(months=1))
        tax_id = tax.id

    client.put(f'{TAXES_URL}/{tax_id}', json={'recurring': ''},
               headers=auth_headers(user.id))

    entry = _reload(app, tax_id)
    assert entry.recurring is False
    assert entry.next_due_date is None


# --- switching ON --------------------------------------------------------------

def test_turning_recurring_on_schedules_a_future_date(app, client, user, auth_headers):
    with app.app_context():
        vehicle = _vehicle(user.id)
        tax = _tax(user.id, vehicle.id, date=TODAY - relativedelta(years=2))
        tax_id = tax.id

    resp = client.put(f'{TAXES_URL}/{tax_id}',
                      json={'recurring': True, 'recurrence_type': 'monthly'},
                      headers=auth_headers(user.id))
    assert resp.status_code == 200, resp.data[:200]

    entry = _reload(app, tax_id)
    assert entry.next_due_date is not None
    assert entry.next_due_date > TODAY, 'an edit must not schedule into the past'


def test_turning_recurring_on_does_not_fabricate_history(app, client, user, auth_headers):
    """The whole point: no back-dated 'paid' rows conjured from a checkbox."""
    with app.app_context():
        vehicle = _vehicle(user.id)
        tax = _tax(user.id, vehicle.id, date=TODAY - relativedelta(years=2))
        tax_id = tax.id
        before = TaxEntry.query.count()

    client.put(f'{TAXES_URL}/{tax_id}',
               json={'recurring': True, 'recurrence_type': 'monthly'},
               headers=auth_headers(user.id))

    process_recurring_tax_entries(app)

    with app.app_context():
        db.session.remove()
        assert TaxEntry.query.count() == before, 'the generator backfilled an edit'


def test_explicit_next_due_date_wins(app, client, user, auth_headers):
    """A client that sends its own next_due_date is never second-guessed."""
    chosen = TODAY + relativedelta(months=5)
    with app.app_context():
        vehicle = _vehicle(user.id)
        tax = _tax(user.id, vehicle.id)
        tax_id = tax.id

    client.put(f'{TAXES_URL}/{tax_id}',
               json={'recurring': True, 'recurrence_type': 'monthly',
                     'next_due_date': chosen.isoformat()},
               headers=auth_headers(user.id))

    assert _reload(app, tax_id).next_due_date == chosen


# --- changing frequency --------------------------------------------------------

def test_changing_frequency_reschedules(app, client, user, auth_headers):
    """annual → monthly must take effect now, not up to a year from now."""
    far_off = TODAY + relativedelta(months=11)
    with app.app_context():
        vehicle = _vehicle(user.id)
        tax = _tax(user.id, vehicle.id, recurring=True, recurrence_type='annual',
                   next_due_date=far_off)
        tax_id = tax.id

    client.put(f'{TAXES_URL}/{tax_id}', json={'recurrence_type': 'monthly'},
               headers=auth_headers(user.id))

    entry = _reload(app, tax_id)
    assert entry.next_due_date != far_off
    assert TODAY < entry.next_due_date <= TODAY + relativedelta(months=1)


# --- the invariant: an unrelated edit must not move the schedule ---------------

def test_editing_other_fields_leaves_the_schedule_alone(app, client, user, auth_headers):
    """The form posts every field on every save; only real changes reschedule."""
    scheduled = TODAY + relativedelta(months=7)
    with app.app_context():
        vehicle = _vehicle(user.id)
        tax = _tax(user.id, vehicle.id, recurring=True, recurrence_type='annual',
                   next_due_date=scheduled)
        tax_id = tax.id

    resp = client.put(
        f'{TAXES_URL}/{tax_id}',
        json={'notes': 'paid at the town hall', 'amount': 21.5,
              'recurring': True, 'recurrence_type': 'annual'},
        headers=auth_headers(user.id),
    )
    assert resp.status_code == 200, resp.data[:200]

    entry = _reload(app, tax_id)
    assert entry.next_due_date == scheduled, 'an unrelated edit moved the series'
    assert float(entry.amount) == 21.5
    assert entry.notes == 'paid at the town hall'


def test_non_recurring_edit_does_not_gain_a_schedule(app, client, user, auth_headers):
    with app.app_context():
        vehicle = _vehicle(user.id)
        tax = _tax(user.id, vehicle.id)
        tax_id = tax.id

    client.put(f'{TAXES_URL}/{tax_id}', json={'amount': 99},
               headers=auth_headers(user.id))

    entry = _reload(app, tax_id)
    assert entry.recurring is False
    assert entry.next_due_date is None


def test_cross_user_update_still_forbidden(app, client, user, auth_headers):
    """Ownership check is unchanged by the new block."""
    from app.models import User
    with app.app_context():
        vehicle = _vehicle(user.id)
        tax = _tax(user.id, vehicle.id, recurring=True, recurrence_type='monthly')
        tax_id = tax.id

        intruder = User(username='intruder', email='intruder@example.com',
                        is_active=True)
        intruder.set_password('StrongPass123!')
        db.session.add(intruder)
        db.session.commit()
        intruder_id = intruder.id

    resp = client.put(f'{TAXES_URL}/{tax_id}', json={'recurring': False},
                      headers=auth_headers(intruder_id))
    assert resp.status_code == 404
    assert _reload(app, tax_id).recurring is True

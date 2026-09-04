"""Tests for email_service.get_tax_alerts (R4-38 coverage, R4-23 bug).

The query's own comment said "use next_due_date for recurring, due_date
otherwise", but it filtered and reported `due_date` only. A recurring road tax
— the exact case the feature exists for — has a `due_date` in the past and its
next occurrence in `next_due_date`, so it never reached the digest: the user
was never reminded about the one tax that repeats.
"""

from datetime import timedelta

import pytest

from app import db
from app.models import TaxEntry, User, Vehicle
from app.services.email_service import get_tax_alerts
from app.utils.timeutils import utc_today


def today():
    """Read the date at CALL time, not at import.

    A module-level `TODAY = utc_today()` constant disagrees with the application's own
    `utc_today()` for any run that crosses UTC midnight — the suite takes ~9
    minutes, so that is a real and reproducible failure, not a theoretical one.
    """
    return utc_today()


@pytest.fixture
def fleet(app):
    with app.app_context():
        user = User(username='taxes', email='taxes@example.com', is_active=True,
                    currency='GBP')
        user.set_password('StrongPass123!')
        db.session.add(user)
        db.session.commit()
        vehicle = Vehicle(user_id=user.id, name='Golf')
        db.session.add(vehicle)
        db.session.commit()
        return user.id, vehicle.id


def _tax(user_id, vehicle_id, due_date=None, next_due_date=None, **kwargs):
    return TaxEntry(
        user_id=user_id, vehicle_id=vehicle_id, date=today(), amount=180,
        currency='GBP', title='Road tax', tax_type='road_tax',
        due_date=due_date, next_due_date=next_due_date, **kwargs
    )


def test_a_recurring_tax_is_alerted_on_its_next_occurrence(app, fleet):
    """R4-23: due_date is last year's; next_due_date is the one that matters."""
    user_id, vehicle_id = fleet
    with app.app_context():
        db.session.add(_tax(user_id, vehicle_id,
                            due_date=today() - timedelta(days=340),
                            next_due_date=today() + timedelta(days=10),
                            recurring=True, recurrence_type='annual'))
        db.session.commit()

        alerts = get_tax_alerts(user_id, days_ahead=30)

    assert len(alerts) == 1, alerts                       # was: 0
    assert alerts[0]['details'] == '10 days remaining'
    assert alerts[0]['due_date'] == (today() + timedelta(days=10)).strftime('%d %b %Y')


def test_a_one_off_tax_still_uses_its_due_date(app, fleet):
    user_id, vehicle_id = fleet
    with app.app_context():
        db.session.add(_tax(user_id, vehicle_id, due_date=today() + timedelta(days=20)))
        db.session.commit()

        alerts = get_tax_alerts(user_id, days_ahead=30)

    assert len(alerts) == 1
    assert alerts[0]['details'] == '20 days remaining'
    assert alerts[0]['vehicle'] == 'Golf'


@pytest.mark.parametrize('days_left, severity', [
    (3, 'urgent'),
    (7, 'urgent'),
    (10, 'warning'),
    (14, 'warning'),
    (20, 'info'),
])
def test_severity_bands(app, fleet, days_left, severity):
    user_id, vehicle_id = fleet
    with app.app_context():
        db.session.add(_tax(user_id, vehicle_id,
                            due_date=today() + timedelta(days=days_left)))
        db.session.commit()

        alerts = get_tax_alerts(user_id, days_ahead=30)

    assert alerts[0]['severity'] == severity


def test_a_tax_beyond_the_horizon_is_not_alerted(app, fleet):
    user_id, vehicle_id = fleet
    with app.app_context():
        db.session.add(_tax(user_id, vehicle_id, due_date=today() + timedelta(days=45)))
        db.session.add(_tax(user_id, vehicle_id,
                            due_date=today() - timedelta(days=400),
                            next_due_date=today() + timedelta(days=45),
                            recurring=True))
        db.session.commit()

        assert get_tax_alerts(user_id, days_ahead=30) == []


def test_an_overdue_tax_is_not_alerted(app, fleet):
    """The digest is about what is coming, not what was missed."""
    user_id, vehicle_id = fleet
    with app.app_context():
        db.session.add(_tax(user_id, vehicle_id, due_date=today() - timedelta(days=5)))
        db.session.commit()

        assert get_tax_alerts(user_id, days_ahead=30) == []


def test_next_due_date_wins_when_both_dates_are_in_the_horizon(app, fleet):
    user_id, vehicle_id = fleet
    with app.app_context():
        db.session.add(_tax(user_id, vehicle_id,
                            due_date=today() + timedelta(days=5),
                            next_due_date=today() + timedelta(days=25),
                            recurring=True))
        db.session.commit()

        alerts = get_tax_alerts(user_id, days_ahead=30)

    assert len(alerts) == 1
    assert alerts[0]['details'] == '25 days remaining'


def test_an_archived_vehicles_tax_is_not_alerted(app, fleet):
    user_id, vehicle_id = fleet
    with app.app_context():
        db.session.get(Vehicle, vehicle_id).archived = True
        db.session.add(_tax(user_id, vehicle_id,
                            next_due_date=today() + timedelta(days=10),
                            recurring=True))
        db.session.commit()

        assert get_tax_alerts(user_id, days_ahead=30) == []


def test_another_users_tax_is_never_alerted(app, fleet):
    user_id, vehicle_id = fleet
    with app.app_context():
        other = User(username='stranger', email='stranger@example.com',
                     is_active=True)
        other.set_password('StrongPass123!')
        db.session.add(other)
        db.session.commit()
        stranger_vehicle = Vehicle(user_id=other.id, name='Not Mine')
        db.session.add(stranger_vehicle)
        db.session.commit()
        db.session.add(_tax(other.id, stranger_vehicle.id,
                            due_date=today() + timedelta(days=10)))
        db.session.commit()

        assert get_tax_alerts(user_id, days_ahead=30) == []

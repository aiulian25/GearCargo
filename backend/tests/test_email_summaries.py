"""Regression tests for R4-02: the weekly and monthly e-mail summaries queried
columns that do not exist on the models, so every report e-mail has silently
failed since the feature shipped.

  * ``Vehicle.is_active``    -> the column is ``archived`` (models/vehicle.py)
  * ``FuelEntry.total_cost`` -> the column is ``total_price`` (models/fuel.py)
  * ``Entry.cost``           -> the column is ``amount``; ``cost`` exists only as
                               a ``to_dict`` alias (models/entry.py)

``send_weekly_reports`` / ``send_monthly_reports`` catch per user and log, so the
breakage was invisible in production. These tests call the summary builders
directly so a regression fails loudly.

Also pinned here:
  * totals are converted into the user's display currency before being summed
    (F1/F28), instead of adding EUR to GBP as if identical;
  * the monthly builder always returns a (summary, breakdown) TUPLE — its caller
    unpacks two values, so the "user vanished" path must not return a bare dict.
"""

from datetime import date, timedelta

import pytest

from app import db
from app.models import FuelEntry, ServiceEntry, User, Vehicle
from app.services.email_service import (
    get_user_monthly_summary,
    get_user_weekly_summary,
)
from app.utils.timeutils import utc_today


def _make_user(email, currency='GBP'):
    user = User(username=email.split('@')[0], email=email, is_active=True,
                currency=currency, distance_unit='km')
    user.set_password('StrongPass123!')
    db.session.add(user)
    db.session.commit()
    return user


def _seed(user, entry_currency='GBP', entry_date=None):
    """One active vehicle (with a 40 fuel + 100 service entry) and one ARCHIVED
    vehicle that must be excluded from every figure."""
    active = Vehicle(user_id=user.id, name='Daily', make='VW', model='Golf')
    archived = Vehicle(user_id=user.id, name='Old', make='Ford', model='Focus',
                       archived=True)
    db.session.add_all([active, archived])
    db.session.commit()

    today = entry_date or utc_today()
    db.session.add_all([
        FuelEntry(user_id=user.id, vehicle_id=active.id, date=today,
                  amount=40, total_price=40, liters=30, currency=entry_currency),
        ServiceEntry(user_id=user.id, vehicle_id=active.id, date=today,
                     amount=100, service_type='oil_change', currency=entry_currency),
        # On the archived vehicle — must never reach a total.
        FuelEntry(user_id=user.id, vehicle_id=archived.id, date=today,
                  amount=999, total_price=999, liters=99, currency=entry_currency),
    ])
    db.session.commit()
    return active, archived


def test_weekly_summary_uses_real_columns(app):
    with app.app_context():
        user = _make_user('weekly@example.com')
        _seed(user)

        summary = get_user_weekly_summary(user.id)

        assert summary['total_vehicles'] == 1        # archived one excluded
        assert summary['fuel_entries'] == 1
        assert summary['fuel_spent'] == '40.00'      # total_price, not total_cost
        assert summary['services'] == 1
        assert summary['distance_unit'] == 'km'
        # The template renders "{{ currency }}{{ amount }}" — it needs the SYMBOL,
        # the way the monthly summary already provided it.
        assert summary['currency'] == '£'


def test_monthly_summary_uses_real_columns(app):
    with app.app_context():
        user = _make_user('monthly@example.com')
        _seed(user)
        today = utc_today()

        summary, vehicles = get_user_monthly_summary(user.id, today.month, today.year)

        assert summary['fuel_total'] == '40.00'
        assert summary['services_total'] == '100.00'
        assert summary['grand_total'] == '140.00'
        assert summary['currency'] == '£'

        assert len(vehicles) == 1                    # archived one excluded
        assert vehicles[0]['name'] == 'Daily'
        assert vehicles[0]['fuel'] == '40.00'
        assert vehicles[0]['service'] == '100.00'
        assert vehicles[0]['total'] == '140.00'


def test_monthly_summary_always_returns_a_tuple(app):
    """send_monthly_reports does `summary, vehicles = ...` — a bare dict on the
    missing-user path would raise ValueError inside the scheduled job."""
    with app.app_context():
        today = utc_today()
        summary, vehicles = get_user_monthly_summary(999999, today.month, today.year)
        assert summary == {}
        assert vehicles == []


def test_totals_are_converted_into_the_display_currency(app, monkeypatch):
    """F1/F28: amounts logged in another currency are converted before summing,
    not added as if identical."""
    import app.services.currency as currency_module

    # EUR is the pivot base, so 1 EUR = 0.5 GBP under these rates.
    monkeypatch.setattr(currency_module, 'get_rates_cached', lambda _app: {'GBP': 0.5})

    with app.app_context():
        user = _make_user('fx@example.com', currency='GBP')
        _seed(user, entry_currency='EUR')
        today = utc_today()

        weekly = get_user_weekly_summary(user.id)
        assert weekly['fuel_spent'] == '20.00'       # 40 EUR -> 20 GBP

        summary, vehicles = get_user_monthly_summary(user.id, today.month, today.year)
        assert summary['fuel_total'] == '20.00'
        assert summary['services_total'] == '50.00'  # 100 EUR -> 50 GBP
        assert summary['grand_total'] == '70.00'
        assert vehicles[0]['total'] == '70.00'


def test_same_currency_skips_the_rate_lookup(app, monkeypatch):
    """The common single-currency case must not make the scheduled job reach for
    live FX rates (an outbound call it does not need)."""
    import app.services.currency as currency_module

    def _boom(_app):
        raise AssertionError('rates fetched for a single-currency summary')

    monkeypatch.setattr(currency_module, 'get_rates_cached', _boom)

    with app.app_context():
        user = _make_user('nofx@example.com', currency='GBP')
        _seed(user, entry_currency='GBP')
        assert get_user_weekly_summary(user.id)['fuel_spent'] == '40.00'


def test_unknown_currency_code_is_not_shown_as_pounds(app):
    """A code with no symbol in the table renders as the code, never as '£' —
    labelling a CHF total with a pound sign is worse than showing 'CHF'."""
    with app.app_context():
        user = _make_user('chf@example.com', currency='CHF')
        _seed(user, entry_currency='CHF')
        today = utc_today()

        assert get_user_weekly_summary(user.id)['currency'].strip() == 'CHF'
        summary, _ = get_user_monthly_summary(user.id, today.month, today.year)
        assert summary['currency'].strip() == 'CHF'


def test_monthly_report_job_renders_an_email_with_the_totals(app, monkeypatch):
    """End-to-end: the scheduled job unpacks the tuple, builds its insights and
    renders a report whose numbers and currency symbol reach the template.

    This is the user-visible failure — the job caught the exception per user and
    logged it, so no monthly report has ever been delivered.
    """
    from app.services import send_monthly_reports
    from app.services.email_service import EmailService

    sent = {}

    def _capture(to, subject, content_html, reply_to=None, unsubscribe_url=None):
        sent['to'] = to
        sent['subject'] = subject
        sent['html'] = content_html
        return True

    monkeypatch.setattr(EmailService, 'send_email', staticmethod(_capture))

    with app.app_context():
        app.config['MAIL_ENABLED'] = True
        user = _make_user('report-job@example.com')
        user.monthly_report_enabled = True
        # The job always reports on the month that just ENDED, so seed there.
        last_month_day = utc_today().replace(day=1) - timedelta(days=1)
        _seed(user, entry_date=last_month_day)
        db.session.commit()

        send_monthly_reports(app)

    assert sent, 'the monthly report job produced no e-mail'
    assert sent['to'] == 'report-job@example.com'
    assert '£140.00' in sent['html']      # grand total, with the currency symbol
    assert 'Daily' in sent['html']        # the per-vehicle breakdown row
    assert 'Old' not in sent['html']      # the archived vehicle is excluded

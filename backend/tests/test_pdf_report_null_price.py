"""Regression tests for R4-09: the PDF report crashed on any fuel entry with no
price or volume.

`f"{entry.liters:.2f}L @ {entry.price_per_liter:.2f} ..."` raises TypeError on
None, and both columns are nullable — the fuel PUT clears them
(`routes/fuel.py:434,437`) and the LubeLog importer writes 0/None
(`services/lubelog_import.py:406-408`). One such row anywhere in the period made
`POST /reports/pdf` 500 for the whole vehicle.

Also pinned here: the odometer column is labelled with the VEHICLE's own
distance unit (a miles car was reported in "km"), and a vehicle with no
make/model never renders as "None None".
"""

from datetime import timedelta

from app import db
from app.models import FuelEntry, ServiceEntry, User, Vehicle
from app.services.pdf_report_service import (
    generate_pdf_report,
    get_report_filename,
    get_vehicle_entries,
    get_period_dates,
)
from app.utils.timeutils import utc_today


def _user_with_vehicle(email, distance_unit='km', make='VW', model='Golf'):
    user = User(username=email.split('@')[0], email=email, is_active=True,
                currency='GBP')
    user.set_password('StrongPass123!')
    db.session.add(user)
    db.session.commit()
    vehicle = Vehicle(user_id=user.id, name='Daily', make=make, model=model,
                      distance_unit=distance_unit)
    db.session.add(vehicle)
    db.session.commit()
    return user, vehicle


def _fuel(user, vehicle, **overrides):
    entry = FuelEntry(user_id=user.id, vehicle_id=vehicle.id, date=utc_today(),
                      currency='GBP', **overrides)
    db.session.add(entry)
    db.session.commit()
    return entry


def _rows(vehicle, currency='GBP'):
    start, end, _label = get_period_dates('current_month')
    return get_vehicle_entries(vehicle, start, end, currency, None)


def test_pdf_renders_when_a_fill_up_has_no_volume_or_price(app):
    with app.app_context():
        user, vehicle = _user_with_vehicle('nullfuel@example.com')
        _fuel(user, vehicle, liters=None, price_per_liter=None,
              total_price=30, amount=30)

        buffer = generate_pdf_report(user, [vehicle], 'current_month')

    assert buffer.getvalue().startswith(b'%PDF')   # was: TypeError -> 500


def test_fuel_row_reads_cleanly_with_missing_values(app):
    with app.app_context():
        user, vehicle = _user_with_vehicle('partial@example.com')
        _fuel(user, vehicle, liters=None, price_per_liter=None,
              total_price=30, amount=30)
        _fuel(user, vehicle, liters=40, price_per_liter=None,
              total_price=60, amount=60)

        rows = _rows(vehicle)['fuel']

    assert rows[0]['description'] == '-'           # nothing known about the fill
    assert rows[1]['description'] == '40.00L'      # volume known, price not
    assert 'None' not in rows[0]['description'] + rows[1]['description']


def test_fuel_row_keeps_volume_and_price_when_both_are_present(app):
    """The normal case must be untouched by the null handling."""
    with app.app_context():
        user, vehicle = _user_with_vehicle('normal@example.com')
        _fuel(user, vehicle, liters=40, price_per_liter=1.5,
              total_price=60, amount=60)

        rows = _rows(vehicle)['fuel']

    assert rows[0]['description'] == '40.00L @ 1.50 GBP/L'
    assert rows[0]['amount'] == 60


def test_odometer_uses_the_vehicles_own_distance_unit(app):
    """A miles car was reported in km — wrong units on a maintenance record."""
    with app.app_context():
        user, vehicle = _user_with_vehicle('miles@example.com', distance_unit='miles')
        _fuel(user, vehicle, liters=10, price_per_liter=1.5, total_price=15,
              amount=15, odometer=52000)
        db.session.add(ServiceEntry(user_id=user.id, vehicle_id=vehicle.id,
                                    date=utc_today(), amount=100, odometer=52000,
                                    currency='GBP', service_type='oil_change'))
        db.session.commit()

        rows = _rows(vehicle)

    assert rows['fuel'][0]['odometer'] == '52,000 miles'
    assert rows['service'][0]['odometer'] == '52,000 miles'


def test_vehicle_label_never_renders_none(app):
    """`f"{make} {model}"` printed "None None" for a vehicle identified only by
    the name its owner gave it."""
    from app.services.pdf_report_service import vehicle_label

    with app.app_context():
        user, vehicle = _user_with_vehicle('nomake@example.com', make=None, model=None)
        _fuel(user, vehicle, liters=10, price_per_liter=1.5, total_price=15, amount=15)

        label = vehicle_label(vehicle)
        buffer = generate_pdf_report(user, [vehicle], 'current_month')
        filename = get_report_filename([vehicle], 'current_month')

    # Assert on the label itself — the raw PDF bytes contain ReportLab's own
    # structural tokens (e.g. "/PageMode /UseNone"), so grepping them is noise.
    assert label == 'Daily'
    assert 'None' not in filename
    assert 'Daily' in filename
    assert buffer.getvalue().startswith(b'%PDF')

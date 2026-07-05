"""Tests for the vehicle "spec sheet" exposed to the chat context.

_build_chat_context must surface the vehicle's identity/technical fields
(engine, transmission, drivetrain, colour, plate, VIN, year, purchase) and the
distinct fuel types actually logged, so the assistant can answer simple factual
questions like "what engine is my car?" / "what fuels do I use?".
"""

from datetime import date

from app import db
from app.models import Vehicle, FuelEntry
from app.routes.vehicles import _build_chat_context


def _vehicle(user_id, **kw):
    veh = Vehicle(user_id=user_id, name=kw.pop('name', 'Daily'),
                  make=kw.pop('make', 'Volkswagen'), model=kw.pop('model', 'Golf'),
                  year=kw.pop('year', 2019), fuel_type=kw.pop('fuel_type', 'diesel'),
                  current_mileage=kw.pop('mileage', 82000), **kw)
    db.session.add(veh)
    db.session.commit()
    return veh


def _fuel(user_id, vid, d, fuel_type, total=60.0):
    db.session.add(FuelEntry(user_id=user_id, vehicle_id=vid, type='fuel',
                             total_price=total, amount=total, date=d,
                             fuel_type=fuel_type))
    db.session.commit()


def test_spec_sheet_includes_identity_fields(app, user):
    with app.app_context():
        v = _vehicle(user.id, engine_cc=1598, transmission='manual',
                     drivetrain='fwd', color='blue', license_plate='AB12CDE',
                     vin='WVWZZZ1KZAW000001', purchase_date=date(2021, 5, 1),
                     purchase_price=15500)
        ctx = _build_chat_context(user, db.session.get(Vehicle, v.id))
        veh = ctx['vehicle']
        assert veh['year'] == 2019
        assert veh['engine_cc'] == 1598
        assert veh['transmission'] == 'manual'
        assert veh['drivetrain'] == 'fwd'
        assert veh['color'] == 'blue'
        assert veh['license_plate'] == 'AB12CDE'
        assert veh['vin'] == 'WVWZZZ1KZAW000001'
        assert veh['purchase_date'] == '2021-05-01'
        assert veh['purchase_price'] == 15500.0


def test_empty_spec_fields_are_dropped(app, user):
    with app.app_context():
        v = _vehicle(user.id, engine_cc=None, transmission=None, color=None)
        veh = _build_chat_context(user, db.session.get(Vehicle, v.id))['vehicle']
        # Absent optional fields are omitted (keeps the prompt lean); core stay.
        assert 'engine_cc' not in veh
        assert 'transmission' not in veh
        assert 'color' not in veh
        assert veh['make'] == 'Volkswagen' and veh['distance_unit'] == 'km'


def test_fuel_types_logged_is_distinct_sorted(app, user):
    with app.app_context():
        v = _vehicle(user.id)
        _fuel(user.id, v.id, date(2025, 1, 1), 'diesel')
        _fuel(user.id, v.id, date(2025, 2, 1), 'Diesel')   # case-folded dupe
        _fuel(user.id, v.id, date(2025, 3, 1), 'premium')
        _fuel(user.id, v.id, date(2025, 4, 1), None)        # ignored
        veh = _build_chat_context(user, db.session.get(Vehicle, v.id))['vehicle']
        assert veh['fuel_types_logged'] == ['diesel', 'premium']


def test_fuel_types_logged_absent_when_no_fuel(app, user):
    with app.app_context():
        v = _vehicle(user.id)
        veh = _build_chat_context(user, db.session.get(Vehicle, v.id))['vehicle']
        assert 'fuel_types_logged' not in veh

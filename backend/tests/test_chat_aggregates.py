"""Tests for the chat context aggregates (summaries + all-time rollups).

Covers the two user-approved follow-ups, both implemented as bounded, grouped
queries inside _build_chat_context (no tool-calling / RAG):
  1. `other_vehicles` — compact summaries of the user's OTHER owned vehicles,
     so cross-vehicle questions are answerable from any chat (isolation-safe:
     same owner).
  2. `all_time` — lifetime per-category / per-type counts + totals for
     "how many times / how much ever" questions.
"""

from datetime import date

from app import db
from app.models import Vehicle, ServiceEntry, RepairEntry, FuelEntry
from app.routes.vehicles import _build_chat_context


def _vehicle(user_id, name, **kw):
    veh = Vehicle(user_id=user_id, name=name, make=kw.pop('make', 'VW'),
                  model=kw.pop('model', 'Golf'), year=kw.pop('year', 2019),
                  fuel_type='diesel', current_mileage=kw.pop('mileage', 80000), **kw)
    db.session.add(veh)
    db.session.commit()
    return veh


def _service(user_id, vid, service_type, amount, d):
    db.session.add(ServiceEntry(user_id=user_id, vehicle_id=vid, type='service',
                                service_type=service_type, amount=amount, date=d))
    db.session.commit()


def _fuel(user_id, vid, total, d):
    db.session.add(FuelEntry(user_id=user_id, vehicle_id=vid, type='fuel',
                             total_price=total, amount=total, date=d))
    db.session.commit()


def test_all_time_rollups_count_and_total(app, user):
    with app.app_context():
        v = _vehicle(user.id, 'Primary')
        _service(user.id, v.id, 'oil_change', 80, date(2023, 1, 1))
        _service(user.id, v.id, 'oil_change', 90, date(2024, 1, 1))
        _service(user.id, v.id, 'brakes', 240, date(2025, 3, 1))
        db.session.add(RepairEntry(user_id=user.id, vehicle_id=v.id, type='repair',
                                   repair_type='alternator', amount=300, date=date(2024, 6, 1)))
        db.session.commit()

        ctx = _build_chat_context(user, db.session.get(Vehicle, v.id))
        at = ctx['all_time']
        # Per-category counts/totals.
        assert at['by_type']['service']['count'] == 3
        assert at['by_type']['service']['total'] == 410.0
        assert at['by_type']['repair']['count'] == 1
        # Per service-type rollup with last_date.
        oil = next(r for r in at['service_by_type'] if r['service_type'] == 'oil_change')
        assert oil['count'] == 2 and oil['total'] == 170.0 and oil['last_date'] == '2024-01-01'
        rep = at['repair_by_type'][0]
        assert rep['repair_type'] == 'alternator' and rep['total'] == 300.0


def test_other_vehicles_summaries_are_present_and_isolated(app, user):
    with app.app_context():
        from app.models import User
        primary = _vehicle(user.id, 'Primary', make='Nissan', model='Qashqai', year=2008)
        secondary = _vehicle(user.id, 'Second', make='BMW', model='320d', year=2015)
        _fuel(user.id, secondary.id, 60, date(2025, 5, 1))
        _service(user.id, secondary.id, 'mot', 55, date(2025, 4, 1))

        # A DIFFERENT user's vehicle must never leak into the summaries.
        other = User(username='intruder', email='x@example.com', is_active=True)
        other.set_password('StrongPass123!')
        db.session.add(other)
        db.session.commit()
        _vehicle(other.id, 'Foreign')

        ctx = _build_chat_context(user, db.session.get(Vehicle, primary.id))
        others = ctx['other_vehicles']
        names = {o['name'] for o in others}
        assert names == {'Second'}  # only the same owner's OTHER vehicle
        bmw = others[0]
        assert bmw['make'] == 'BMW' and bmw['fuel_total'] == 60.0
        assert bmw['spend_total'] == 115.0  # fuel 60 + service 55
        assert bmw['last_service_date'] == '2025-04-01'


def test_single_vehicle_has_empty_other_vehicles(app, user):
    with app.app_context():
        v = _vehicle(user.id, 'Only')
        ctx = _build_chat_context(user, db.session.get(Vehicle, v.id))
        assert ctx['other_vehicles'] == []

"""Tests for F31 — per-vehicle, unit-aware maintenance intervals."""

from datetime import date, timedelta

from app import db
from app.models import Vehicle, ServiceEntry
from app.routes.vehicles import _effective_intervals, MAINTENANCE_INTERVALS

TODAY = date.today()


def _mk_vehicle(app, user, **kwargs):
    with app.app_context():
        v = Vehicle(user_id=user.id, name='F150', make='Ford', model='F-150', **kwargs)
        db.session.add(v)
        db.session.commit()
        db.session.refresh(v)
        db.session.expunge(v)
        return v


def test_defaults_converted_for_miles_vehicles(app, user):
    v_km = _mk_vehicle(app, user, distance_unit='km')
    v_mi = _mk_vehicle(app, user, distance_unit='miles')
    with app.app_context():
        km = _effective_intervals(v_km)
        mi = _effective_intervals(v_mi)
    assert km['oil_change'] == 10000
    assert 6000 <= mi['oil_change'] <= 6500          # 10000 km ≈ 6213 mi → 6000
    assert mi['timing_belt'] == 62000                # 100000 km → 62137 → 62000
    assert set(mi) == set(MAINTENANCE_INTERVALS)


def test_overrides_respected_and_garbage_ignored(app, user):
    v = _mk_vehicle(app, user, distance_unit='km', maintenance_intervals={
        'oil_change': 20000,          # valid override (long-life diesel)
        'brake_pads': -5,             # non-positive → ignored
        'timing_belt': 9999999,       # over cap → ignored
        'flux_capacitor': 1000,       # unknown key → ignored
        'coolant': True,              # bool → ignored
    })
    with app.app_context():
        eff = _effective_intervals(v)
    assert eff['oil_change'] == 20000
    assert eff['brake_pads'] == MAINTENANCE_INTERVALS['brake_pads']
    assert eff['timing_belt'] == MAINTENANCE_INTERVALS['timing_belt']
    assert eff['coolant'] == MAINTENANCE_INTERVALS['coolant']
    assert 'flux_capacitor' not in eff


def test_put_validates_intervals(app, client, user, auth_headers):
    v = _mk_vehicle(app, user)

    ok = client.put(f'/api/vehicles/{v.id}', json={
        'maintenance_intervals': {'oil_change': 20000, 'tires': 40000},
    }, headers=auth_headers(user.id))
    assert ok.status_code == 200
    assert ok.get_json()['vehicle']['maintenance_intervals'] == {
        'oil_change': 20000, 'tires': 40000}

    assert client.put(f'/api/vehicles/{v.id}', json={
        'maintenance_intervals': {'flux_capacitor': 1000},
    }, headers=auth_headers(user.id)).status_code == 400
    assert client.put(f'/api/vehicles/{v.id}', json={
        'maintenance_intervals': {'oil_change': -1},
    }, headers=auth_headers(user.id)).status_code == 400
    assert client.put(f'/api/vehicles/{v.id}', json={
        'maintenance_intervals': 'not-a-dict',
    }, headers=auth_headers(user.id)).status_code == 400

    # null clears all overrides.
    cleared = client.put(f'/api/vehicles/{v.id}', json={'maintenance_intervals': None},
                         headers=auth_headers(user.id))
    assert cleared.get_json()['vehicle']['maintenance_intervals'] is None


def test_health_wear_uses_override_and_unit(app, client, user, auth_headers):
    """8000 since the oil change: overdue on the 10000-default at 80%→due_soon,
    but a 20000 override halves the wear percentage."""
    v = _mk_vehicle(app, user, distance_unit='km', current_mileage=58000)
    with app.app_context():
        db.session.add(ServiceEntry(user_id=user.id, vehicle_id=v.id, amount=100,
                                    date=TODAY - timedelta(days=120),
                                    service_type='oil_change', odometer=50000))
        db.session.commit()

    comp = client.get(f'/api/vehicles/{v.id}/health',
                      headers=auth_headers(user.id)).get_json()['components']['oil_change']
    assert comp['interval'] == 10000
    assert comp['distance_unit'] == 'km'
    assert comp['wear_percentage'] == 80
    assert comp['status'] == 'due_soon'

    client.put(f'/api/vehicles/{v.id}', json={
        'maintenance_intervals': {'oil_change': 20000},
    }, headers=auth_headers(user.id))

    comp = client.get(f'/api/vehicles/{v.id}/health',
                      headers=auth_headers(user.id)).get_json()['components']['oil_change']
    assert comp['interval'] == 20000
    assert comp['wear_percentage'] == 40
    assert comp['status'] == 'good'


def test_health_uses_miles_thresholds_for_miles_vehicle(app, client, user, auth_headers):
    """A miles vehicle 5000 mi past its oil change: vs the raw 10000-km default
    that's 50%, but vs the converted 6000-mi default it's 83% (due_soon)."""
    v = _mk_vehicle(app, user, distance_unit='miles', current_mileage=35000)
    with app.app_context():
        db.session.add(ServiceEntry(user_id=user.id, vehicle_id=v.id, amount=100,
                                    date=TODAY - timedelta(days=100),
                                    service_type='oil_change', odometer=30000))
        db.session.commit()

    comp = client.get(f'/api/vehicles/{v.id}/health',
                      headers=auth_headers(user.id)).get_json()['components']['oil_change']
    assert comp['interval'] == 6000
    assert comp['distance_unit'] == 'miles'
    assert comp['wear_percentage'] == 83
    assert comp['status'] == 'due_soon'

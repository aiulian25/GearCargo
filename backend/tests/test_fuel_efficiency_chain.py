"""Tests for F29 — full-to-full fuel efficiency + recalculation on edit/delete.

Before the fix every fill was scored against the previous entry regardless of
partial fills, and editing/deleting never touched the stored figures.
"""

from datetime import date, timedelta

from app import db
from app.models import Vehicle, FuelEntry

TODAY = date.today()


def _mk_vehicle(app, user):
    with app.app_context():
        v = Vehicle(user_id=user.id, name='Fabia', make='Skoda', model='Fabia',
                    current_mileage=50000)
        db.session.add(v)
        db.session.commit()
        db.session.refresh(v)
        return v.id


def _post_fuel(client, user, auth_headers, vid, *, days_ago, odometer, liters,
               full_tank=True):
    resp = client.post('/api/fuel', json={
        'vehicle_id': vid,
        'date': (TODAY - timedelta(days=days_ago)).isoformat(),
        'odometer': odometer,
        'liters': liters,
        'total_price': liters * 1.5,
        'full_tank': full_tank,
    }, headers=auth_headers(user.id))
    assert resp.status_code == 201
    return resp.get_json()['entry']['id']


def _eff(app, entry_id):
    with app.app_context():
        e = db.session.get(FuelEntry, entry_id)
        return e.fuel_efficiency, e.trip_distance


def test_partial_fill_rolls_into_next_full(app, client, user, auth_headers):
    vid = _mk_vehicle(app, user)
    first = _post_fuel(client, user, auth_headers, vid,
                       days_ago=20, odometer=50000, liters=40)
    partial = _post_fuel(client, user, auth_headers, vid,
                         days_ago=10, odometer=50500, liters=20, full_tank=False)
    second = _post_fuel(client, user, auth_headers, vid,
                        days_ago=1, odometer=51000, liters=30)

    assert _eff(app, first) == (None, None)      # no baseline before it
    assert _eff(app, partial) == (None, None)    # partials never score
    eff, dist = _eff(app, second)
    assert dist == 1000
    assert round(eff, 2) == 5.0                  # (30 + 20) / 1000 * 100


def test_editing_a_middle_entry_recomputes_the_next_full(app, client, user, auth_headers):
    vid = _mk_vehicle(app, user)
    _post_fuel(client, user, auth_headers, vid, days_ago=20, odometer=50000, liters=40)
    partial = _post_fuel(client, user, auth_headers, vid,
                         days_ago=10, odometer=50500, liters=20, full_tank=False)
    second = _post_fuel(client, user, auth_headers, vid,
                        days_ago=1, odometer=51000, liters=30)

    resp = client.put(f'/api/fuel/{partial}', json={'liters': 10},
                      headers=auth_headers(user.id))
    assert resp.status_code == 200

    eff, dist = _eff(app, second)
    assert round(eff, 2) == 4.0                  # (30 + 10) / 1000 * 100
    assert dist == 1000

    # Flipping the partial to a full tank splits the window in two.
    client.put(f'/api/fuel/{partial}', json={'full_tank': True},
               headers=auth_headers(user.id))
    eff_p, dist_p = _eff(app, partial)
    assert dist_p == 500 and round(eff_p, 2) == 2.0    # 10 / 500 * 100
    eff_s, dist_s = _eff(app, second)
    assert dist_s == 500 and round(eff_s, 2) == 6.0    # 30 / 500 * 100


def test_deleting_the_baseline_clears_dependent_efficiency(app, client, user, auth_headers):
    vid = _mk_vehicle(app, user)
    first = _post_fuel(client, user, auth_headers, vid,
                       days_ago=20, odometer=50000, liters=40)
    second = _post_fuel(client, user, auth_headers, vid,
                        days_ago=1, odometer=51000, liters=30)
    assert _eff(app, second)[1] == 1000

    resp = client.delete(f'/api/fuel/{first}', headers=auth_headers(user.id))
    assert resp.status_code == 200
    assert _eff(app, second) == (None, None)     # baseline gone


def test_stats_avg_consumption_uses_only_full_windows(app, client, user, auth_headers):
    vid = _mk_vehicle(app, user)
    _post_fuel(client, user, auth_headers, vid, days_ago=20, odometer=50000, liters=40)
    _post_fuel(client, user, auth_headers, vid,
               days_ago=10, odometer=50500, liters=20, full_tank=False)
    _post_fuel(client, user, auth_headers, vid, days_ago=1, odometer=51000, liters=30)

    stats = client.get(f'/api/vehicles/{vid}/stats',
                       headers=auth_headers(user.id)).get_json()
    # Exactly one efficiency point exists (the second full fill) → avg == 5.0.
    assert round(stats['avg_consumption'], 2) == 5.0


def test_full_fill_without_odometer_accumulates(app, client, user, auth_headers):
    vid = _mk_vehicle(app, user)
    _post_fuel(client, user, auth_headers, vid, days_ago=20, odometer=50000, liters=40)
    # Full tank but no odometer — can't anchor a window; litres roll forward.
    resp = client.post('/api/fuel', json={
        'vehicle_id': vid, 'date': (TODAY - timedelta(days=10)).isoformat(),
        'liters': 25, 'total_price': 40, 'full_tank': True,
    }, headers=auth_headers(user.id))
    assert resp.status_code == 201
    no_odo = resp.get_json()['entry']['id']
    second = _post_fuel(client, user, auth_headers, vid,
                        days_ago=1, odometer=51000, liters=30)

    assert _eff(app, no_odo) == (None, None)
    eff, dist = _eff(app, second)
    assert dist == 1000
    assert round(eff, 2) == 5.5                  # (30 + 25) / 1000 * 100

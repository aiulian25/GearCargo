"""GC-105: every fill says why it has, or lacks, a consumption figure."""
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import event

from app import db
from app.models import FuelEntry, Vehicle
from app.services.fuel_efficiency import (
    ODOMETER_REGRESSION_MESSAGE,
    FuelMeasurement,
    derive_efficiencies,
    measure_fills,
    measurement_statuses,
    recalculate_efficiencies,
)

# ((odometer, liters, full_tank), status, previous full-tank reading)
OBSERVATIONS = [
    ((None, 10, False), 'partial', None),
    ((100, 10, True), 'first_full_fill', None),
    ((None, 2, False), 'partial', 100),
    ((None, 3, True), 'odometer_missing', 100),
    ((200, 5, True), 'measured', 100),
    ((200, 10, True), 'odometer_regression', 200),
    ((100, 10, True), 'odometer_regression', 200),
    ((200, 10, True), 'measured', 100),
    ((250, None, False), 'volume_invalid', 200),
    ((None, 6, True), 'odometer_missing', None),
    ((300, 10, True), 'first_full_fill', None),
    ((-5, 10, True), 'odometer_invalid', 300),
    ((400, 10, True), 'first_full_fill', None),
    ((500, 10, True), 'measured', 400),
    ((None, 0, False), 'partial', 500),
    ((600, 0, True), 'measured', 500),
    ((700, 10, True), 'measured', 600),
]

# String litres, as unit_rebuild reads them, and an odd distance: reordering the
# arithmetic changes the resulting float in both units.
PIN_ROWS = [(1000, '37.50', True), (None, '7.77', False), (None, '0.10', False), (1611, '20.07', True)]

# Fills 4 (no litres) and 6 (negative odometer) seed the windows of fills 5 and 7.
MIXED_HISTORY = [(1000, 10, True), (None, 5, False), (1500, 10, True), (1600, None, True),
                 (1700, 10, True), (-5, 10, True), (1800, 10, True), (None, 4, False),
                 (1750, 10, True), (2250, 10, True)]

LONG_HISTORY = 2100
HISTORY_START = date(2024, 1, 1)


def fills(rows):
    return [SimpleNamespace(odometer=odometer, liters=liters, full_tank=full_tank)
            for odometer, liters, full_tank in rows]


def km_vehicle(user, name='Measured'):
    vehicle = Vehicle(user_id=user.id, name=name, distance_unit='km')
    db.session.add(vehicle)
    db.session.flush()
    return vehicle


def add_fills(user, vehicle, rows, first_day=HISTORY_START):
    """ORM rows outside a request, so legacy values the API rejects are allowed."""
    entries = [FuelEntry(user_id=user.id, vehicle_id=vehicle.id, date=first_day + timedelta(days=index),
                         odometer=odometer, liters=liters, full_tank=full_tank,
                         amount=20, total_price=20, currency='GBP')
               for index, (odometer, liters, full_tank) in enumerate(rows)]
    db.session.add_all(entries)
    db.session.flush()
    return entries


def post_fill(client, headers, vehicle, day, odometer, full_tank=True):
    response = client.post('/api/fuel', headers=headers, json={
        'vehicle_id': vehicle.id, 'date': (HISTORY_START + timedelta(days=day)).isoformat(),
        'odometer': odometer, 'liters': 40, 'total_price': 60, 'full_tank': full_tank})
    assert response.status_code == 201, response.json
    return response.json


def statuses_by_id(rows):
    return {row['id']: row['measurement_status'] for row in rows}


def test_every_fill_names_its_outcome():
    result = [measurement for _, measurement in measure_fills(fills(row for row, _, _ in OBSERVATIONS), 'km')]
    assert [measurement.status for measurement in result] == [status for _, status, _ in OBSERVATIONS]
    assert [measurement.previous_odometer for measurement in result] == [previous for _, _, previous in OBSERVATIONS]
    assert [measurement.distance for measurement in result] == [
        None, None, None, None, 100, None, None, 100, None, None, None, None, None, 100, None, 100, 100]
    assert all(measurement.efficiency is None for measurement in result if measurement.status != 'measured')
    # Litres logged before any full tank are never counted (the first figure would
    # be 20.0), and zero litres are a measurement, not a missing volume.
    assert [measurement.efficiency for measurement in result if measurement.status == 'measured'] == (
        pytest.approx([10.0, 10.0, 10.0, 0.0, 10.0]))


def test_unknown_distance_unit_keeps_the_distance_without_a_figure():
    _, measurement = list(measure_fills(fills([(100, 10, True), (200, 10, True)]), None))[-1]
    assert measurement == FuelMeasurement(100, None, 'distance_unit_unknown', 100)


@pytest.mark.parametrize('unit,factor', [('km', Decimal(1)), ('miles', Decimal('1.609344'))])
def test_derived_figures_stay_bit_identical(unit, factor):
    """unit_rebuild compares stored floats with != and bumps revisions on apply."""
    _, distance, efficiency = list(derive_efficiencies(fills(PIN_ROWS), unit))[-1]
    assert distance == 611
    assert efficiency == (20.07 + (0.0 + 7.77 + 0.1)) / float(Decimal(611) * factor) * 100


def test_regression_reanchors_and_drops_pending_partial_litres():
    rows = [(1000, 40, True), (None, 20, False), (900, 30, True), (1400, 40, True)]
    result = [measurement for _, measurement in measure_fills(fills(rows), 'km')]
    assert [measurement.status for measurement in result] == [
        'first_full_fill', 'partial', 'odometer_regression', 'measured']
    assert [measurement.previous_odometer for measurement in result] == [None, 1000, 1000, 900]
    assert result[-1].efficiency == 8.0  # Keeping the 20 partial litres would give 12.0.


def test_recalculation_reports_only_the_requested_fills(app, user):
    vehicle = km_vehicle(user)
    _, second, third = add_fills(user, vehicle, [(1000, 10, True), (1500, 10, True), (1400, 10, True)])
    assert recalculate_efficiencies(vehicle.id, user.id, positions=[(third.date, third.id)]) == {
        third.id: FuelMeasurement(None, None, 'odometer_regression', 1500)}
    measurements = recalculate_efficiencies(vehicle.id, user.id, positions=[(second.date, second.id)])
    assert list(measurements) == [second.id]
    assert (measurements[second.id].status, measurements[second.id].previous_odometer,
            measurements[second.id].distance) == ('measured', 1000, 500)
    assert measurements[second.id].efficiency == pytest.approx(2.0)
    assert recalculate_efficiencies(vehicle.id, user.id) == {}


def test_window_walks_and_reads_agree_with_the_full_walk(app, user):
    vehicle = km_vehicle(user)
    entries = add_fills(user, vehicle, MIXED_HISTORY)
    full_walk = {entry.id: measurement for entry, measurement in measure_fills(entries, 'km')}
    assert [full_walk[entry.id].status for entry in entries] == [
        'first_full_fill', 'partial', 'measured', 'volume_invalid', 'first_full_fill',
        'odometer_invalid', 'first_full_fill', 'partial', 'odometer_regression', 'measured']
    statuses = measurement_statuses(user.id, [vehicle.id])
    for entry in entries:
        window = recalculate_efficiencies(vehicle.id, user.id, positions=[(entry.date, entry.id)])
        assert window == {entry.id: full_walk[entry.id]}, entry.odometer
        assert statuses[entry.id] == full_walk[entry.id].status, entry.odometer


def test_create_warns_about_a_lower_reading_without_rejecting_it(client, user, auth_headers):
    vehicle = km_vehicle(user)
    db.session.commit()
    headers = auth_headers(user.id)
    first = post_fill(client, headers, vehicle, 1, 50000)
    assert (first['warnings'], first['entry']['measurement_status']) == ([], 'first_full_fill')
    second = post_fill(client, headers, vehicle, 2, 51000)
    assert (second['warnings'], second['entry']['measurement_status']) == ([], 'measured')
    typo = post_fill(client, headers, vehicle, 3, 5100)
    assert typo['warnings'] == [{'code': 'odometer_regression', 'previous': 51000,
                                 'message': ODOMETER_REGRESSION_MESSAGE.format(previous=51000)}]
    assert typo['entry']['measurement_status'] == 'odometer_regression'
    assert db.session.get(FuelEntry, typo['entry']['id']).odometer == 5100
    partial = post_fill(client, headers, vehicle, 4, 4000, full_tank=False)
    assert (partial['warnings'], partial['entry']['measurement_status']) == ([], 'partial')


def test_update_reports_and_clears_the_warning(client, user, auth_headers):
    vehicle = km_vehicle(user)
    db.session.commit()
    headers = auth_headers(user.id)
    post_fill(client, headers, vehicle, 1, 50000)
    post_fill(client, headers, vehicle, 2, 51000)
    typo = post_fill(client, headers, vehicle, 3, 5100)['entry']
    fixed = client.put(f"/api/fuel/{typo['id']}", headers=headers, json={'odometer': 51500})
    assert fixed.status_code == 200, fixed.json
    assert (fixed.json['warnings'], fixed.json['entry']['measurement_status']) == ([], 'measured')
    equal = client.put(f"/api/fuel/{typo['id']}", headers=headers, json={'odometer': 51000})
    assert equal.status_code == 200, equal.json
    assert [(warning['code'], warning['previous']) for warning in equal.json['warnings']] == [
        ('odometer_regression', 51000)]


def two_vehicle_history(user):
    first_vehicle, second_vehicle = km_vehicle(user, 'A'), km_vehicle(user, 'B')
    first_fill, second_fill = add_fills(user, first_vehicle, [(50000, 40, True), (51000, 40, True)])
    (other_fill,) = add_fills(user, second_vehicle, [(100, 40, True)], first_day=HISTORY_START + timedelta(days=2))
    ids = first_vehicle.id, first_fill.id, second_fill.id, other_fill.id
    db.session.commit()
    return ids


def test_reads_measure_each_vehicle_against_its_own_history(client, user, auth_headers):
    vehicle_id, first_fill, second_fill, other_fill = two_vehicle_history(user)
    headers = auth_headers(user.id)
    listed = client.get('/api/fuel', headers=headers).json['entries']
    assert statuses_by_id(listed) == {first_fill: 'first_full_fill', second_fill: 'measured',
                                      other_fill: 'first_full_fill'}
    filtered = client.get(f'/api/fuel?vehicle_id={vehicle_id}', headers=headers).json['entries']
    assert statuses_by_id(filtered) == {first_fill: 'first_full_fill', second_fill: 'measured'}
    assert client.get(f'/api/fuel/{second_fill}', headers=headers).json['measurement_status'] == 'measured'


def test_status_read_is_one_query_however_many_vehicles_are_listed(app, client, user, auth_headers):
    vehicle_id = two_vehicle_history(user)[0]
    headers = auth_headers(user.id)
    statements = []

    def count(connection, cursor, statement, parameters, context, executemany):
        # The first request also reloads the expired user; only fuel reads matter here.
        if 'fuel_entries' in statement:
            statements.append(statement)

    counts = []
    event.listen(db.engine, 'before_cursor_execute', count)
    try:
        for url in (f'/api/fuel?vehicle_id={vehicle_id}&per_page=20', '/api/fuel?per_page=20'):
            statements.clear()
            assert client.get(url, headers=headers).status_code == 200
            counts.append(len(statements))
    finally:
        event.remove(db.engine, 'before_cursor_execute', count)
    assert counts[0] == counts[1]


def test_status_depends_on_an_anchor_far_back(client, user, auth_headers):
    vehicle = km_vehicle(user)
    add_fills(user, vehicle, [(1000 + index, 1, index in (0, LONG_HISTORY - 1)) for index in range(LONG_HISTORY)])
    db.session.commit()
    latest = client.get(f'/api/fuel?vehicle_id={vehicle.id}&per_page=1', headers=auth_headers(user.id)).json
    assert [(row['odometer'], row['measurement_status']) for row in latest['entries']] == [
        (1000 + LONG_HISTORY - 1, 'measured')]


def test_vehicle_fuel_table_names_each_outcome(client, user, auth_headers):
    vehicle = km_vehicle(user)
    first_fill, second_fill, typo = add_fills(user, vehicle, [(50000, 40, True), (51000, 40, True), (5100, 40, True)])
    db.session.commit()
    page = client.get(f'/api/vehicles/{vehicle.id}/expense-records',
                      query_string={'category': 'fuel', 'year': HISTORY_START.year},
                      headers=auth_headers(user.id)).json
    assert statuses_by_id(page['records']) == {first_fill.id: 'first_full_fill', second_fill.id: 'measured',
                                               typo.id: 'odometer_regression'}

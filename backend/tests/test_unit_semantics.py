"""GC-015: source measurements retain units; all consumption is L/100km."""
import json
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import update

from app import db
from app.models import Vehicle, FuelEntry, Reminder
from app.services.fuel_efficiency import derive_efficiencies, recalculate_efficiencies
from app.utils.units import convert_odometer, distance_to_km


def make_vehicle(user, unit='miles', **kwargs):
    vehicle = Vehicle(user_id=user.id, name='Unit fixture', distance_unit=unit, **kwargs)
    db.session.add(vehicle)
    db.session.flush()
    return vehicle


def make_fill(user, vehicle, odo, liters, day=1, full=True, **kwargs):
    entry = FuelEntry(user_id=user.id, vehicle_id=vehicle.id, date=date(2026, 1, day),
                      odometer=odo, liters=liters, full_tank=full, amount=20,
                      total_price=20, currency='GBP', **kwargs)
    db.session.add(entry)
    db.session.flush()
    return entry


@pytest.mark.parametrize('unit,factor', [('km', 1), ('miles', 1.609344), ('mi', 1.609344)])
def test_full_partial_full_and_weighted_stats(app, client, user, auth_headers, unit, factor):
    vehicle = make_vehicle(user, unit)
    fills = [make_fill(user, vehicle, 0, 10), make_fill(user, vehicle, 40, 5, 2, False),
             make_fill(user, vehicle, 100, 5, 3), make_fill(user, vehicle, 400, 15, 4)]
    recalculate_efficiencies(vehicle.id, user.id)
    db.session.commit()
    assert [(f.trip_distance, f.fuel_efficiency) for f in fills[:2]] == [(None, None)] * 2
    assert fills[2].trip_distance == 100
    assert fills[2].fuel_efficiency == pytest.approx(10 / factor)
    assert fills[3].fuel_efficiency == pytest.approx(5 / factor)
    headers = auth_headers(user.id)
    stats = client.get(f'/api/vehicles/{vehicle.id}/stats', headers=headers).json
    assert stats['fuel_economy_unit'] == 'L/100km'
    assert stats['avg_consumption'] == pytest.approx(6.25 / factor, abs=.01)
    fleet = client.get('/api/fuel/stats', headers=headers).json
    assert fleet['efficiency_unit'] == 'L/100km'
    assert fleet['avg_efficiency'] == pytest.approx(6.25 / factor)


def test_mixed_fleet_weights_canonical_distance(app, client, user, auth_headers):
    for unit, liters in [('km', 10), ('miles', 20)]:
        vehicle = make_vehicle(user, unit)
        make_fill(user, vehicle, 0, 1)
        make_fill(user, vehicle, 100, liters, 2)
        recalculate_efficiencies(vehicle.id, user.id)
    db.session.commit()
    result = client.get('/api/fuel/stats', headers=auth_headers(user.id))
    assert result.status_code == 200
    assert result.json['avg_efficiency'] == pytest.approx(30 / 260.9344 * 100)


@pytest.mark.parametrize('unit,factor', [('km', 1), ('miles', 1.609344)])
def test_missing_equal_decreasing_and_invalid_observations(unit, factor):
    inputs = [(100, 10, True), (None, 2, False), (None, 3, True), (200, 5, True),
              (200, 10, True), (100, 10, True), (200, 10, True),
              (250, None, False), (300, 10, True), (400, 10, True)]
    result = list(derive_efficiencies([SimpleNamespace(odometer=o, liters=l, full_tank=f) for o, l, f in inputs], unit))
    assert [distance for _, distance, _ in result] == [None, None, None, 100, None, None, 100, None, None, 100]
    for index in [3, 6, 9]:
        assert result[index][2] == pytest.approx(10 / factor)
    assert list(derive_efficiencies([SimpleNamespace(odometer=o, liters=l, full_tank=f) for o, l, f in inputs], None))[-1][2] is None


def test_miles_edit_and_delete_rebuild_dependents(app, client, user, auth_headers):
    vehicle = make_vehicle(user)
    first = make_fill(user, vehicle, 1000, 10)
    partial = make_fill(user, vehicle, 1050, 5, 2, False)
    last = make_fill(user, vehicle, 1100, 5, 3)
    recalculate_efficiencies(vehicle.id, user.id)
    db.session.commit()
    headers = auth_headers(user.id)
    response = client.put(f'/api/fuel/{partial.id}', json={'liters': 10}, headers=headers)
    assert response.status_code == 200, response.json
    db.session.expire_all()
    assert last.fuel_efficiency == pytest.approx(15 / 160.9344 * 100)
    assert client.delete(f'/api/fuel/{first.id}', headers=headers).status_code == 200
    db.session.expire_all()
    assert last.trip_distance is None and last.fuel_efficiency is None


@pytest.mark.parametrize('history', ['mileage', 'fuel', 'threshold', 'reminder', 'trip'])
def test_unit_change_cannot_relabel_history(app, client, user, auth_headers, history):
    vehicle = make_vehicle(user, 'km', current_mileage=10000 if history == 'mileage' else 0,
                           maintenance_intervals={'oil_change': 5000} if history == 'threshold' else None,
                           avg_trip_distance=50 if history == 'trip' else None)
    if history == 'fuel':
        make_fill(user, vehicle, 0, 0)
    if history == 'reminder':
        db.session.add(Reminder(user_id=user.id, vehicle_id=vehicle.id, title='Oil', due_mileage=5000, due_date=date(2027, 1, 1)))
    db.session.commit()
    headers = auth_headers(user.id)
    response = client.put(f'/api/vehicles/{vehicle.id}', json={'name': 'Must rollback', 'distance_unit': 'miles'}, headers=headers)
    assert response.status_code == 409, response.json
    assert response.json['code'] == 'DISTANCE_UNIT_LOCKED'
    db.session.expire_all()
    assert vehicle.distance_unit == 'km' and vehicle.name == 'Unit fixture'
    assert client.get(f'/api/vehicles/{vehicle.id}', headers=headers).json['distance_unit_locked'] is True


def test_empty_vehicle_can_choose_units_and_alias_does_not_relabel(app, client, user, auth_headers):
    vehicle = make_vehicle(user, 'km', current_mileage=0)
    db.session.commit()
    headers = auth_headers(user.id)
    assert client.put(f'/api/vehicles/{vehicle.id}', json={'distance_unit': 'miles'}, headers=headers).status_code == 200
    make_fill(user, vehicle, 1000, 10)
    db.session.commit()
    assert client.put(f'/api/vehicles/{vehicle.id}', json={'distance_unit': 'mi'}, headers=headers).status_code == 200


def test_costs_and_due_mileage_keep_explicit_units(app, client, user, auth_headers):
    from app.models import ServiceEntry
    vehicle = make_vehicle(user, current_mileage=1100)
    make_fill(user, vehicle, 1000, 10)
    make_fill(user, vehicle, 1100, 10, 2)
    service = ServiceEntry(user_id=user.id, vehicle_id=vehicle.id, date=date(2026, 1, 1),
                           amount=0, currency='GBP', service_type='oil_change', odometer=1000,
                           next_due_mileage=1200, warranty_km=500)
    db.session.add(service)
    recalculate_efficiencies(vehicle.id, user.id)
    db.session.commit()
    headers = auth_headers(user.id)
    health = client.get(f'/api/vehicles/{vehicle.id}/health', headers=headers)
    assert health.status_code == 200, health.json
    assert health.json['cost_efficiency']['total_distance_km'] == pytest.approx(160.9344)
    assert health.json['cost_efficiency']['cost_per_km'] == pytest.approx(40 / 160.9344, abs=.001)
    analytics = client.get(f'/api/vehicles/{vehicle.id}/cost-analytics', headers=headers)
    assert analytics.status_code == 200, analytics.json
    assert analytics.json['distance_unit'] == 'miles'
    assert analytics.json['total_distance'] == 100
    assert analytics.json['cost_per_distance_lifetime'] == .4
    response = client.get(f'/api/services/{service.id}', headers=headers)
    assert response.json['next_due_mileage'] == 1200
    assert response.json['warranty_km'] == 500
    from app.services import process_due_services
    process_due_services(app)
    assert Reminder.query.filter_by(source_service_id=service.id).count() == 0
    vehicle.current_mileage = 1200
    db.session.commit()
    process_due_services(app)
    assert Reminder.query.filter_by(source_service_id=service.id).one().due_mileage == 1200


def classified():
    return dict(vehicles=[{'_id': 1, 'Year': 2020, 'Make': 'Ford', 'Model': 'Focus', 'LicensePlate': 'UNITS'}],
                gas_records=[{'VehicleId': 1, 'Cost': '50.00', 'Gallons': 10, 'Mileage': 100, 'Date': '2026-01-01'}],
                tax_records=[], service_records=[], collision_records=[], reminder_records=[])


@pytest.mark.parametrize('source,liters', [('us_gallons', '37.85'), ('imperial_gallons', '45.46'), ('liters', '10.00')])
def test_lubelog_converts_explicit_volume_preserves_cost_and_source(source, liters):
    from app.services.lubelog_import import map_to_gearcargo
    mapped = map_to_gearcargo(classified(), config={'UseMPG': True}, distance_unit='km', source_volume_unit=source)
    vehicle = mapped['vehicles'][0]
    entry = vehicle['fuel_entries'][0]
    assert entry['liters'] == Decimal(liters)
    assert entry['odometer'] == 161 and vehicle['current_mileage'] == 161
    assert entry['amount'] == entry['total_price'] == Decimal('50.00')
    assert entry['price_per_liter'] == round(Decimal('50.00') / Decimal(liters), 3)
    assert '100 miles' in entry['notes']
    if source != 'liters':
        assert 'Source fuel volume: 10' in entry['notes']
    assert mapped['unit_conversion']['source_volume_unit'] == source


def test_lubelog_rejects_ambiguous_units_and_converts_reminder_threshold():
    from app.services.lubelog_import import map_to_gearcargo
    from app.utils.entryparse import InvalidFieldError
    for config in [None, {'UseMPG': True}]:
        with pytest.raises(InvalidFieldError, match='volume'):
            map_to_gearcargo(classified(), config=config)
    with pytest.raises(InvalidFieldError, match='odometer'):
        map_to_gearcargo(classified(), source_volume_unit='liters')
    data = classified()
    data['reminder_records'] = [{'VehicleId': 1, 'Mileage': 1000, 'Description': 'Oil', 'Date': '2026-02-01'}]
    mapped = map_to_gearcargo(data, source_distance_unit='miles', source_volume_unit='us_gallons', distance_unit='km')
    assert mapped['reminders'][0]['due_mileage'] == 1609
    assert '1000 miles' in mapped['reminders'][0]['description']


def test_real_lubelog_import_converts_and_rebuilds(app, user):
    from test_lubelog_import import _lubelog_zip
    from app.services.lubelog_import import import_lubelog_to_gearcargo
    data = classified()
    archive = _lubelog_zip([data['vehicles'][0],
                           {**data['gas_records'][0], '_id': 1, 'Date': date(2026, 1, 1).isoformat(), 'IsFillToFull': True},
                           {**data['gas_records'][0], '_id': 2, 'Date': date(2026, 1, 2).isoformat(), 'Mileage': 200, 'IsFillToFull': True}])
    result = import_lubelog_to_gearcargo(user, archive, distance_unit='miles', source_distance_unit='miles', source_volume_unit='us_gallons')
    assert not result.get('error'), result
    entries = FuelEntry.query.order_by(FuelEntry.date).all()
    assert len(entries) == 2
    assert entries[1].liters == Decimal('37.85')
    assert entries[1].trip_distance == 100
    assert entries[1].fuel_efficiency == pytest.approx(37.85 / 160.9344 * 100)


def test_import_merge_refuses_different_vehicle_units(app, user):
    from app.services.backup_schema import prepare_backup, import_records, BackupSchemaError, export_user_data
    vehicle = make_vehicle(user, 'km', license_plate='UNITS')
    make_fill(user, vehicle, 100, 10)
    db.session.commit()
    payload = export_user_data(user)
    payload['vehicles'][0]['distance_unit'] = 'miles'
    with pytest.raises(BackupSchemaError, match='distance units'):
        import_records(user, prepare_backup(payload), 'merge', {}, {})
    db.session.rollback()
    assert Vehicle.query.one().distance_unit == 'km'
    assert FuelEntry.query.count() == 1


@pytest.mark.parametrize('value', [0, 1, 100, 10000, 1234567])
def test_odometer_roundtrip_has_only_storage_precision_loss(value):
    km = convert_odometer(value, 'miles', 'km')
    assert convert_odometer(km, 'km', 'miles') == value
    mi = convert_odometer(value, 'km', 'miles')
    assert abs(convert_odometer(mi, 'miles', 'km') - value) <= 1
    assert distance_to_km(value, 'mi') == Decimal(value) * Decimal('1.609344')


def test_repeated_notes_only_api_saves_preserve_sources_and_zero(app, client, user, auth_headers):
    vehicle = make_vehicle(user)
    entry = make_fill(user, vehicle, 0, Decimal('37.85'), price_per_liter=Decimal('-1.321'))
    db.session.commit()
    headers = auth_headers(user.id)
    for n in range(5):
        response = client.put(f'/api/fuel/{entry.id}', json={'notes': f'Note {n}'}, headers=headers)
        assert response.status_code == 200, response.json
        db.session.expire_all()
        assert (entry.odometer, entry.liters, entry.price_per_liter, entry.total_price, entry.amount) == (0, Decimal('37.85'), Decimal('-1.321'), 20, 20)
    entry.liters = entry.price_per_liter = entry.total_price = 0
    db.session.commit()
    data = client.get(f'/api/fuel/{entry.id}', headers=headers).json
    assert data['liters'] == data['price_per_liter'] == data['total_price'] == 0


def test_preview_apply_is_audited_source_preserving_and_idempotent(app, user, tmp_path):
    from app.services.unit_rebuild import create_rebuild_app
    vehicle = make_vehicle(user)
    first = make_fill(user, vehicle, 1000, 10)
    second = make_fill(user, vehicle, 1100, 10, 2, fuel_efficiency=10, trip_distance=100)
    vehicle.cost_per_km = .4
    vehicle.health_score = 30
    db.session.commit()
    source_timestamps = (first.updated_at, second.updated_at, vehicle.updated_at)
    original = (first.odometer, second.odometer, second.liters, second.total_price, second.amount, second.revision)
    cli = create_rebuild_app(app.config['SQLALCHEMY_DATABASE_URI']).test_cli_runner()
    preview = tmp_path / 'preview.json'
    result = cli.invoke(args=['rebuild-unit-metrics', '--output', str(preview)])
    assert result.exit_code == 0, result.output
    report = json.loads(preview.read_text())
    assert report['changes'][0]['before']['fuel_efficiency'] == 10
    assert report['cache_invalidations'][0]['before']['cost_per_km'] == .4
    db.session.expire_all()
    assert second.fuel_efficiency == 10 and second.revision == original[-1]
    applied = tmp_path / 'applied.json'
    result = cli.invoke(args=['rebuild-unit-metrics', '--apply', '--preview', str(preview), '--output', str(applied)])
    assert result.exit_code == 0, result.output
    db.session.expire_all()
    assert second.fuel_efficiency == pytest.approx(10 / 160.9344 * 100)
    assert (first.odometer, second.odometer, second.liters, second.total_price, second.amount) == original[:-1]
    assert second.revision == original[-1] + 1 and vehicle.cost_per_km is None
    assert vehicle.health_score is None
    assert (first.updated_at, second.updated_at, vehicle.updated_at) == source_timestamps
    assert json.loads(applied.read_text())['applied'] is True
    fresh = tmp_path / 'fresh.json'
    assert cli.invoke(args=['rebuild-unit-metrics', '--output', str(fresh)]).exit_code == 0
    assert json.loads(fresh.read_text())['changes'] == []
    assert json.loads(fresh.read_text())['cache_invalidations'] == []
    stale = cli.invoke(args=['rebuild-unit-metrics', '--apply', '--preview', str(preview), '--output', str(tmp_path / 'stale.json')])
    assert stale.exit_code != 0 and 'fresh preview' in stale.output


def test_rebuild_failure_rolls_back_and_preserves_existing_reports(app, user, tmp_path, monkeypatch):
    from app.services import unit_rebuild
    vehicle = make_vehicle(user)
    make_fill(user, vehicle, 1000, 10)
    last = make_fill(user, vehicle, 1100, 10, 2, fuel_efficiency=10, trip_distance=100)
    db.session.commit()
    cli = unit_rebuild.create_rebuild_app(app.config['SQLALCHEMY_DATABASE_URI']).test_cli_runner()
    preview, audit = tmp_path / 'preview.json', tmp_path / 'audit.json'
    assert cli.invoke(args=['rebuild-unit-metrics', '--output', str(preview)]).exit_code == 0
    def fail(*args):
        raise OSError('simulated full disk')
    monkeypatch.setattr(unit_rebuild, '_write_report', fail)
    result = cli.invoke(args=['rebuild-unit-metrics', '--apply', '--preview', str(preview), '--output', str(audit)])
    assert result.exit_code != 0 and not audit.exists()
    db.session.expire_all()
    assert last.fuel_efficiency == 10
    previous = preview.read_bytes()
    result = cli.invoke(args=['rebuild-unit-metrics', '--output', str(preview)])
    assert result.exit_code != 0 and preview.read_bytes() == previous


def test_read_only_rebuild_factory_does_not_start_jobs(app, monkeypatch):
    import app as application
    from app.services.unit_rebuild import create_rebuild_app
    def forbidden(*args, **kwargs):
        pytest.fail('Ordinary startup must not run during a preview')
    monkeypatch.setattr(application, 'create_app', forbidden)
    scan = create_rebuild_app(app.config['SQLALCHEMY_DATABASE_URI'])
    assert 'rebuild-unit-metrics' in scan.cli.commands


def test_lubelog_merge_unit_conflict_is_preflighted(app, user):
    from test_lubelog_import import _lubelog_zip
    from app.services.lubelog_import import import_lubelog_to_gearcargo
    make_vehicle(user, 'km', license_plate='UNITS')
    db.session.commit()
    data = classified()
    archive = _lubelog_zip([data['vehicles'][0], {**data['gas_records'][0], '_id': 1, 'IsFillToFull': True}])
    from app.utils.entryparse import InvalidFieldError
    with pytest.raises(InvalidFieldError) as error:
        import_lubelog_to_gearcargo(user, archive, distance_unit='miles', source_distance_unit='miles', source_volume_unit='us_gallons')
    assert error.value.message_key == 'backup.distanceUnitMismatch'
    assert Vehicle.query.count() == 1 and FuelEntry.query.count() == 0


def test_backup_restore_rebuilds_derived_values_preserving_source(app, user):
    from app.services.backup_schema import prepare_backup, import_records, export_user_data
    from app.models import User
    vehicle = make_vehicle(user)
    make_fill(user, vehicle, 1000, 10)
    make_fill(user, vehicle, 1100, 10, 2, trip_distance=100, fuel_efficiency=10)
    db.session.commit()
    payload = export_user_data(user)
    target = User(username='unit_restore', email='unit_restore@example.invalid')
    target.set_password('UnitFixturePassword123!')
    db.session.add(target)
    db.session.commit()
    import_records(target, prepare_backup(payload), 'merge', {}, {})
    db.session.commit()
    restored = FuelEntry.query.filter_by(user_id=target.id).order_by(FuelEntry.date).all()
    assert [row.odometer for row in restored] == [1000, 1100]
    assert restored[1].fuel_efficiency == pytest.approx(10 / 160.9344 * 100)
    assert restored[1].liters == Decimal('10.00') and restored[1].amount == 20


def test_rebuild_preview_flags_unknown_units(app, user):
    from app.services import unit_rebuild
    vehicle = make_vehicle(user)
    for day in [1, 2, 3]:
        make_fill(user, vehicle, day * 100, 10, day, trip_distance=100, fuel_efficiency=10)
    db.session.commit()
    db.session.execute(update(Vehicle).where(Vehicle.id == vehicle.id).values(distance_unit=None))
    db.session.commit()
    with db.engine.connect() as connection:
        report = unit_rebuild.preview_metrics(connection)
    assert 'Unknown distance unit' in report['review_required'][0]['reason']
    assert all(row['after']['fuel_efficiency'] is None for row in report['changes'])
    assert report['source_measurements_changed'] is False


def test_report_race_does_not_delete_another_report(app, user, tmp_path, monkeypatch):
    from app.services import unit_rebuild
    make_vehicle(user)
    db.session.commit()
    cli = unit_rebuild.create_rebuild_app(app.config['SQLALCHEMY_DATABASE_URI']).test_cli_runner()
    output = tmp_path / 'race.json'
    write_report = unit_rebuild._write_report
    def race(path, report):
        output.write_text('Other process audit')
        write_report(path, report)
    monkeypatch.setattr(unit_rebuild, '_write_report', race)
    result = cli.invoke(args=['rebuild-unit-metrics', '--output', str(output)])
    assert result.exit_code != 0 and output.read_text() == 'Other process audit'


def test_post_commit_report_failure_keeps_reconcilable_prepared_audit(app, user, tmp_path, monkeypatch):
    from app.services import unit_rebuild
    vehicle = make_vehicle(user)
    make_fill(user, vehicle, 1000, 10)
    last = make_fill(user, vehicle, 1100, 10, 2, fuel_efficiency=10, trip_distance=100)
    db.session.commit()
    cli = unit_rebuild.create_rebuild_app(app.config['SQLALCHEMY_DATABASE_URI']).test_cli_runner()
    preview, audit = tmp_path / 'preview.json', tmp_path / 'audit.json'
    assert cli.invoke(args=['rebuild-unit-metrics', '--output', str(preview)]).exit_code == 0
    def fail(*args):
        raise OSError('simulated final audit failure')
    monkeypatch.setattr(unit_rebuild, '_finalize_report', fail)
    result = cli.invoke(args=['rebuild-unit-metrics', '--apply', '--preview', str(preview), '--output', str(audit)])
    assert result.exit_code != 0 and 'Database committed' in result.output
    report = json.loads(audit.read_text())
    assert report['phase'] == 'prepared' and report['applied'] is False and report['changes']
    db.session.expire_all()
    assert last.fuel_efficiency == pytest.approx(10 / 160.9344 * 100)

"""GC-014: identical domain boundaries before API/CSV/archive persistence.

The same file runs on SQLite and PostgreSQL via TEST_DATABASE_URL.
"""
from datetime import date
from decimal import Decimal
import csv
import io
import json

import pytest
from sqlalchemy import text

from app import db
from app.models import FuelEntry, Vehicle
from app.utils.entryparse import InvalidFieldError, parse_amount, parse_optional_int


@pytest.mark.parametrize('value', ['NaN', 'Infinity', '-Infinity', '1e400', True, False, '1,25'])
def test_parser_rejects_nonfinite_boolean_and_comma_decimal(value):
    with pytest.raises(InvalidFieldError):
        parse_amount(value)


@pytest.mark.parametrize('value', [1.5, '1.5', True, 'NaN', '1e400', 2147483648])
def test_integer_never_truncates_or_overflows(value):
    with pytest.raises(InvalidFieldError):
        parse_optional_int(value)


def test_parser_preserves_decimal_and_optional_values():
    assert parse_amount('12.345') == Decimal('12.345')
    assert parse_amount('-12.34') == Decimal('-12.34')
    assert parse_optional_int('12.0') == 12
    assert parse_optional_int(0) == 0
    assert parse_optional_int(None) is None
    assert parse_optional_int('') is None


@pytest.fixture()
def garage(app, user, auth_headers):
    vehicle = Vehicle(user_id=user.id, name='Validation car', current_mileage=0)
    db.session.add(vehicle)
    db.session.commit()
    return user, vehicle.id, auth_headers(user.id)


BAD_FIELDS = [
    ('liters', 'NaN'), ('liters', 'Infinity'), ('liters', '1e400'),
    ('liters', True), ('liters', False), ('liters', -1), ('liters', '1,25'),
    ('liters', '1000000'), ('price_per_liter', '999.9995'),
    ('total_price', '100000000'), ('total_price', False),
    ('odometer', '3.5'), ('odometer', -1), ('odometer', 2147483648),
    ('station', 'x' * 101), ('station', {'name': 'invalid'}),
    ('fuel_type', 'unlisted'), ('currency', 'ZZZ'), ('currency', True),
    ('full_tank', 'false'), ('vehicle_id', True),
]


@pytest.mark.parametrize('field,value', BAD_FIELDS)
def test_fuel_create_and_update_reject_atomically(client, garage, field, value):
    user, vehicle_id, headers = garage
    payload = dict(vehicle_id=vehicle_id, liters='10', total_price='20', date='2026-01-02', odometer=0)
    result = client.post('/api/fuel', json={**payload, field: value}, headers=headers)
    assert result.status_code == 400, result.json
    assert result.json['message_key'].startswith('validation.')
    assert result.json['field'] == field
    assert FuelEntry.query.count() == 0
    entry = FuelEntry(user_id=user.id, vehicle_id=vehicle_id, date=date(2026, 1, 2),
                      liters=10, total_price=20, amount=20, odometer=0, station='original')
    db.session.add(entry)
    db.session.commit()
    result = client.put(f'/api/fuel/{entry.id}', json={'notes': 'must roll back', field: value}, headers=headers)
    assert result.status_code == 400, result.json
    db.session.expire_all()
    assert db.session.get(FuelEntry, entry.id).notes is None
    assert db.session.get(Vehicle, vehicle_id).current_mileage == 0


@pytest.mark.parametrize('field,value', [
    ('year', 2026.5), ('name', 'x' * 101), ('name', None), ('name', ''),
    ('engine_cc', True), ('current_mileage', -1), ('tank_capacity', '10000'),
    ('purchase_price', -1), ('monthly_budget', 'NaN'), ('distance_unit', 'yards'),
    ('transmission', 'teleport'), ('drivetrain', 'all'),
    ('maintenance_intervals', {'oil_change': 100.5}),
])
def test_vehicle_create_update_domains(client, garage, field, value):
    user, vehicle_id, headers = garage
    for method, path in [('post', '/api/vehicles'), ('put', f'/api/vehicles/{vehicle_id}')]:
        response = getattr(client, method)(path, headers=headers, json={'name': 'changed', field: value})
        assert response.status_code == 400, response.json
    db.session.expire_all()
    assert db.session.get(Vehicle, vehicle_id).name == 'Validation car'
    assert Vehicle.query.count() == 1


@pytest.mark.parametrize('field,value', [(f, v) for f, v in BAD_FIELDS if f not in {'vehicle_id', 'station'}] + [('station', 'x'*101)])
def test_csv_and_backup_reject_the_same_invalid_domains(garage, field, value):
    from app.services.csv_io import import_entries_csv
    from app.services.backup_schema import export_user_data, prepare_backup, BackupSchemaError
    user, vehicle_id, _ = garage
    cells = {'vehicle_id': vehicle_id, 'date': '2026-01-02', 'liters': '10', 'amount': '20', 'total_price': '20', field: value}
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=cells)
    writer.writeheader()
    # CSV's format explicitly represents booleans as true/false strings.
    writer.writerow({key: str(val).lower() if isinstance(val, bool) else val for key, val in cells.items()})
    result = import_entries_csv(user, 'fuel', stream.getvalue())
    if field == 'full_tank' and value == 'false':
        assert result['created'] == 1  # valid CSV boolean syntax; JSON requires boolean
        db.session.delete(FuelEntry.query.one())
        db.session.commit()
    else:
        assert result['error_count'] == 1 and result['created'] == 0, result
    data = export_user_data(user)
    data['vehicles'][0]['fuel_entries'] = [{
        'id': 999, 'vehicle_id': vehicle_id, 'date': '2026-01-02', 'liters': '10.00',
        'amount': '20.00', 'total_price': '20.00', field: value,
    }]
    with pytest.raises(BackupSchemaError):
        prepare_backup(data)
    assert FuelEntry.query.count() == 0


def test_decimal_rounding_refunds_zero_and_nullable_fields(client, garage):
    from app.services.csv_io import import_entries_csv
    from app.services.backup_schema import export_user_data, prepare_backup
    user, vehicle_id, headers = garage
    result = client.post('/api/fuel', headers=headers, json={
        'vehicle_id': vehicle_id, 'liters': '1.005', 'price_per_liter': '1.2345',
        'total_price': '-2.345', 'odometer': 0, 'currency': 'gbp', 'date': '2026-01-02',
    })
    assert result.status_code == 201, result.json
    entry = FuelEntry.query.one()
    assert (entry.liters, entry.price_per_liter, entry.total_price, entry.amount) == (
        Decimal('1.01'), Decimal('1.235'), Decimal('-2.35'), Decimal('-2.35'))
    assert entry.odometer == 0 and entry.currency == 'GBP'
    result = client.put(f'/api/fuel/{entry.id}', headers=headers, json={'odometer': '', 'price_per_liter': None})
    assert result.status_code == 200, result.json
    db.session.expire_all()
    assert entry.odometer is None and entry.price_per_liter is None
    result = import_entries_csv(user, 'fuel', f'vehicle_id,date,liters,amount,total_price,currency\n{vehicle_id},2026-01-03,1.005,-2.345,-2.345,GBP\n')
    assert result['created'] == 1, result
    imported = FuelEntry.query.order_by(FuelEntry.id.desc()).first()
    assert imported.liters == Decimal('1.01') and imported.amount == Decimal('-2.35')
    prepared = prepare_backup(export_user_data(user))
    assert prepared.records['fuel_entries'][0]['amount'] == Decimal('-2.35')


def test_computed_overflow_and_retry_receipt_are_rolled_back(client, garage):
    from app.models.mutation import MutationOperation
    user, vehicle_id, headers = garage
    headers = {**headers, 'Idempotency-Key': 'gc014-overflow-operation', 'X-GearCargo-Mutation-Version': '1'}
    payload = {'vehicle_id': vehicle_id, 'liters': '999999.99', 'price_per_liter': '999.999'}
    result = client.post('/api/fuel', headers=headers, json=payload)
    assert result.status_code == 400, result.json
    assert FuelEntry.query.count() == MutationOperation.query.count() == 0
    payload['liters'] = '1'
    result = client.post('/api/fuel', headers=headers, json=payload)
    assert result.status_code == 201, result.json
    replay = client.post('/api/fuel', headers=headers, json=payload)
    assert replay.status_code == 201 and replay.headers['Idempotent-Replay'] == 'true'
    assert FuelEntry.query.count() == 1


@pytest.mark.parametrize('field,value', [('Cost', 'NaN'), ('Cost', True), ('Cost', '1e400'), ('Gallons', -1), ('Mileage', 1.5)])
def test_lubelog_rejects_invalid_source_before_mapping(field, value):
    from app.services.lubelog_import import map_to_gearcargo
    classified = dict(vehicles=[{'_id': 1, 'Year': 2020, 'Make': 'Ford', 'Model': 'Focus'}],
                      gas_records=[{'VehicleId': 1, 'Cost': 10, 'Gallons': 5, 'Mileage': 10, field: value}],
                      tax_records=[], service_records=[], collision_records=[], reminder_records=[])
    with pytest.raises(InvalidFieldError):
        map_to_gearcargo(classified, config={'UseMPG': False})


def test_read_only_scan_reports_existing_bad_data(app, garage, tmp_path):
    from app.services.domain_scan import scan_records, create_scan_app
    user, vehicle_id, _ = garage
    fuel = FuelEntry(user_id=user.id, vehicle_id=vehicle_id, date=date(2026, 1, 2), liters=10)
    db.session.add(fuel)
    db.session.commit()
    # Deliberately bypass write validation to represent a pre-upgrade record.
    fuel_id = fuel.id
    db.session.execute(text("UPDATE fuel_entries SET liters='NaN' WHERE id=:id"), {'id': fuel_id})
    db.session.execute(text('UPDATE entries SET currency=NULL WHERE id=:id'), {'id': fuel_id})
    db.session.execute(text("UPDATE vehicles SET current_mileage=-5, fuel_type='invalid' WHERE id=:id"), {'id': vehicle_id})
    db.session.commit()
    before = db.session.execute(text('SELECT current_mileage, fuel_type FROM vehicles WHERE id=:id'), {'id': vehicle_id}).one()
    report = scan_records()
    assert report['read_only'] is True
    assert {'current_mileage', 'fuel_type', 'liters', 'currency'} <= {issue['field'] for issue in report['issues']}
    output = tmp_path / 'repair-report.json'
    scan_app = create_scan_app(app.config['SQLALCHEMY_DATABASE_URI'])
    result = scan_app.test_cli_runner().invoke(args=['validate-records', '--output', str(output)])
    assert result.exit_code == 0, result.output
    assert json.loads(output.read_text()) == report
    after = db.session.execute(text('SELECT current_mileage, fuel_type FROM vehicles WHERE id=:id'), {'id': vehicle_id}).one()
    assert before == after
    assert db.session.execute(text('SELECT CAST(liters AS TEXT) FROM fuel_entries WHERE id=:id'), {'id': fuel_id}).scalar() == 'NaN'
    assert db.session.execute(text('SELECT currency FROM entries WHERE id=:id'), {'id': fuel_id}).scalar() is None


def test_numeric_strings_are_normalized_before_foreign_key_queries(client, garage):
    _, vehicle_id, headers = garage
    result = client.post('/api/fuel', headers=headers, json={
        'vehicle_id': f'{vehicle_id}.0', 'liters': '10', 'odometer': '12.0', 'total_price': '20',
    })
    assert result.status_code == 201, result.json
    result = client.put(f'/api/vehicles/{vehicle_id}', headers=headers, json={'current_mileage': '15.0'})
    assert result.status_code == 200, result.json
    assert db.session.get(Vehicle, vehicle_id).current_mileage == 15


def test_invalid_historical_domains_can_be_exported_for_repair(app, garage):
    from app.routes.backup import create_backup_zip
    from app.services.backup_schema import prepare_backup, BackupSchemaError
    _, vehicle_id, _ = garage
    db.session.execute(text("UPDATE vehicles SET current_mileage=-1 WHERE id=:id"), {'id': vehicle_id})
    db.session.commit()
    archive, payload = create_backup_zip(garage[0], include_attachments=False)
    assert archive.getbuffer().nbytes and payload['vehicles'][0]['current_mileage'] == -1
    with pytest.raises(BackupSchemaError):
        prepare_backup(payload)


def test_zero_fuel_values_are_stored_as_zero(client, garage):
    _, vehicle_id, headers = garage
    result = client.post('/api/fuel', headers=headers, json={
        'vehicle_id': vehicle_id, 'liters': 0, 'price_per_liter': 0, 'total_price': 0, 'odometer': 0,
        'currency': ' gbp ',
    })
    assert result.status_code == 201, result.json
    entry = FuelEntry.query.one()
    assert (entry.liters, entry.price_per_liter, entry.total_price, entry.odometer) == (0, 0, 0, 0)
    result = client.put(f'/api/fuel/{entry.id}', headers=headers,
                        json={'liters': 0, 'price_per_liter': 0, 'total_price': 0})
    assert result.status_code == 200, result.json
    db.session.expire_all()
    assert (entry.liters, entry.price_per_liter, entry.total_price) == (0, 0, 0)


def test_lubelog_preserves_a_refund_with_a_signed_unit_price():
    from app.services.lubelog_import import map_to_gearcargo
    result = map_to_gearcargo(dict(
        vehicles=[{'_id': 1, 'Year': 2020, 'Make': 'Ford', 'Model': 'Focus'}],
        gas_records=[{'VehicleId': 1, 'Cost': '-10.25', 'Gallons': 5, 'Mileage': 0}],
        tax_records=[], service_records=[], collision_records=[], reminder_records=[],
    ), config={'UseMPG': False})
    entry = result['vehicles'][0]['fuel_entries'][0]
    assert entry['amount'] == entry['total_price'] == Decimal('-10.25')
    assert entry['price_per_liter'] == Decimal('-2.050') and entry['liters'] == Decimal('5.00')


def test_scan_cli_does_not_run_application_startup(app, monkeypatch):
    import app as application
    import threading
    from app.services import restore_transaction
    from app.services.domain_scan import create_scan_app

    def forbidden(*args, **kwargs):
        raise AssertionError('Read-only scan must not run application startup work')

    monkeypatch.setattr(application, 'create_app', forbidden)
    monkeypatch.setattr(application, 'init_default_admin', forbidden)
    monkeypatch.setattr(restore_transaction, 'recover_unfinished', forbidden)
    monkeypatch.setattr(threading.Thread, 'start', forbidden)
    scan_app = create_scan_app(app.config['SQLALCHEMY_DATABASE_URI'])
    result = scan_app.test_cli_runner().invoke(args=['validate-records'])
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report['read_only'] is True and report['scanned'] == 0


@pytest.mark.parametrize('empty', ['', None])
def test_parking_form_accepts_and_clears_optional_times(client, garage, empty):
    from app.models import ParkingEntry
    _, vehicle_id, headers = garage
    result = client.post('/api/parking', headers=headers, json={
        'vehicle_id': vehicle_id, 'date': '2026-01-02', 'amount': '3.50',
        'parking_type': 'hourly', 'currency': 'GBP', 'recurring': False,
        'start_time': empty, 'end_time': empty, 'permit_expires': '',
    })
    assert result.status_code == 201, result.json
    entry = ParkingEntry.query.one()
    assert entry.start_datetime is None and entry.end_datetime is None
    result = client.put(f'/api/parking/{entry.id}', headers=headers,
                        json={'start_time': '10:00', 'end_time': '11:30'})
    assert result.status_code == 200, result.json
    db.session.expire_all()
    assert entry.start_datetime.hour == 10 and entry.end_datetime.minute == 30
    result = client.put(f'/api/parking/{entry.id}', headers=headers,
                        json={'start_time': empty, 'end_time': empty})
    assert result.status_code == 200, result.json
    db.session.expire_all()
    assert entry.start_datetime is None and entry.end_datetime is None

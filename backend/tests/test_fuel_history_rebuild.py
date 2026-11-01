"""GC-034: complete fuel histories, bounded traversal and atomic repair."""
import json
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import event

from app import db
from app.models import FuelEntry, Vehicle
from app.services.fuel_efficiency import recalculate_efficiencies


def _history(user, count=2213, unit='km'):
    vehicle = Vehicle(user_id=user.id, name='Long fuel history', distance_unit=unit)
    db.session.add(vehicle)
    db.session.flush()
    entries = [FuelEntry(user_id=user.id, vehicle_id=vehicle.id,
                         date=date(2020, 1, 1) + timedelta(days=i // 3),
                         odometer=i * 100, liters=Decimal(5 + i % 7),
                         full_tank=i % 5 == 0 or i == count - 1,
                         total_price=20, amount=20, currency='GBP',
                         trip_distance=1, fuel_efficiency=999)
               for i in range(count)]
    if count > 1002:
        entries[500].odometer = None  # A full fill without a usable baseline.
        entries[1002].liters = None  # Unknown volume breaks the window.
    db.session.add_all(entries)
    db.session.flush()
    ids = [entry.id for entry in entries]
    db.session.commit()
    return vehicle.id, ids


def _rows(vehicle_id):
    return FuelEntry.query.filter_by(vehicle_id=vehicle_id).order_by(FuelEntry.date, FuelEntry.id).all()


def _reference(rows, unit='km'):
    """Independent endpoint calculation: look back from each full fill.

    Deliberately does not use production helpers or carry a running sum.
    """
    result = {}
    factor = Decimal('1.609344') if unit in ('mi', 'miles') else Decimal(1)
    for index, row in enumerate(rows):
        result[row.id] = (None, None)
        if not row.full_tank or row.odometer is None or row.liters is None:
            continue
        for prior in range(index - 1, -1, -1):
            anchor = rows[prior]
            if anchor.liters is None or anchor.liters < 0:
                break
            if anchor.full_tank and anchor.odometer is not None:
                distance = row.odometer - anchor.odometer
                if distance > 0:
                    volume = sum((item.liters for item in rows[prior + 1:index + 1]), Decimal(0))
                    result[row.id] = (distance, float(volume * 100 / (Decimal(distance) * factor)))
                break
    return result


def _assert_reference(vehicle_id, unit='km'):
    db.session.expire_all()
    rows = _rows(vehicle_id)
    expected = _reference(rows, unit)
    for row in rows:
        distance, efficiency = expected[row.id]
        assert row.trip_distance == distance, row.id
        if efficiency is None:
            assert row.fuel_efficiency is None, row.id
        else:
            assert row.fuel_efficiency == pytest.approx(efficiency), row.id


@pytest.mark.parametrize('unit', ['km', 'miles', 'mi'])
def test_complete_history_crosses_2000_and_partial_boundaries(app, user, unit):
    vehicle_id, ids = _history(user, unit=unit)
    recalculate_efficiencies(vehicle_id, user.id)
    db.session.commit()
    _assert_reference(vehicle_id, unit)
    assert db.session.get(FuelEntry, ids[-1]).fuel_efficiency != 999


def test_long_maintenance_preview_apply_preserves_sources_and_marks_completion(app, user, tmp_path):
    from app.services.unit_rebuild import create_rebuild_app
    vehicle_id, ids = _history(user, unit='miles')
    source = [(row.id, row.date, row.odometer, row.liters, row.amount, row.updated_at)
              for row in _rows(vehicle_id)]
    cli = create_rebuild_app(app.config['SQLALCHEMY_DATABASE_URI']).test_cli_runner()
    preview, audit = tmp_path / 'preview.json', tmp_path / 'applied.json'
    result = cli.invoke(args=['rebuild-unit-metrics', '--output', str(preview)])
    assert result.exit_code == 0, result.output
    proposed = json.loads(preview.read_text())
    assert not proposed['review_required']
    assert proposed['version'] == 2 and proposed['entry_count'] == len(ids)
    assert proposed['rebuild_scope'] == 'complete_fuel_history'
    assert ids[-1] in {row['entry_id'] for row in proposed['changes']}
    assert proposed['applied'] is False and proposed['phase'] == 'preview'
    result = cli.invoke(args=['rebuild-unit-metrics', '--apply', '--preview', str(preview), '--output', str(audit)])
    assert result.exit_code == 0, result.output
    completed = json.loads(audit.read_text())
    assert completed['applied'] is True and completed['phase'] == 'committed'
    _assert_reference(vehicle_id, 'miles')
    assert [(row.id, row.date, row.odometer, row.liters, row.amount, row.updated_at)
            for row in _rows(vehicle_id)] == source
    verification = tmp_path / 'verification.json'
    assert cli.invoke(args=['rebuild-unit-metrics', '--output', str(verification)]).exit_code == 0
    assert json.loads(verification.read_text())['changes'] == []


def test_full_walk_pages_are_bounded_and_interruption_rolls_every_page_back(app, user, monkeypatch):
    from app.services import fuel_efficiency
    vehicle_id, ids = _history(user)
    original = fuel_efficiency._batched_entries
    processed = []

    def interrupted(query):
        for row in original(query):
            processed.append(row.id)
            if len(processed) == 2050:
                raise RuntimeError('synthetic interruption after several flushed pages')
            yield row

    monkeypatch.setattr(fuel_efficiency, '_batched_entries', interrupted)
    with pytest.raises(RuntimeError, match='synthetic interruption'):
        recalculate_efficiencies(vehicle_id, user.id)
    db.session.rollback()
    assert len(processed) == 2050
    assert all(row.trip_distance == 1 and row.fuel_efficiency == 999 for row in _rows(vehicle_id))
    monkeypatch.setattr(fuel_efficiency, '_batched_entries', original)
    # Inspect actual SELECT bounds, not merely the eventual output count.
    statements = []
    def select_bound(connection, cursor, statement, parameters, context, many):
        if statement.lstrip().upper().startswith('SELECT') and 'JOIN fuel_entries' in statement:
            statements.append((statement, parameters))
    event.listen(db.engine, 'before_cursor_execute', select_bound)
    try:
        recalculate_efficiencies(vehicle_id, user.id)
        db.session.commit()
    finally:
        event.remove(db.engine, 'before_cursor_execute', select_bound)
    assert len(statements) > 8
    assert all('LIMIT' in statement for statement, _ in statements)
    assert all(fuel_efficiency.BATCH_SIZE in (parameters.values() if isinstance(parameters, dict) else parameters)
               for _, parameters in statements)
    _assert_reference(vehicle_id)


@pytest.mark.parametrize('operation', ['edit_partial', 'delete_partial', 'delete_full', 'move_full',
                                       'full_to_partial', 'clear_odometer', 'append'])
def test_api_repairs_only_affected_windows_in_long_history(app, client, user, auth_headers, operation):
    vehicle_id, ids = _history(user)
    recalculate_efficiencies(vehicle_id, user.id)
    db.session.commit()
    headers = auth_headers(user.id)
    loaded = []
    def loaded_entry(target, context):
        loaded.append(target.id)
    event.listen(FuelEntry, 'load', loaded_entry)
    try:
        if operation == 'edit_partial':
            response = client.put(f'/api/fuel/{ids[1999]}', headers=headers, json={'liters': 33})
        elif operation == 'delete_partial':
            response = client.delete(f'/api/fuel/{ids[1999]}', headers=headers)
        elif operation == 'delete_full':
            response = client.delete(f'/api/fuel/{ids[2000]}', headers=headers)
        elif operation == 'move_full':
            response = client.put(f'/api/fuel/{ids[2000]}', headers=headers,
                                  json={'date': '2020-01-02', 'odometer': 450})
        elif operation == 'full_to_partial':
            response = client.put(f'/api/fuel/{ids[2000]}', headers=headers, json={'full_tank': False})
        elif operation == 'clear_odometer':
            response = client.put(f'/api/fuel/{ids[2000]}', headers=headers, json={'odometer': None})
        else:
            response = client.post('/api/fuel', headers=headers, json={
                'vehicle_id': vehicle_id, 'date': '2023-01-01', 'odometer': 230000,
                'liters': 30, 'full_tank': True, 'total_price': 50})
        assert response.status_code == (201 if operation == 'append' else 200), response.json
    finally:
        event.remove(FuelEntry, 'load', loaded_entry)
    assert len(loaded) < 30, 'A single-record write must not load the full 2,000+ entry history'
    _assert_reference(vehicle_id)


def test_partial_window_itself_can_span_many_pages(app, user):
    vehicle_id, ids = _history(user)
    for row in _rows(vehicle_id):
        row.full_tank = row.id in (ids[0], ids[-1])
        row.liters = 1
        if row.id == ids[0]:
            row.trip_distance = row.fuel_efficiency = None
    db.session.commit()
    recalculate_efficiencies(vehicle_id, user.id, positions=[(db.session.get(FuelEntry, ids[1999]).date, ids[1999])])
    db.session.commit()
    _assert_reference(vehicle_id)


def test_failed_api_recalculation_rolls_back_source_edit(app, client, user, auth_headers, monkeypatch):
    from app.services import fuel_efficiency
    vehicle_id, ids = _history(user, count=12)
    recalculate_efficiencies(vehicle_id, user.id)
    db.session.commit()
    original_liters = db.session.get(FuelEntry, ids[6]).liters
    original = fuel_efficiency._batched_entries
    def interrupted(query):
        for index, row in enumerate(original(query)):
            if index == 2:
                raise RuntimeError('synthetic request interruption')
            yield row
    monkeypatch.setattr(fuel_efficiency, '_batched_entries', interrupted)
    with pytest.raises(RuntimeError, match='synthetic request interruption'):
        client.put(f'/api/fuel/{ids[6]}', headers=auth_headers(user.id), json={'liters': 99})
    db.session.expire_all()
    assert db.session.get(FuelEntry, ids[6]).liters == original_liters
    _assert_reference(vehicle_id)


def test_long_maintenance_interruption_and_old_preview_are_safe(app, user, tmp_path, monkeypatch):
    from app.services import unit_rebuild
    vehicle_id, ids = _history(user)
    cli = unit_rebuild.create_rebuild_app(app.config['SQLALCHEMY_DATABASE_URI']).test_cli_runner()
    preview = tmp_path / 'preview.json'
    assert cli.invoke(args=['rebuild-unit-metrics', '--output', str(preview)]).exit_code == 0
    # A GC-015 preview could have silently skipped this same source history;
    # its fingerprint alone must never authorize the new complete repair.
    old_report = json.loads(preview.read_text())
    old_report['version'] = 1
    old_preview = tmp_path / 'old-preview.json'
    old_preview.write_text(json.dumps(old_report))
    result = cli.invoke(args=['rebuild-unit-metrics', '--apply', '--preview', str(old_preview),
                             '--output', str(tmp_path / 'rejected.json')])
    assert result.exit_code != 0 and 'fresh preview' in result.output
    def fail_report(*args):
        raise OSError('synthetic full disk after all changes were prepared')
    monkeypatch.setattr(unit_rebuild, '_write_report', fail_report)
    result = cli.invoke(args=['rebuild-unit-metrics', '--apply', '--preview', str(preview),
                             '--output', str(tmp_path / 'interrupted.json')])
    assert result.exit_code != 0
    db.session.expire_all()
    assert all(row.trip_distance == 1 and row.fuel_efficiency == 999 for row in _rows(vehicle_id))
    assert not (tmp_path / 'interrupted.json').exists()


def test_history_index_migration_round_trip_preserves_records(app, user):
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect
    vehicle_id, ids = _history(user, count=3)
    before = [(row.id, row.odometer, row.liters, row.fuel_efficiency) for row in _rows(vehicle_id)]
    db.session.rollback()
    path = Path(__file__).parents[1] / 'migrations/versions/gc034_fuel_history_index.py'
    spec = importlib.util.spec_from_file_location('gc034_test_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with db.engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.downgrade()  # create_all already supplied the model index.
        assert not any(i['name'] == 'ix_entries_user_vehicle_date_id' for i in inspect(connection).get_indexes('entries'))
        migration.upgrade()
        index = next(i for i in inspect(connection).get_indexes('entries') if i['name'] == 'ix_entries_user_vehicle_date_id')
        assert index['column_names'] == ['user_id', 'vehicle_id', 'date', 'id'] and not index['unique']
    assert [(row.id, row.odometer, row.liters, row.fuel_efficiency) for row in _rows(vehicle_id)] == before


def test_long_backup_import_repairs_the_tail_and_preserves_source_measurements(app, user):
    from app.models import User
    from app.services.backup_schema import export_user_data, import_records, prepare_backup
    vehicle_id, ids = _history(user, count=2007, unit='miles')
    source = [(row.date, row.odometer, row.liters, row.amount, row.total_price,
               row.full_tank, row.created_at, row.updated_at) for row in _rows(vehicle_id)]
    payload = export_user_data(user)
    recipient = User(username='long_import', email='long_import@example.invalid', is_active=True)
    recipient.set_password('LongHistoryFixture123!')
    db.session.add(recipient)
    db.session.commit()
    import_records(recipient, prepare_backup(payload), 'merge', {}, {})
    db.session.commit()
    imported = Vehicle.query.filter_by(user_id=recipient.id).one()
    _assert_reference(imported.id, 'miles')
    assert [(row.date, row.odometer, row.liters, row.amount, row.total_price,
             row.full_tank, row.created_at, row.updated_at) for row in _rows(imported.id)] == source
    # An import for another owner never repairs/mutates the original history.
    assert all(row.fuel_efficiency == 999 for row in _rows(vehicle_id))

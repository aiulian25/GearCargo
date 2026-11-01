"""Preview/apply only derived fuel metrics; preserve every source measurement.

The CLI uses a minimal factory so preview cannot start ordinary application jobs.
Applying requires an unchanged saved preview and writes a separate audit report.
"""
import hashlib
import json
import math
from datetime import date
from types import SimpleNamespace

import click
from sqlalchemy import cast, inspect, select, String, update

from app import db
from app.models import Vehicle, FuelEntry, Entry
from app.services.fuel_efficiency import derive_efficiencies
from app.utils.units import distance_unit


def _number(value):
    return str(value) if isinstance(value, float) and not math.isfinite(value) else value


def preview_metrics(connection, lock=False):
    vehicles = select(Vehicle.id, Vehicle.user_id, Vehicle.distance_unit, Vehicle.avg_fuel_efficiency,
                      Vehicle.cost_per_km, Vehicle.health_score, cast(Vehicle.health_computed_at, String).label('health_computed_at'))
    if lock and connection.dialect.name == 'postgresql':
        vehicles = vehicles.with_for_update()
    snapshots, changes, reviews = [], [], []
    for vehicle in connection.execute(vehicles.order_by(Vehicle.id)):
        statement = select(FuelEntry.id, cast(FuelEntry.date, String).label('date'), FuelEntry.odometer,
                           cast(FuelEntry.liters, String).label('liters'), FuelEntry.full_tank,
                           FuelEntry.trip_distance, FuelEntry.fuel_efficiency).where(
                               FuelEntry.vehicle_id == vehicle.id, FuelEntry.user_id == vehicle.user_id).order_by(FuelEntry.date, FuelEntry.id)
        if lock and connection.dialect.name == 'postgresql':
            statement = statement.with_for_update(of=(Entry.__table__, FuelEntry.__table__))
        rows = [dict(row) for row in connection.execute(statement).mappings()]
        for row in rows:
            row['fuel_efficiency'] = _number(row['fuel_efficiency'])
        snapshots.append({'vehicle_id': vehicle.id, 'distance_unit': vehicle.distance_unit, 'entries': rows,
                          'health_cache': {key: _number(getattr(vehicle, key)) for key in
                                           ('avg_fuel_efficiency', 'cost_per_km', 'health_score', 'health_computed_at')}})
        try:
            for row in rows:
                date.fromisoformat(row['date'])
        except (ValueError, TypeError):
            reviews.append({'vehicle_id': vehicle.id, 'reason': 'Invalid source date; review the source before rebuilding.'})
            continue
        if distance_unit(vehicle.distance_unit) is None:
            reviews.append({'vehicle_id': vehicle.id, 'reason': 'Unknown distance unit; no unit will be inferred.'})
        for row, trip_distance, efficiency in derive_efficiencies((SimpleNamespace(**r) for r in rows), vehicle.distance_unit):
            if row.trip_distance != trip_distance or row.fuel_efficiency != efficiency:
                changes.append({'vehicle_id': vehicle.id, 'entry_id': row.id,
                                'before': {'trip_distance': row.trip_distance, 'fuel_efficiency': row.fuel_efficiency},
                                'after': {'trip_distance': trip_distance, 'fuel_efficiency': efficiency}})
    affected = {change['vehicle_id'] for change in changes}
    caches = [{'vehicle_id': snapshot['vehicle_id'], 'before': snapshot['health_cache'],
               'after': dict.fromkeys(snapshot['health_cache'])} for snapshot in snapshots if snapshot['vehicle_id'] in affected or any(value is not None for value in snapshot['health_cache'].values())]
    fingerprint = hashlib.sha256(json.dumps(snapshots, sort_keys=True, allow_nan=False).encode()).hexdigest()
    return {'version': 2, 'applied': False, 'phase': 'preview', 'source_fingerprint': fingerprint,
            'rebuild_scope': 'complete_fuel_history', 'entry_count': sum(len(s['entries']) for s in snapshots),
            'vehicle_count': len(snapshots), 'changes': changes, 'cache_invalidations': caches, 'review_required': reviews,
            'efficiency_unit': 'L/100km', 'trip_distance_unit': 'vehicle.distance_unit',
            'source_measurements_changed': False}


def _write_report(path, report):
    # Exclusive creation preserves the preview and prior audit trail.
    stream = open(path, 'x', encoding='utf-8')
    try:
        with stream:
            json.dump(report, stream, indent=2, allow_nan=False)
            stream.write('\n')
            stream.flush()
            import os
            os.fsync(stream.fileno())
    except Exception:
        from pathlib import Path
        Path(path).unlink(missing_ok=True)
        raise


def _finalize_report(path, report):
    """Mark committed only after commit; a crash leaves the prepared audit intact."""
    import os
    import tempfile
    from pathlib import Path
    descriptor, temporary = tempfile.mkstemp(prefix='.unit-audit-', dir=Path(path).parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump(report, stream, indent=2, allow_nan=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def create_rebuild_app(database_uri=None):
    from app.services.domain_scan import create_scan_app
    app = create_scan_app(database_uri)

    @app.cli.command('rebuild-unit-metrics')
    @click.option('--output', required=True, type=click.Path(dir_okay=False), help='New JSON preview/audit report file.')
    @click.option('--apply', is_flag=True, help='Apply derived changes from an unchanged saved preview.')
    @click.option('--preview', type=click.Path(exists=True, dir_okay=False), help='Previously saved preview; required with --apply.')
    def rebuild_unit_metrics(output, apply, preview):
        """Preview first; apply derived fields atomically without converting source data."""
        from pathlib import Path
        if Path(output).exists():
            raise click.ClickException('Choose a new output file; existing reports are never overwritten.')
        if apply and not preview:
            raise click.ClickException('--apply requires a saved --preview report.')
        expected = None
        if preview:
            try:
                expected = json.loads(Path(preview).read_text())
            except (ValueError, OSError):
                raise click.ClickException('Cannot read the preview report.') from None
        report = None
        report_written = False
        try:
            with db.engine.begin() as connection:
                if apply and connection.dialect.name == 'sqlite':
                    connection.exec_driver_sql('BEGIN IMMEDIATE')
                report = preview_metrics(connection, lock=apply)
                if apply:
                    if not isinstance(expected, dict) or expected.get('version') != report['version'] or expected.get('phase') != 'preview' or expected.get('applied') is not False or expected.get('source_fingerprint') != report['source_fingerprint']:
                        raise click.ClickException('Records changed or preview is invalid. Generate and review a fresh preview.')
                    columns = {column['name'] for column in inspect(connection).get_columns('entries')}
                    if 'revision' not in columns:
                        raise click.ClickException('Run the required database migrations before applying derived changes.')
                    for change in report['changes']:
                        connection.execute(update(FuelEntry.__table__).where(FuelEntry.id == change['entry_id']).values(**change['after']))
                        connection.execute(update(Entry.__table__).where(Entry.id == change['entry_id']).values(revision=Entry.revision + 1, updated_at=Entry.updated_at))
                    # Health caches depend on consumption and are rebuilt by the
                    # existing health workflow, never guessed from old values.
                    affected = {change['vehicle_id'] for change in report['cache_invalidations']}
                    if affected:
                        connection.execute(update(Vehicle.__table__).where(Vehicle.id.in_(affected)).values(
                            avg_fuel_efficiency=None, cost_per_km=None, health_score=None, health_computed_at=None,
                            revision=Vehicle.revision + 1, updated_at=Vehicle.updated_at))
                    report['phase'] = 'prepared'
                # Report-write failure aborts the database transaction.
                _write_report(output, report)
                report_written = True
        except Exception:
            # A prepared apply audit is retained if commit outcome is uncertain.
            if report_written and not apply and Path(output).exists():
                Path(output).unlink()
            raise
        if apply:
            report.update(applied=True, phase='committed')
            try:
                _finalize_report(output, report)
            except OSError as exc:
                raise click.ClickException('Database committed; audit remains prepared. Generate a fresh preview to reconcile before retrying.') from exc
        click.echo(f"{'Applied' if apply else 'Previewed'} {len(report['changes'])} derived changes; {len(report['review_required'])} vehicles require review.")

    return app

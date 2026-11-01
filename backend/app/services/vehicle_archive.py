"""Archive eligibility and a read-only review of possible legacy cancellations."""
import json

import click
from sqlalchemy import or_, select


def active_vehicle_condition(model):
    """Keep standalone tasks eligible while pausing archived vehicle activity."""
    from app.models import Vehicle
    active_ids = select(Vehicle.id).where(Vehicle.archived.is_(False)).correlate(None)
    return or_(model.vehicle_id.is_(None), model.vehicle_id.in_(active_ids))


def scan_archive_history(connection):
    """Flag ambiguous old archive side effects; never infer or restore values."""
    from app.models import Vehicle, InsurancePolicy, TaxEntry, Entry
    vehicles = connection.execute(select(Vehicle.id, Vehicle.user_id, Vehicle.archived_at)
        .where(Vehicle.archived.is_(True))).mappings().all()
    issues = []
    for vehicle in vehicles:
        archived_at = vehicle['archived_at']
        if archived_at is None:
            continue
        policies = connection.execute(select(InsurancePolicy.id).where(
            InsurancePolicy.vehicle_id == vehicle['id'],
            InsurancePolicy.user_id == vehicle['user_id'],
            InsurancePolicy.status == 'cancelled',
            InsurancePolicy.auto_renew.is_(False),
            InsurancePolicy.end_date == archived_at.date())).scalars().all()
        taxes = connection.execute(select(TaxEntry.id).select_from(TaxEntry).where(
            Entry.vehicle_id == vehicle['id'], Entry.user_id == vehicle['user_id'],
            TaxEntry.recurring.is_(False), TaxEntry.next_due_date.is_(None),
            TaxEntry.recurrence_type.isnot(None))).scalars().all()
        if policies or taxes:
            issues.append({'vehicle_id': vehicle['id'], 'user_id': vehicle['user_id'],
                'archived_at': archived_at.isoformat(), 'insurance_ids': policies,
                'tax_ids': taxes, 'reason': 'possible_legacy_archive_cancellation'})
    return {'version': 1, 'read_only': True, 'issue_count': len(issues), 'issues': issues,
        'review': 'These are candidates, not proof of an archive error. Compare policies, bills and earlier backups before correcting dates or recurrence. No values have been changed.',
        'limitations': 'Previously restored vehicles have no archive timestamp and cannot be identified reliably. Cleared dates and auto-renew settings cannot be reconstructed from current rows.'}


def create_archive_review_app(database_uri=None):
    """Minimal CLI factory without jobs, recovery or administrator creation."""
    from app import db
    from app.services.domain_scan import create_scan_app
    app = create_scan_app(database_uri)

    @app.cli.command('check-archive-history')
    @click.option('--output', type=click.File('w'), default='-')
    def check_archive_history(output):
        with db.engine.connect() as connection:
            report = scan_archive_history(connection)
        json.dump(report, output, indent=2)
        output.write('\n')
    return app

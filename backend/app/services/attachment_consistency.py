"""GC-017: validate receipt ownership and parent vehicles as one relationship.

The ORM guard runs after SQL relationship synchronization but before commit.
Historical rows are reported, never silently moved or deleted. Maintenance SQL
must use the read-only inventory before changing relationships outside the ORM.
"""
import json

import click
from sqlalchemy import event, inspect, or_, select, text
from sqlalchemy.orm import Session

from app import db
from app.utils.entryparse import InvalidFieldError


class AttachmentParentError(InvalidFieldError):
    def __init__(self, field='vehicle_id'):
        super().__init__('validation.invalidValue',
                         'Attachment, parent and vehicle must belong to the same account and vehicle. Review their links.', field)


def relationship_issues(graph):
    """Pure validator shared by database scans and portable archive preflight."""
    issues = []
    vehicles, entries = graph['vehicles'], graph['entries']
    attachments, policies = graph['attachments'], graph['insurance_policies']
    def issue(attachment, code, field, parent=None, policy=None):
        issues.append({'attachment_id': attachment['id'], 'user_id': attachment.get('user_id'),
                       'code': code, 'field': field, 'vehicle_id': attachment.get('vehicle_id'),
                       'entry_id': attachment.get('entry_id'), 'policy_id': policy['id'] if policy else None,
                       'parent_vehicle_id': parent.get('vehicle_id') if parent else None})
    for attachment in attachments.values():
        vehicle_id = attachment.get('vehicle_id')
        if vehicle_id is not None:
            vehicle = vehicles.get(vehicle_id)
            if vehicle is None:
                issue(attachment, 'missing_vehicle', 'vehicle_id')
            elif vehicle['user_id'] != attachment['user_id']:
                issue(attachment, 'vehicle_owner_mismatch', 'vehicle_id')
        if attachment.get('entry_id') is not None:
            parent = entries.get(attachment['entry_id'])
            if parent is None:
                issue(attachment, 'missing_entry', 'entry_id')
            elif parent['user_id'] != attachment['user_id']:
                issue(attachment, 'entry_owner_mismatch', 'entry_id', parent)
            elif parent['vehicle_id'] != vehicle_id or vehicle_id is None:
                issue(attachment, 'entry_vehicle_mismatch', 'vehicle_id', parent)
    for policy in policies.values():
        attachment_id = policy.get('document_attachment_id')
        if attachment_id is None:
            continue
        attachment = attachments.get(attachment_id)
        if attachment is None:
            issue({'id': attachment_id, 'user_id': policy['user_id']}, 'missing_document', 'document_attachment_id', policy, policy)
        elif attachment['user_id'] != policy['user_id']:
            issue(attachment, 'policy_owner_mismatch', 'document_attachment_id', policy, policy)
        elif attachment.get('vehicle_id') != policy['vehicle_id']:
            issue(attachment, 'policy_vehicle_mismatch', 'document_attachment_id', policy, policy)
    return issues


def read_graph(connection, *, attachment_ids=None, policy_ids=None, user_id=None):
    """Read only relationship columns, including foreign references for diagnosis."""
    from app.models import Attachment, Entry, InsurancePolicy, Vehicle
    a, e, p, v = (model.__table__ for model in (Attachment, Entry, InsurancePolicy, Vehicle))
    def rows(table, fields, condition=None):
        query = select(*(table.c[name] for name in fields))
        if condition is not None:
            query = query.where(condition)
        return {row['id']: dict(row) for row in connection.execute(query).mappings()}
    policy_fields = ('id', 'user_id', 'vehicle_id', 'document_attachment_id')
    attachment_fields = ('id', 'user_id', 'vehicle_id', 'entry_id')
    if user_id is not None:
        chosen_policies = rows(p, policy_fields, p.c.user_id == user_id)
        selected = (a.c.user_id == user_id) | a.c.id.in_([r['document_attachment_id'] for r in chosen_policies.values()])
    elif attachment_ids is not None or policy_ids is not None:
        chosen_policies = rows(p, policy_fields, p.c.id.in_(policy_ids or []))
        selected = a.c.id.in_(set(attachment_ids or []) | {r['document_attachment_id'] for r in chosen_policies.values()})
    else:
        chosen_policies, selected = rows(p, policy_fields), None
    attachments = rows(a, attachment_fields, selected)
    # Validate every policy pointing at a selected receipt, not just the first.
    chosen_policies.update(rows(p, policy_fields, p.c.document_attachment_id.in_(attachments)))
    entries = rows(e, ('id', 'user_id', 'vehicle_id'), e.c.id.in_([r['entry_id'] for r in attachments.values()]))
    vehicle_ids = {r['vehicle_id'] for r in [*attachments.values(), *entries.values(), *chosen_policies.values()]}
    vehicles = rows(v, ('id', 'user_id'), v.c.id.in_(vehicle_ids))
    return dict(vehicles=vehicles, entries=entries, attachments=attachments, insurance_policies=chosen_policies)


def validate_database(connection, **scope):
    issues = relationship_issues(read_graph(connection, **scope))
    if issues:
        raise AttachmentParentError(issues[0]['field'])


def validate_archive(records):
    """Derive absent parent vehicles; reject contradictory source evidence."""
    from app.services.backup_schema import ENTRY_COLLECTIONS, BackupSchemaError
    attachments = {r['id']: r for r in records['attachments']}
    entries = {r['id']: r for kind in ENTRY_COLLECTIONS for r in records[kind]}
    parents = {}
    for row in attachments.values():
        if row.get('entry_id') in entries:
            parents.setdefault(row['id'], []).append(entries[row['entry_id']])
    for policy in records['insurance_policies']:
        if policy.get('document_attachment_id') in attachments:
            parents.setdefault(policy['document_attachment_id'], []).append(policy)
    for attachment_id, linked in parents.items():
        row = attachments[attachment_id]
        vehicles = {parent['vehicle_id'] for parent in linked}
        if len(vehicles) != 1 or (row.get('vehicle_id') is not None and row['vehicle_id'] not in vehicles):
            raise BackupSchemaError('Attachment vehicle conflicts with its parent. Review the source links.',
                                    f'attachments[id={attachment_id}].vehicle_id')
        row['vehicle_id'] = next(iter(vehicles))
    graph = {'vehicles': {r['id']: {**r, 'user_id': 0} for r in records['vehicles']},
             'entries': {key: {**row, 'user_id': 0} for key, row in entries.items()},
             'attachments': {key: {**row, 'user_id': 0} for key, row in attachments.items()},
             'insurance_policies': {r['id']: {**r, 'user_id': 0} for r in records['insurance_policies']
                                    if r.get('vehicle_id') in {v['id'] for v in records['vehicles']}}}
    issues = relationship_issues(graph)
    if issues:
        issue = issues[0]
        raise BackupSchemaError('Attachment references an inconsistent parent or vehicle. Review the source links.',
                                f'attachments[id={issue["attachment_id"]}].{issue["field"]}')


# Relationship writes use a common transaction lock. This also serializes an
# entry/vehicle move against a concurrent receipt link in PostgreSQL.
_RELATION_LOCK = 0x4743303137
_FIELDS = {'attachments': ('user_id', 'vehicle_id', 'entry_id', 'entry', 'vehicle'),
           'entries': ('user_id', 'vehicle_id', 'vehicle'),
           'insurance_policies': ('user_id', 'vehicle_id', 'document_attachment_id', 'document', 'vehicle'),
           'vehicles': ('user_id',)}


@event.listens_for(Session, 'before_flush')
def _track_relationship_writes(session, flush_context, instances):
    from app.models import Attachment, Entry, InsurancePolicy, Vehicle
    selected = []
    for record in session.new | session.dirty | session.deleted:
        if not isinstance(record, (Attachment, Entry, InsurancePolicy, Vehicle)):
            continue
        state = inspect(record)
        table = state.mapper.base_mapper.local_table.name
        if record in session.new or record in session.deleted or any(
                field in state.attrs and state.attrs[field].history.has_changes() for field in _FIELDS[table]):
            selected.append((table, record))
    if not selected:
        return
    connection = session.connection()
    if connection.dialect.name == 'postgresql':
        connection.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': _RELATION_LOCK})
    session.info.setdefault('attachment_parent_checks', []).extend(selected)


@event.listens_for(Session, 'after_flush_postexec')
def _check_relationship_writes(session, flush_context):
    pending = session.info.pop('attachment_parent_checks', [])
    if not pending:
        return
    from app.models import Attachment, Entry, InsurancePolicy
    ids = {kind: {row.id for table, row in pending if table == kind and row.id is not None} for kind in _FIELDS}
    connection = session.connection()
    a, e, p = (model.__table__ for model in (Attachment, Entry, InsurancePolicy))
    attachment_ids = ids['attachments'] | set(connection.execute(select(a.c.id).where(or_(
        a.c.entry_id.in_(ids['entries']), a.c.vehicle_id.in_(ids['vehicles']),
        a.c.entry_id.in_(select(e.c.id).where(e.c.vehicle_id.in_(ids['vehicles'])))))).scalars())
    policy_ids = ids['insurance_policies'] | set(connection.execute(select(p.c.id).where(p.c.vehicle_id.in_(ids['vehicles']))).scalars())
    validate_database(connection, attachment_ids=attachment_ids, policy_ids=policy_ids)


@event.listens_for(Session, 'after_soft_rollback')
def _clear_checks(session, previous_transaction):
    session.info.pop('attachment_parent_checks', None)


def scan_relationships(connection):
    graph = read_graph(connection)
    issues = relationship_issues(graph)
    return {'version': 1, 'read_only': True, 'attachment_count': len(graph['attachments']),
            'issue_count': len(issues), 'issues': issues,
            'review': 'Compare the source documents and parent records. Explicitly correct vehicle/entry links or detach an incorrect link; never infer ownership or delete files automatically.'}


def create_consistency_app(database_uri=None):
    """CLI-only factory: no recovery, schedulers, OCR, or administrator creation."""
    from app.services.domain_scan import create_scan_app
    app = create_scan_app(database_uri)
    @app.cli.command('check-attachment-links')
    @click.option('--output', type=click.File('w'), default='-', help='JSON review report; defaults to stdout.')
    def check_attachment_links(output):
        with db.engine.connect() as connection:
            report = scan_relationships(connection)
        json.dump(report, output, indent=2)
        output.write('\n')
    return app


@event.listens_for(Session, 'do_orm_execute')
def _require_relationship_unit_of_work(state):
    # Bulk ORM DML bypasses flush listeners and relationship synchronization.
    # Application callers must use ordinary records; explicit maintenance SQL
    # uses an Engine connection and the review/report workflow instead.
    table = getattr(getattr(state.statement, 'table', None), 'name', None)
    if table not in _FIELDS or not (state.is_insert or state.is_update):
        return
    # Include both UPDATE.values() assignments and executemany parameter maps.
    # Metadata-only bulk updates do not change this invariant.
    assignments = set(getattr(state.statement, '_values', None) or {})
    assignments.update(key for key, value in (getattr(state.statement, '_ordered_values', None) or []))
    parameters = state.parameters or []
    if isinstance(parameters, dict):
        parameters = [parameters]
    for values in parameters:
        if isinstance(values, dict):
            assignments.update(values)
    fields = {getattr(key, 'key', key) for key in assignments}
    if state.is_insert or fields.intersection(_FIELDS[table]):
        raise AttachmentParentError('parent')

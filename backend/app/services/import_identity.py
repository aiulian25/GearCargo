"""Plan imports by source identity. Similar content is advisory, never a match."""
import hashlib
import json
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import text
from app import db
from app.models import ImportBatch, ImportIdentity

DERIVED = {'fuel_efficiency', 'trip_distance', 'avg_fuel_efficiency', 'cost_per_km',
           'health_score', 'health_computed_at', 'revision', 'created_at', 'updated_at'}


def portable(value):
    if isinstance(value, Decimal):
        return format(value.normalize(), 'f')
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): portable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [portable(v) for v in value]
    return value


def digest(value):
    return hashlib.sha256(json.dumps(portable(value), sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def namespace_for(source_format, label, file_key):
    if label is None or label == '':
        return f'{source_format}:file:{file_key}'
    if not isinstance(label, str) or len(label) > 100 or not label.strip():
        raise ValueError('Source label must contain 1–100 characters.')
    return f'{source_format}:source:{digest(label.strip())}'


def native_namespace(user):
    return 'gearcargo:' + user.export_namespace


def source_payload(row):
    payload = portable({key: row.get('_source_refs', {}).get(key, value) for key, value in row.items()
                     if key not in DERIVED and key != 'id' and (not key.startswith('_') or key in {'_content_sha256', '_photo_sha256'})})
    payload.update({key: None for key in row.get('_empty_fields', []) if key not in DERIVED})
    return payload


def same_source(left, right):
    # Old provenance predates nullable currency/recurrence fields; empty adds no fact.
    nullable_additions = {'purchase_currency', 'repeat_mileage', 'recurrence_anchor_date', 'notification_state'}
    left = {k: v for k, v in left.items() if k not in nullable_additions or v not in (None, {})}
    right = {k: v for k, v in right.items() if k not in nullable_additions or v not in (None, {})}
    # A data-only export has no byte fingerprint. Adding media later must not
    # create another expense or attachment. Compare bytes when both supplied it.
    optional = {'_content_sha256', '_photo_sha256'}
    if left.get('_partial') or right.get('_partial'):
        fields = (left.keys() & right.keys()) - {'_partial'}
        left = {k: left[k] for k in fields}
        right = {k: right[k] for k in fields}
    common = optional & left.keys() & right.keys()
    return digest({k: v for k, v in left.items() if k not in optional or k in common}) == digest(
        {k: v for k, v in right.items() if k not in optional or k in common})


def created_stamp(record):
    value = getattr(record, 'created_at', None)
    return value.isoformat() if value is not None else None


def lock_imports(user_id):
    """Serialise competing imports; uniqueness is a second database guard."""
    if db.engine.dialect.name == 'postgresql':
        key = int.from_bytes(hashlib.sha256(f'gc016:{user_id}'.encode()).digest()[:8], 'big', signed=True)
        db.session.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': key})
    elif db.engine.dialect.name == 'sqlite':
        connection = db.session.connection()
        if not connection.connection.driver_connection.in_transaction:
            connection.exec_driver_sql('BEGIN IMMEDIATE')


from app.services.backup_schema import BackupSchemaError


class ImportConflict(BackupSchemaError):
    def __init__(self, preview, message='Review changed source records before importing.'):
        self.preview = preview
        super().__init__(message)


class ImportPlan:
    def __init__(self, user, prepared):
        from app.services.backup_schema import MODELS
        self.user, self.prepared, self.models = user, prepared, MODELS
        self.actions = {}
        self.batch = None
        self.existing = {kind: {record.id: record for record in model.query.filter_by(user_id=user.id).all()}
                         for kind, model in MODELS.items() if prepared.records.get(kind)}
        identities = ImportIdentity.query.filter_by(user_id=user.id).all()
        self.identities = {(item.namespace, item.entity_kind, item.source_id): item for item in identities}
        seen = {}
        for kind, rows in prepared.records.items():
            for row in rows:
                local_key = (kind, row['id'])
                namespace, source_id = prepared.source_keys.get(local_key, (prepared.namespace, str(row['id'])))
                key = (namespace, kind, str(source_id))
                claims = [key] + [(o['namespace'], kind, o['source_id']) for o in prepared.origins.get(local_key, [])]
                for claim in claims:
                    if claim in seen and seen[claim] != local_key:
                        raise ValueError('Duplicate source identity within the import. Give distinct source rows distinct IDs.')
                    seen[claim] = local_key
                payload = source_payload(row)
                if prepared.import_format == 'csv':
                    payload['_partial'] = True
                source_hash = digest(payload)
                identity = self.identities.get(key)
                target, reason, action = None, None, 'create'
                if identity:
                    target = self.existing.get(kind, {}).get(identity.target_id)
                    if target is None or created_stamp(target) != identity.target_created_at:
                        target, action, reason = None, 'conflict', 'destination_missing'
                    elif not same_source(identity.source_payload, payload):
                        action, reason = 'conflict', 'source_changed'
                    else:
                        action = 'exact_repeat'
                elif prepared.origins.get(local_key):
                    matches = [self.identities.get((origin['namespace'], kind, origin['source_id']))
                               for origin in prepared.origins[local_key]]
                    matches = [match for match in matches if match]
                    if matches:
                        ids = {match.target_id for match in matches}
                        target = self.existing.get(kind, {}).get(matches[0].target_id) if len(ids) == 1 else None
                        if target is None or any(created_stamp(target) != match.target_created_at for match in matches):
                            action, reason = 'conflict', 'destination_missing'
                        else:
                            fields = {name: value for name, value in payload.items() if not name.endswith('_id') and not name.startswith('_')}
                            local = source_payload({name: getattr(target, name) for name in fields})
                            action = 'exact_repeat' if digest(local) == digest(fields) else 'conflict'
                            reason = None if action == 'exact_repeat' else 'source_changed'
                elif namespace == native_namespace(user):
                    target = self.existing.get(kind, {}).get(int(source_id)) if str(source_id).isdigit() else None
                    if target:
                        local = source_payload({name: getattr(target, name) for name in payload if not name.startswith('_')})
                        action = 'exact_repeat' if same_source(local, payload) else 'conflict'
                        reason = None if action == 'exact_repeat' else 'source_changed'
                if action == 'create' and kind in ('statement_batches', 'statement_transactions'):
                    field = 'source_key' if kind == 'statement_batches' else 'fingerprint'
                    existing_statement = next((record for record in self.existing.get(kind, {}).values()
                                               if getattr(record, field) == row[field]), None)
                    if existing_statement:
                        target, action, reason = existing_statement, 'conflict', 'statement_source_collision'
                if action == 'create' and not target and not identity and kind == 'vehicles':
                    target = next((record for record in self.existing.get(kind, {}).values()
                                   if (row.get('vin') and row['vin'] == record.vin)
                                   or (row.get('license_plate') and row['license_plate'] == record.license_plate)), None)
                    if target:
                        action, reason = 'conflict', 'vehicle_link_required'
                if target and kind == 'vehicles':
                    from app.utils.units import distance_unit
                    if distance_unit(target.distance_unit) != distance_unit(row.get('distance_unit')):
                        action, reason = 'conflict', 'distance_unit_mismatch'
                possible = []
                if action == 'create':
                    # Compare a projection of domain content. This never suppresses
                    # an expense or establishes a relationship to a vehicle.
                    fields = {field: value for field, value in payload.items()
                              if not field.endswith('_id') and field != 'filename' and not field.startswith('_')}
                    for candidate in self.existing.get(kind, {}).values():
                        local = portable({field: getattr(candidate, field) for field in fields})
                        if digest(local) == digest(fields):
                            possible.append(candidate.id)
                self.actions[local_key] = dict(key=key, row=row, payload=payload, source_hash=source_hash,
                    identity=identity, target=target, action=action, reason=reason, possible=possible[:10])
        # A deleted source parent cannot silently acquire newly imported children.
        for (kind, row_id), item in self.actions.items():
            row = item['row']
            parent = self.actions.get(('vehicles', row.get('vehicle_id')))
            if parent and parent['reason'] == 'destination_missing':
                item.update(action='conflict', reason='destination_missing', target=None)
        state = [{**self.public_action(key, item), 'hash': item['source_hash'],
                  'revision': getattr(item['target'], 'revision', None),
                  'updated_at': portable(getattr(item['target'], 'updated_at', None))}
                 for key, item in self.actions.items()]
        self.preview = {
            'batch_key': prepared.batch_key, 'source_namespace': prepared.namespace,
            'new_records': sum(item['action'] == 'create' for item in self.actions.values()),
            'exact_repeats': sum(item['action'] == 'exact_repeat' for item in self.actions.values()),
            'conflicts': sum(item['action'] == 'conflict' for item in self.actions.values()),
            'possible_duplicates': sum(bool(item['possible']) for item in self.actions.values()),
            'records': [self.public_action(key, item) for key, item in sorted(self.actions.items(), key=lambda pair: pair[1]['action'] != 'conflict')][:100],
            'records_truncated': len(state) > 100,
            'blocked': any(item['reason'] in ('distance_unit_mismatch', 'statement_source_collision') for item in self.actions.values()),
            'preview_token': digest({'batch': prepared.batch_key, 'state': state}),
        }

        if any(item['reason'] == 'statement_source_collision' for item in self.actions.values()):
            self.preview['statement_collision'] = True

    @staticmethod
    def public_action(key, item):
        return {'kind': key[0], 'source_id': item['key'][2], 'archive_id': key[1], 'action': item['action'],
                'reason': item['reason'], 'existing_id': item['target'].id if item['target'] else None,
                'possible_duplicate_ids': item['possible']}

    def validate_apply(self, policy='reject', token=None):
        if policy not in ('reject', 'keep_existing'):
            raise ValueError('Unsupported conflict decision.')
        if token and token != self.preview['preview_token']:
            raise ImportConflict(self.preview, 'Import or destination changed. Review a fresh preview.')
        blocked = [item for item in self.actions.values() if item['action'] == 'conflict'
                   and (policy != 'keep_existing' or item['reason'] in ('distance_unit_mismatch', 'statement_source_collision'))]
        if blocked:
            if any(item['reason'] == 'distance_unit_mismatch' for item in blocked):
                message = 'Vehicle distance units differ. Import into a separate account or use matching units.'
            elif any(item['reason'] == 'statement_source_collision' for item in blocked):
                message = 'This statement file already exists from another source. Review it or delete its statement data before replacement.'
            else:
                message = 'Review changed source records before importing.'
            raise ImportConflict(self.preview, message)

    def begin(self, policy):
        self.batch = ImportBatch.query.filter_by(user_id=self.user.id, batch_key=self.prepared.batch_key).first()
        if self.batch is None:
            self.batch = ImportBatch(user_id=self.user.id, batch_key=self.prepared.batch_key,
                source_format=self.prepared.import_format,
                metadata_json={'namespace': self.prepared.namespace, 'policy': policy,
                               'origins': [origin for origins in self.prepared.origins.values() for origin in origins],
                               'records': [{**self.public_action(key, item), 'source_hash': item['source_hash'],
                                            'source_payload': item['payload']} for key, item in self.actions.items()]})
            db.session.add(self.batch)
            db.session.flush()

    def remember(self, local_key, target):
        item = self.actions[local_key]
        if target is None:
            return
        identity = item['identity']
        if identity is None:
            namespace, kind, source_id = item['key']
            identity = ImportIdentity(user_id=self.user.id, namespace=namespace, entity_kind=kind,
                source_id=source_id, target_id=target.id, target_created_at=created_stamp(target),
                original_payload=item['payload'], first_batch_id=self.batch.id)
            db.session.add(identity)
        # Retain byte evidence when the next transport contains metadata only.
        payload = {k: v for k, v in (identity.source_payload or {}).items() if k in {'_content_sha256', '_photo_sha256'} or self.prepared.import_format == 'csv'}
        payload.update(item['payload'])
        identity.source_hash = digest(payload)
        identity.source_payload = payload
        self.identities[item['key']] = identity
        identity.last_batch_id = self.batch.id
        for origin in self.prepared.origins.get(local_key, []):
            key = (origin['namespace'], local_key[0], origin['source_id'])
            known = self.identities.get(key)
            if known:
                # A different target can never acquire an already-bound identity.
                if known.target_id != target.id or known.target_created_at != created_stamp(target):
                    raise ImportConflict(self.preview, 'Source metadata is already linked to another record.')
                continue
            if key == item['key']:
                continue
            alias = ImportIdentity(user_id=self.user.id, namespace=key[0], entity_kind=key[1], source_id=key[2],
                target_id=target.id, target_created_at=created_stamp(target), source_hash=origin['source_hash'],
                source_payload=origin['source_payload'], original_payload=origin['original_payload'],
                first_batch_id=self.batch.id, last_batch_id=self.batch.id)
            db.session.add(alias)
            self.identities[key] = alias

    def result(self):
        return {name: self.preview[name] for name in ('batch_key', 'new_records', 'exact_repeats', 'conflicts', 'possible_duplicates')}

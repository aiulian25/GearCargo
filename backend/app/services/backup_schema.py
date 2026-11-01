"""Versioned, allowlisted portable-user backup contract (GC-001).

Never use UI ``to_dict`` methods here. IDs are archive-local relationship keys,
not identities to reuse in the destination database. Account authentication,
consent, integration credentials, delivery logs and server configuration are
intentionally outside this portable format; see docs/USER_BACKUPS.md.
"""
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import math

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, JSON, Numeric, String, inspect, null
from sqlalchemy.orm.attributes import flag_modified

from app import db
from app.models import (Entry, Vehicle, FuelEntry, ServiceEntry, RepairEntry, TaxEntry,
                        ParkingEntry, ConsumableEntry, InsurancePolicy, Reminder,
                        Todo, PredictionAlert, Attachment, DueDismissal, User, TireSet, Tire, FitmentEvent, TreadReading, Appointment, AppointmentTask, AppointmentExpense, StatementBatch, StatementTransaction, StatementMatch)

USER_BACKUP_VERSION = '4.7'
STATEMENT_COLLECTIONS = ('statement_batches', 'statement_transactions', 'statement_matches')
APPOINTMENT_COLLECTIONS = ('appointments', 'appointment_tasks', 'appointment_expenses')
TIRE_COLLECTIONS = ('tire_sets', 'tires', 'tire_fitments', 'tread_readings')
LEGACY_VERSIONS = {'1.0', '2.0'}
ENTRY_COLLECTIONS = ('fuel_entries', 'service_entries', 'repair_entries',
                     'tax_entries', 'parking_entries', 'consumable_entries')

# Explicit inventory. The regression test requires a decision for each mapped
# column, so adding a model field cannot silently make backups incomplete.
MODELS = {
    'vehicles': Vehicle,
    'fuel_entries': FuelEntry,
    'service_entries': ServiceEntry,
    'repair_entries': RepairEntry,
    'tax_entries': TaxEntry,
    'parking_entries': ParkingEntry,
    'consumable_entries': ConsumableEntry,
    'insurance_policies': InsurancePolicy,
    'reminders': Reminder,
    'todos': Todo,
    'predictions': PredictionAlert,
    'attachments': Attachment,
    'tire_sets': TireSet, 'tires': Tire, 'tire_fitments': FitmentEvent, 'tread_readings': TreadReading,
    'appointments': Appointment, 'appointment_tasks': AppointmentTask, 'appointment_expenses': AppointmentExpense,
    'statement_batches': StatementBatch, 'statement_transactions': StatementTransaction, 'statement_matches': StatementMatch,
    'due_dismissals': DueDismissal,
}

FIELDS = {
    'statement_batches': tuple('id name source_key selection_hash status created_at updated_at'.split()),
    'statement_transactions': tuple('id batch_id row_number fingerprint date amount currency vendor exclusion_reason created_at'.split()),
    'statement_matches': tuple('id transaction_id entry_id amount entry_signature created_at'.split()),
    'appointments': tuple('id vehicle_id title shop_name shop_contact notes status time_zone start_at end_at confirmed_at dropoff_at pickup_at prepare_minutes notify_push notify_email preparation_reminder_id created_at updated_at'.split()),
    'appointment_tasks': tuple('id vehicle_id appointment_id title done reminder_id todo_id service_id prediction_id source_signature created_at'.split()),
    'appointment_expenses': tuple('id vehicle_id appointment_id entry_id created_at'.split()),
    'tire_sets': tuple('id vehicle_id name season storage_location purchase_entry_id rotation_interval tread_unit tread_threshold created_at updated_at'.split()),
    'tires': tuple('id vehicle_id tire_set_id identifier created_at'.split()),
    'tire_fitments': tuple('id vehicle_id tire_set_id kind date odometer positions created_at'.split()),
    'tread_readings': tuple('id vehicle_id tire_set_id tire_id date depth unit created_at'.split()),
    'vehicles': tuple('''
        id name make model year vin license_plate
        fuel_type tank_capacity engine_cc transmission drivetrain color vehicle_weight_kg
        vehicle_height_cm vehicle_length_cm vehicle_width_cm current_mileage distance_unit purchase_date purchase_price purchase_currency
        monthly_budget avg_trip_distance city_driving_percentage highway_driving_percentage cost_per_km avg_fuel_efficiency maintenance_score
        prediction_accuracy_score health_score health_computed_at maintenance_intervals archived archived_at last_prediction_at
        display_order created_at updated_at
    '''.split()),
    'fuel_entries': tuple('''
        id title description amount currency odometer date
        notes vehicle_id created_at updated_at liters price_per_liter total_price
        fuel_type station station_address full_tank fuel_efficiency trip_distance ocr_populated
    '''.split()),
    'service_entries': tuple('''
        id title description amount currency odometer date
        notes vehicle_id created_at updated_at service_type service_types provider
        garage_name garage_address garage_phone postcode work_order_number labor_hours labor_cost
        parts_cost parts_used warranty_months warranty_km warranty_notes warranty_expires warranty_notified
        next_due_date next_due_mileage
    '''.split()),
    'repair_entries': tuple('''
        id title description amount currency odometer date
        notes vehicle_id created_at updated_at repair_type repair_types diagnosis
        symptoms root_cause provider garage_name garage_address labor_hours labor_cost
        parts_cost parts_replaced warranty_months warranty_km warranty_notes under_warranty warranty_notified
        severity
    '''.split()),
    'tax_entries': tuple('''
        id title description amount currency odometer date
        notes vehicle_id created_at updated_at tax_type tax_year tax_period
        tax_rate insurance_policy_id status due_date paid_date filing_date reference_number
        recurring recurrence_type next_due_date reminder_days
    '''.split()),
    'parking_entries': tuple('''
        id title description amount currency odometer date
        notes vehicle_id created_at updated_at parking_type location location_address
        start_datetime end_datetime duration_minutes recurring recurrence_type next_due_date reminder_days
        permit_number permit_expires fine_reason fine_status
    '''.split()),
    'consumable_entries': tuple('''
        id title description amount currency odometer date
        notes vehicle_id created_at updated_at consumable_type brand quantity
        install_date install_odometer expected_lifespan_km expected_lifespan_months warranty_months replace_notified warranty_notified
    '''.split()),
    'insurance_policies': tuple('''
        id vehicle_id policy_number provider policy_type coverage_amount deductible
        coverage_details premium payment_frequency currency start_date end_date agent_name
        agent_phone agent_email claims_phone document_attachment_id status auto_renew renewed_from_id
        notes created_at updated_at
    '''.split()),
    'reminders': tuple('''
        id title description due_date due_mileage reminder_type priority
        recurring frequency frequency_value recurrence_end repeat_mileage recurrence_anchor_date notification_state completed completed_at dismissed
        dismissed_at snoozed_until calendar_sync title_translations description_translations notify_days_before notify_email
        notify_push last_notified_at vehicle_id source_service_id completed_from_id mileage_notified created_at updated_at
    '''.split()),
    'todos': tuple('''
        id title description due_date priority recurring frequency
        frequency_value completed completed_at completed_from_id vehicle_id created_at updated_at
    '''.split()),
    'predictions': tuple('''
        id alert_type description predicted_mileage predicted_date confidence_score severity
        dismissed dismissed_at actioned actioned_at i18n_key i18n_params description_en_us
        description_ro description_es generated_by model_version title urgency estimated_cost
        recommended_action source_data vehicle_id created_at expires_at
    '''.split()),
    'attachments': tuple('''
        id filename original_filename file_type file_size description category
        tags ocr_text ocr_processed vin_extracted expires_at expiry_notified entry_id
        vehicle_id created_at updated_at
    '''.split()),
    'due_dismissals': tuple('''
        id kind ref_id due_date created_at
    '''.split()),
}

EXCLUDED_COLUMNS = {
    'statement_batches': ('user_id', 'revision'), 'statement_transactions': ('user_id',), 'statement_matches': ('user_id',),
    'appointments': ('user_id', 'revision'), 'appointment_tasks': ('user_id',), 'appointment_expenses': ('user_id',),
    'tire_sets': ('user_id', 'revision'),
    'tires': ('user_id',), 'tire_fitments': ('user_id',), 'tread_readings': ('user_id',),
    'vehicles': ('photo', 'user_id'),
    'fuel_entries': ('receipt_image', 'type', 'user_id'),
    'service_entries': ('type', 'user_id'),
    'repair_entries': ('type', 'user_id'),
    'tax_entries': ('type', 'user_id'),
    'parking_entries': ('type', 'user_id'),
    'consumable_entries': ('type', 'user_id'),
    'insurance_policies': ('user_id',),
    'reminders': ('calendar_service', 'external_calendar_id', 'external_checksum', 'external_etag', 'last_synced_at', 'local_version_data', 'remote_version_data', 'sync_conflict', 'user_id'),
    'todos': ('user_id',),
    'predictions': ('user_id',),
    'attachments': ('filepath', 'user_id', 'ocr_state', 'ocr_attempts', 'ocr_generation',
                    'ocr_owner', 'ocr_lease_until', 'ocr_next_attempt_at', 'ocr_error'),
    'due_dismissals': ('user_id',),
}

# Revisions identify a local record incarnation, not portable business data.
for _kind in ('vehicles', *ENTRY_COLLECTIONS, 'insurance_policies', 'reminders', 'todos', 'attachments'):
    EXCLUDED_COLUMNS[_kind] += ('revision',)

PREFERENCE_FIELDS = tuple('''
    language timezone theme currency distance_unit volume_unit date_format country_preference
    notifications_enabled email_insurance_alerts email_tax_alerts email_service_alerts
    email_reminder_alerts email_smart_alerts login_alerts_enabled daily_alerts_enabled
    weekly_report_enabled monthly_report_enabled alert_days_before
    location_lat location_lon location_name location_auto_detect
'''.split())
# Do not copy arbitrary preferences: avatar URLs, calendar credentials and future
# integration settings must not cross account boundaries through an open dict.
PREFERENCE_JSON_KEYS = ('seasonal_checklists', 'checklist_settings')

# Account identity/security/operational columns are intentionally not portable.
# Keep this explicit so future profile/preferences additions require a decision.
ACCOUNT_EXCLUDED_COLUMNS = tuple('export_namespace id username email password_hash first_name last_name avatar two_factor_secret two_factor_enabled two_factor_backup_codes email_otp_secret email_verified email_verification_token email_verification_expires password_reset_token password_reset_expires last_password_change security_questions security_questions_set_at is_active is_admin is_dummy must_change_password vehicle_limit max_sessions api_key api_key_hash api_key_prefix notification_email notification_email_hash notification_email_verified notification_email_token notification_email_token_exp notification_email_consented_at notification_email_consent_ip notification_email_bounce_count unsubscribe_token last_weekly_report last_monthly_report calendar_enabled calendar_provider calendar_url calendar_username calendar_password calendar_id calendar_last_sync calendar_feed_secret failed_login_attempts locked_until created_at updated_at last_login'.split())
EXCLUDED_MODELS = {
    'User': 'Only allowlisted preferences are portable; identity/security remain local.',
    'Entry': 'Base table covered by the six supported concrete expense types.',
    'Backup': 'Local archive catalog and paths.',
    'BackupSchedule': 'Deployment scheduling and external credentials.',
    'PushSubscription': 'Device-bound subscription credentials.',
    'NotificationLog': 'Operational delivery history, subscription IDs and transport payloads.',
    'ActivityLog': 'Security audit history belonging to this account/installation.',
    'EmailConsentLog': 'Consent evidence must not transfer to another account.',
    'UserSession': 'Authentication state.',
    'Passkey': 'Device- and hostname-bound credentials; the private half never leaves the authenticator, so a restored public key authenticates nothing.',
    'ReportShare': 'Public capabilities must not be reactivated by personal restore.',
    'BlockedIP': 'Installation security policy.',
    'BlockedDevice': 'Installation security policy.',
    'AppSetting': 'Server configuration and secrets.',
    'FuelPriceHistory': 'Shared provider data, not account-owned records.',
    'DeletionTask': 'Committed installation cleanup work; never replay deletion in another account.',
    'ImportBatch': 'Import decisions are portable through the source_metadata inventory, not replayed as operations.',
    'ImportIdentity': 'Active source identities are exported through source_metadata with remapped targets.',
    'MutationOperation': 'Installation/account-bound request receipts; never import or reassign request identities.',
    'CalendarOutbox': 'Installation/account/calendar-bound delivery state and tombstones; never replay against another account.',
    'JobRun': 'Installation-owned scheduler occurrence cursor and execution fence.',
    'ScheduledEffect': 'Account/installation-owned scheduled delivery state; not portable vehicle data.',
    'OcrSlot': 'Installation-owned OCR admission and execution slots; never import active claims.',
}

DUE_TARGETS = {
    'tire_rotation': 'tire_sets', 'tire_tread': 'tire_sets',
    'reminder': 'reminders', 'todo': 'todos', 'service': 'service_entries',
    'tax': 'tax_entries', 'insurance': 'insurance_policies', 'document': 'attachments',
    'parking': 'parking_entries', 'fine': 'parking_entries',
    'consumable': 'consumable_entries', 'prediction': 'predictions',
}
LINKS = {
    'statement_transactions': {'batch_id': 'statement_batches'},
    'statement_matches': {'transaction_id': 'statement_transactions', 'entry_id': 'entries'},
    'appointments': {'preparation_reminder_id': 'reminders'},
    'appointment_tasks': {'appointment_id': 'appointments', 'reminder_id': 'reminders', 'todo_id': 'todos', 'service_id': 'service_entries', 'prediction_id': 'predictions'},
    'appointment_expenses': {'appointment_id': 'appointments', 'entry_id': 'entries'},
    'tire_sets': {'purchase_entry_id': 'entries'},
    'tires': {'tire_set_id': 'tire_sets'},
    'tire_fitments': {'tire_set_id': 'tire_sets'},
    'tread_readings': {'tire_set_id': 'tire_sets', 'tire_id': 'tires'},
    'tax_entries': {'insurance_policy_id': 'insurance_policies'},
    'insurance_policies': {'renewed_from_id': 'insurance_policies',
                           'document_attachment_id': 'attachments'},
    'reminders': {'source_service_id': 'service_entries', 'completed_from_id': 'reminders'},
    'todos': {'completed_from_id': 'todos'},
    'attachments': {'entry_id': 'entries'},
}
PREDICTION_SOURCE_LINKS = {'vehicle_id': 'vehicles', 'trigger_entry_id': 'entries'}
for _kind in MODELS:
    if 'vehicle_id' in FIELDS[_kind]:
        LINKS.setdefault(_kind, {})['vehicle_id'] = 'vehicles'


class BackupSchemaError(ValueError):
    """A safe field/path diagnostic, never an echo of untrusted field contents."""
    def __init__(self, message, path='backup'):
        self.issue = {'code': 'invalid_backup', 'path': path, 'message': message}
        super().__init__(message)


def warning(code, path, message):
    return {'code': code, 'path': path, 'message': message}


def serialize_value(value):
    if isinstance(value, Decimal):
        return str(value)  # No binary-float round trip for money/quantities.
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return deepcopy(value)


def serialize_record(kind, record):
    return {field: serialize_value(getattr(record, field)) for field in FIELDS[kind]}


def export_user_data(user, include_attachments=True):
    """Export stored values and portable preferences, including attachment metadata.

    ``include_attachments`` controls file bytes, not metadata. JSON/data-only
    restores retain documents/OCR/relationships but report unavailable file bytes.
    """
    from app.services.attachment_consistency import validate_database, AttachmentParentError
    try:
        validate_database(db.session.connection(), user_id=user.id)
    except AttachmentParentError as exc:
        raise BackupSchemaError(exc.error, 'attachments') from None
    allowed_types = [MODELS[kind].__mapper_args__['polymorphic_identity'] for kind in ENTRY_COLLECTIONS]
    if Entry.query.filter(Entry.user_id == user.id,
                          db.or_(Entry.type.is_(None), Entry.type.notin_(allowed_types))).with_entities(Entry.id).first():
        raise BackupSchemaError('Unsupported expense type in this account.', 'vehicles')
    records = {}
    for kind, model in MODELS.items():
        records[kind] = [serialize_record(kind, row) for row in
                         model.query.filter_by(user_id=user.id).order_by(model.id).all()]
    vehicles = records.pop('vehicles')
    for vehicle in vehicles:
        for kind in ENTRY_COLLECTIONS:
            vehicle[kind] = [row for row in records[kind] if row['vehicle_id'] == vehicle['id']]
    # Fail instead of silently losing a child that is not in its owner's garage.
    owned_ids = {v['id'] for v in vehicles}
    for kind in ENTRY_COLLECTIONS:
        if any(row['vehicle_id'] not in owned_ids for row in records.pop(kind)):
            raise BackupSchemaError('Record has no vehicle in this account.', kind)
    prefs = {key: serialize_value(getattr(user, key)) for key in PREFERENCE_FIELDS}
    prefs['preferences'] = {key: deepcopy(user.preferences[key]) for key in PREFERENCE_JSON_KEYS
                            if user.preferences and key in user.preferences}
    return {
        'version': USER_BACKUP_VERSION,
        'format': 'gearcargo-user',
        'source_namespace': 'gearcargo:' + user.export_namespace,
        'source_metadata': export_source_metadata(user),
        'exported_at': datetime.now(timezone.utc).isoformat(),
        'media_included': bool(include_attachments),
        'user': {'preferences': prefs},
        'vehicles': vehicles,
        **records,
        'media': [],  # ZIP writer adds explicit, hashed file references.
        'warnings': [],
    }


def _parse_storage_field(model, field, value, path):
    column = inspect(model).columns[field]
    if value is None:
        if not column.nullable and not column.primary_key:
            raise BackupSchemaError('This field cannot be null.', path)
        return None
    typ = column.type
    try:
        if isinstance(typ, DateTime):
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            return parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed
        if isinstance(typ, Date):
            return date.fromisoformat(value)
        if isinstance(typ, Boolean):
            if not isinstance(value, bool):
                raise ValueError()
        elif isinstance(typ, Integer):
            if isinstance(value, bool) or not isinstance(value, int) or not -(2**31) <= value < 2**31:
                raise ValueError()
        elif isinstance(typ, Float):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError()
        elif isinstance(typ, Numeric):
            if isinstance(value, bool):
                raise ValueError()
            number = Decimal(str(value))
            if not number.is_finite() or abs(number) >= Decimal(10) ** (typ.precision - typ.scale):
                raise ValueError()
            if number != number.quantize(Decimal(1).scaleb(-typ.scale)):
                raise ValueError()  # Do not silently round recovery data.
            return number
        elif isinstance(typ, JSON):
            # Deep-copy to keep normalization separate from the uploaded payload.
            import json
            json.dumps(value, allow_nan=False)
            return deepcopy(value)
        elif isinstance(typ, String):
            if not isinstance(value, str) or (typ.length and len(value) > typ.length):
                raise ValueError()
    except (ValueError, TypeError, AttributeError, InvalidOperation, OverflowError):
        raise BackupSchemaError('Invalid value for this field.', path) from None
    return value


def _parse_field(model, field, value, path, *, validate_domains=True):
    from app.services.domain_validation import models, validate_field
    from app.utils.entryparse import InvalidFieldError
    parsed = _parse_storage_field(model, field, value, path)
    if validate_domains and model in models():
        try:
            return validate_field(model, field, parsed, exact=True)
        except InvalidFieldError as exc:
            raise BackupSchemaError(exc.error, path) from None
    return parsed


def _list(value, path):
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise BackupSchemaError('Expected a list of records.', path)
    return value


@dataclass
class PreparedBackup:
    version: str
    records: dict
    preferences: dict
    warnings: list
    media_included: bool
    namespace: str = ''
    batch_key: str = ''
    import_format: str = 'backup'
    source_keys: dict = field(default_factory=dict)
    origins: dict = field(default_factory=dict)


def prepare_backup(data, *, validate_domains=True):
    """Validate the full payload before any data is inserted; adapt legacy DTOs.

    Legacy missing fields are reported. Missing currency/distance unit becomes
    explicit NULL (unknown), never the destination model's EUR/km default.
    """
    if not isinstance(data, dict):
        raise BackupSchemaError('Expected a backup object.')
    version = data.get('version', '1.0')
    if not isinstance(version, str) or version not in LEGACY_VERSIONS | {'4.0', '4.1', '4.2', '4.3', '4.4', '4.5', '4.6', USER_BACKUP_VERSION}:
        raise BackupSchemaError('Unsupported backup version. Use a compatible GearCargo release.', 'version')
    legacy = version in LEGACY_VERSIONS
    warnings = []
    if legacy:
        warnings.append(warning('legacy_incomplete', 'version',
            'Legacy backups omitted records and fields. Missing values cannot be recovered; review the listed gaps.'))
    elif data.get('format') != 'gearcargo-user':
        raise BackupSchemaError('Unsupported backup format.', 'format')
    allowed_root = {'version', 'format', 'exported_at', 'media_included', 'user', 'media', 'warnings'} | (set(MODELS) - set(ENTRY_COLLECTIONS))
    if version in ('4.2', '4.3', '4.4', '4.5', '4.6', USER_BACKUP_VERSION):
        allowed_root |= {'source_namespace', 'source_metadata'}
    required_root = allowed_root - {'warnings'}
    if version != USER_BACKUP_VERSION:
        required_root -= set(STATEMENT_COLLECTIONS)
    if version not in ('4.6', USER_BACKUP_VERSION):
        required_root -= set(APPOINTMENT_COLLECTIONS)
    if version not in ('4.5', '4.6', USER_BACKUP_VERSION):
        required_root -= set(TIRE_COLLECTIONS)
    if not legacy and (set(data) - allowed_root or required_root - set(data)):
        raise BackupSchemaError('Unsupported or missing backup collection or field.', 'backup')
    if legacy and set(data) - allowed_root:
        warnings.append(warning('unsupported_fields', 'backup',
                                'Unsupported legacy collections or fields were not restored.'))
    if not isinstance(data.get('media', []), list):
        raise BackupSchemaError('Expected a media inventory.', 'media')
    records = {kind: [] for kind in MODELS}
    source_vehicles = _list(data.get('vehicles', []), 'vehicles')
    for i, raw_vehicle in enumerate(source_vehicles):
        raw_vehicle = deepcopy(raw_vehicle)
        if legacy:
            raw_vehicle.setdefault('id', -(i + 1))
        records['vehicles'].append((deepcopy(raw_vehicle), f'vehicles[{i}]'))
        for kind in ENTRY_COLLECTIONS:
            for j, row in enumerate(_list(raw_vehicle.get(kind, []), f'vehicles[{i}].{kind}')):
                row = deepcopy(row)
                if legacy:
                    row['vehicle_id'] = raw_vehicle.get('id')
                elif row.get('vehicle_id') != raw_vehicle.get('id'):
                    raise BackupSchemaError('Entry vehicle does not match its containing vehicle.', f'vehicles[{i}].{kind}[{j}]')
                records[kind].append((row, f'vehicles[{i}].{kind}[{j}]'))
    for kind in MODELS:
        if kind == 'vehicles' or kind in ENTRY_COLLECTIONS:
            continue
        if ((kind in TIRE_COLLECTIONS and version not in ('4.5', '4.6', USER_BACKUP_VERSION)) or (kind in APPOINTMENT_COLLECTIONS and version not in ('4.6', USER_BACKUP_VERSION)) or (kind in STATEMENT_COLLECTIONS and version != USER_BACKUP_VERSION)) and kind not in data:
            records[kind] = []
            continue
        if not legacy and kind not in data:
            raise BackupSchemaError('Missing record collection.', kind)
        records[kind] = [(deepcopy(row), f'{kind}[{i}]') for i, row in enumerate(_list(data.get(kind, []), kind))]
    normalized = {}
    next_missing_id = -1
    for kind, rows in records.items():
        normalized[kind] = []
        used_ids = set()
        for index, (row, path) in enumerate(rows):
            if legacy:
                aliases = {'date': ('entry_date',), 'odometer': ('mileage',),
                           'amount': ('cost', 'total_price', 'total_cost'),
                           'liters': ('volume',), 'price_per_liter': ('price_per_unit',),
                           'total_price': ('total_cost',), 'full_tank': ('is_full_tank',),
                           'policy_type': ('coverage_type',), 'current_mileage': ('initial_mileage',)}
                for canonical, old_names in aliases.items():
                    if canonical not in row:
                        for old in old_names:
                            if old in row:
                                row[canonical] = row[old]
                                break
                if kind == 'todos' and 'completed' not in row and 'status' in row:
                    row['completed'] = row['status'] == 'completed'
                # Missing legacy IDs need archive-local keys for otherwise valid rows.
                if 'id' not in row:
                    row['id'] = next_missing_id
                    next_missing_id -= 1
                missing = set(FIELDS[kind]) - set(row)
                if missing:
                    warnings.append(warning('missing_fields', path,
                        'Unavailable legacy fields: ' + ', '.join(sorted(missing))))
                for field in ('currency', 'distance_unit'):
                    if field in FIELDS[kind] and field not in row:
                        row[field] = None
                if kind == 'vehicles':
                    row.setdefault('name', 'Imported Vehicle')
                # Preserve old adapter defaults, but expose them above as gaps.
                if kind in ENTRY_COLLECTIONS:
                    row.setdefault('date', date.today().isoformat())
                if kind == 'attachments':
                    row.setdefault('filename', row.get('original_filename') or 'attachment')
                for field, value in list(row.items()):
                    if field in FIELDS[kind] and isinstance(inspect(MODELS[kind]).columns[field].type, Date) and not isinstance(inspect(MODELS[kind]).columns[field].type, DateTime):
                        if isinstance(value, str) and 'T' in value:
                            try:
                                row[field] = datetime.fromisoformat(value.replace('Z', '+00:00')).date().isoformat()
                            except ValueError:
                                raise BackupSchemaError('Invalid date.', f'{path}.{field}') from None
            else:
                if kind == 'reminders' and version in ('4.0', '4.1', '4.2', '4.3'):
                    for field in ('repeat_mileage', 'recurrence_anchor_date', 'notification_state'):
                        row.setdefault(field, None)
                if kind == 'vehicles' and version in ('4.0', '4.1', '4.2'):
                    row.setdefault('purchase_currency', None)
                if version == '4.0' and kind in ('reminders', 'todos'):
                    row.setdefault('completed_from_id', None)
                extras = set(row) - set(FIELDS[kind]) - (set(ENTRY_COLLECTIONS) if kind == 'vehicles' else set())
                missing = set(FIELDS[kind]) - set(row)
                if extras or missing:
                    raise BackupSchemaError('Unsupported or missing record fields: ' + ', '.join(sorted(extras | missing)), path)
                if kind == 'vehicles' and any(k not in row for k in ENTRY_COLLECTIONS):
                    raise BackupSchemaError('Missing vehicle entry collection.', path)
            values = {field: _parse_field(MODELS[kind], field, row[field], f'{path}.{field}', validate_domains=validate_domains)
                      for field in FIELDS[kind] if field in row}
            for field in FIELDS[kind]:
                column = inspect(MODELS[kind]).columns[field]
                if field not in values and not column.nullable and column.default is None:
                    raise BackupSchemaError('Missing required record field.', f'{path}.{field}')
            source_id = values['id']
            if source_id is None or source_id == 0 or source_id in used_ids or (not legacy and source_id < 0):
                raise BackupSchemaError('Missing, duplicate or invalid record ID.', path)
            used_ids.add(source_id)
            normalized[kind].append(values)
    # Entry IDs share a single SQL table, even though the archive nests categories.
    entry_ids = [row['id'] for kind in ENTRY_COLLECTIONS for row in normalized[kind]]
    if not legacy and len(entry_ids) != len(set(entry_ids)):
        raise BackupSchemaError('Duplicate entry ID across categories.', 'vehicles')
    ids = {kind: {row['id'] for row in rows} for kind, rows in normalized.items()}
    ids['entries'] = set(entry_ids)
    for kind, rows in normalized.items():
        for row in rows:
            if kind == 'predictions' and isinstance(row.get('source_data'), dict):
                for field, target in PREDICTION_SOURCE_LINKS.items():
                    ref = row['source_data'].get(field)
                    if ref is not None and (type(ref) is not int or ref not in ids[target]):
                        path = f'predictions[id={row["id"]}].source_data.{field}'
                        if not legacy:
                            raise BackupSchemaError('Referenced record is absent from this backup.', path)
                        warnings.append(warning('unmatched_reference', path,
                            'Referenced record is absent; the metadata link will not be restored.'))
                        row['source_data'][field] = None
            for field, target in LINKS.get(kind, {}).items():
                ref = row.get(field)
                if ref is not None and ref not in ids[target]:
                    if not legacy:
                        raise BackupSchemaError('Referenced record is absent from this backup.', f'{kind}[id={row["id"]}].{field}')
                    warnings.append(warning('unmatched_reference', f'{kind}[id={row["id"]}].{field}',
                                            'Referenced record is absent; the link or record will not be restored.'))
                    # Missing parent is handled as a skipped record by importer.
                    if field != 'vehicle_id':
                        row[field] = None
            if kind == 'due_dismissals':
                target = DUE_TARGETS.get(row.get('kind'))
                if not target or row.get('ref_id') not in ids[target]:
                    raise BackupSchemaError('Unsupported or missing dismissal target.', f'due_dismissals[id={row["id"]}]')
    for kind in ('reminders', 'todos'):
        origins = [row['completed_from_id'] for row in normalized[kind] if row.get('completed_from_id') is not None]
        if len(origins) != len(set(origins)):
            raise BackupSchemaError('Multiple successors reference the same completion.', kind)
        if any(row.get('completed_from_id') == row['id'] for row in normalized[kind]):
            raise BackupSchemaError('A recurring record cannot succeed itself.', kind)
    from app.services.reconciliation import validate_backup_reconciliation
    validate_backup_reconciliation(normalized)
    from app.services.attachment_consistency import validate_archive
    validate_archive(normalized)
    from app.services.tire_lifecycle import validate_backup_tires
    validate_backup_tires(normalized)
    from app.services.appointments import validate_backup_appointments
    validate_backup_appointments(normalized)
    normalized['tire_fitments'].sort(key=lambda row: (row['date'], row['id']))
    source_user = data.get('user', {})
    if not isinstance(source_user, dict) or (not legacy and set(source_user) != {'preferences'}):
        raise BackupSchemaError('Unsupported account data.', 'user')
    prefs = source_user.get('preferences', {})
    if not isinstance(prefs, dict):
        raise BackupSchemaError('Expected preference fields.', 'user.preferences')
    allowed_prefs = set(PREFERENCE_FIELDS) | {'preferences'}
    if not legacy and set(prefs) != allowed_prefs:
        raise BackupSchemaError('Unsupported or missing account preference.', 'user.preferences')
    parsed_prefs = {k: _parse_field(User, k, v, f'user.preferences.{k}')
                    for k, v in prefs.items() if k in PREFERENCE_FIELDS}
    json_prefs = prefs.get('preferences', {})
    if not isinstance(json_prefs, dict) or (not legacy and set(json_prefs) - set(PREFERENCE_JSON_KEYS)):
        raise BackupSchemaError('Unsupported portable preference data.', 'user.preferences.preferences')
    json_prefs = _parse_field(User, 'preferences', json_prefs, 'user.preferences.preferences')
    parsed_prefs['preferences'] = {k: deepcopy(v) for k, v in json_prefs.items() if k in PREFERENCE_JSON_KEYS}
    media_included = data.get('media_included', True if legacy else False)
    if not isinstance(media_included, bool):
        raise BackupSchemaError('Expected a boolean.', 'media_included')
    from app.services.import_identity import digest
    namespace = data.get('source_namespace')
    if namespace is not None and (not isinstance(namespace, str) or not namespace or len(namespace) > 160):
        raise BackupSchemaError('Invalid source namespace.', 'source_namespace')
    prepared = PreparedBackup(version, normalized, parsed_prefs, warnings, media_included,
                              namespace=namespace or 'backup:file:' + digest(data), batch_key=digest(data))
    prepared.origins = parse_source_metadata(data.get('source_metadata', []), ids)
    return prepared


def _assign(record, values, *, inserting=False):
    """Preserve explicit NULL even on nullable columns with an ORM default."""
    for field, value in values.items():
        column = inspect(type(record)).columns[field]
        if inserting and value is None and column.default is not None and not isinstance(column.type, JSON):
            value = null()
        setattr(record, field, value)


def import_records(user, prepared, merge_mode, id_maps, attachment_paths, *, conflict_policy='reject', preview_token=None):
    """Restore an already validated record graph; caller controls commit/media IO.

    Only an owner-scoped source identity can suppress a replay. Content equality
    is advisory; changed source data requires an explicit keep-existing decision.
    """
    if merge_mode not in ('merge', 'replace'):
        raise BackupSchemaError('Unsupported merge mode.', 'merge_mode')
    warnings = list(prepared.warnings)
    summary = {kind: 0 for kind in MODELS}
    summary.update(skipped_duplicates=0, skipped_unmatched_policies=0,
                   skipped_records=0, source_version=prepared.version,
                   format_version=USER_BACKUP_VERSION, warnings=warnings,
                   media_included=prepared.media_included)
    for kind in (*MODELS, 'entries'):
        id_maps.setdefault(kind, {})
    from app.services.import_identity import ImportPlan, lock_imports
    lock_imports(user.id)
    plan = ImportPlan(user, prepared)
    plan.validate_apply(conflict_policy, preview_token)
    plan.begin(conflict_policy)
    summary.update(plan.result())
    summary['skipped_conflicts'] = 0
    created = {}
    # All links except the vehicle parent are assigned in a second pass, after
    # all archive-local IDs have destination mappings (including cycles).
    for kind, rows in prepared.records.items():
        model = MODELS[kind]
        for row in rows:
            source_id = row['id']
            fields = {k: deepcopy(v) for k, v in row.items() if k != 'id' and not k.startswith('_') and k not in LINKS.get(kind, {})}
            if kind == 'due_dismissals':
                fields.pop('ref_id', None)  # nonnullable; target available after earlier collections
                target = DUE_TARGETS[row['kind']]
                fields['ref_id'] = id_maps[target].get(row['ref_id'])
                if fields['ref_id'] is None:
                    summary['skipped_records'] += 1
                    continue
            if 'vehicle_id' in row:
                old_vehicle = row['vehicle_id']
                fields['vehicle_id'] = id_maps['vehicles'].get(old_vehicle) if old_vehicle is not None else None
                if old_vehicle is not None and fields['vehicle_id'] is None:
                    summary['skipped_records'] += 1
                    if kind == 'insurance_policies':
                        summary['skipped_unmatched_policies'] += 1
                    continue
            if kind in TIRE_COLLECTIONS + APPOINTMENT_COLLECTIONS + STATEMENT_COLLECTIONS:
                for field, target in LINKS.get(kind, {}).items():
                    if not inspect(model).columns[field].nullable and field != 'vehicle_id':
                        fields[field] = id_maps[target].get(row[field])
                        if fields[field] is None:
                            raise BackupSchemaError('Lifecycle parent is unavailable in this restore.', kind)
            decision = plan.actions[(kind, source_id)]
            if decision['action'] != 'create':
                obj = decision['target']
                if decision['action'] == 'exact_repeat':
                    summary['skipped_duplicates'] += 1
                else:
                    summary['skipped_conflicts'] += 1
                if obj is None:
                    summary['skipped_records'] += 1
                    continue
            else:
                obj = model(user_id=user.id)
                _assign(obj, fields, inserting=True)
                if kind == 'attachments':
                    from app.routes.attachments import safe_attachment_mime
                    obj.filepath = attachment_paths[source_id]
                    obj.file_type = safe_attachment_mime(row.get('original_filename') or row['filename'])
                db.session.add(obj)
                db.session.flush()
                summary[kind] += 1
                created[(kind, source_id)] = (obj, row)
            plan.remember((kind, source_id), obj)
            id_maps[kind][source_id] = obj.id
            if kind in ENTRY_COLLECTIONS:
                id_maps['entries'][source_id] = obj.id
    for (kind, source_id), (obj, row) in created.items():
        for field, target in LINKS.get(kind, {}).items():
            if field != 'vehicle_id' and field in row:
                mapped = id_maps[target].get(row[field]) if row[field] is not None else None
                if field == 'completed_from_id' and mapped is not None:
                    with db.session.no_autoflush:
                        successor = MODELS[kind].query.filter_by(completed_from_id=mapped).first()
                    if successor is not None and successor.id != obj.id:
                        raise BackupSchemaError('This completion already has a successor in the destination. Review the records or restore into an empty account.', f'{kind}[id={source_id}].{field}')
                setattr(obj, field, mapped)
        if kind == 'predictions' and isinstance(obj.source_data, dict):
            metadata = dict(obj.source_data)
            for field, target in PREDICTION_SOURCE_LINKS.items():
                if field in metadata and metadata[field] is not None:
                    metadata[field] = id_maps[target].get(metadata[field])
            obj.source_data = metadata
        # Link assignment may trigger onupdate: preserve the stored timestamp.
        if 'updated_at' in row:
            obj.updated_at = row['updated_at']
            flag_modified(obj, 'updated_at')
    for key, value in prepared.preferences.items():
        if key == 'preferences':
            user.preferences = {**(user.preferences or {}), **value}
        else:
            setattr(user, key, value)
    from app.services.fuel_efficiency import recalculate_efficiencies
    for vehicle_id in {obj.vehicle_id for (kind, _), (obj, _) in created.items() if kind == 'fuel_entries'}:
        recalculate_efficiencies(vehicle_id, user.id)
    # Rebuilding derived fields must not erase imported source timestamps.
    for (kind, _), (obj, row) in created.items():
        if kind in ('vehicles', 'fuel_entries') and 'updated_at' in row:
            obj.updated_at = row['updated_at']
            flag_modified(obj, 'updated_at')
    from app.services.tire_lifecycle import validate_vehicle
    db.session.flush()
    for vehicle_id in {obj.vehicle_id for (kind, _), (obj, _) in created.items() if kind in TIRE_COLLECTIONS}:
        validate_vehicle(vehicle_id)
    from app.services.reconciliation import validate_restored_allocations
    validate_restored_allocations(user.id)
    summary['new_records'] = len(created)
    summary['exact_repeats'] = summary['skipped_duplicates']
    return summary


def export_source_metadata(user):
    """Portable active provenance; deleted-target tombstones remain operational."""
    from app.models import ImportIdentity, ImportBatch
    from app.services.import_identity import created_stamp
    result = []
    for identity in ImportIdentity.query.filter_by(user_id=user.id).order_by(ImportIdentity.id):
        model = MODELS.get(identity.entity_kind)
        target = model.query.filter_by(id=identity.target_id, user_id=user.id).first() if model else None
        if target is None or created_stamp(target) != identity.target_created_at:
            continue
        first = db.session.get(ImportBatch, identity.first_batch_id)
        last = db.session.get(ImportBatch, identity.last_batch_id)
        inherited = next((origin for origin in first.metadata_json.get('origins', [])
                          if origin['kind'] == identity.entity_kind and origin['namespace'] == identity.namespace
                          and origin['source_id'] == identity.source_id), None)
        first_key = inherited['first_batch'] if inherited else first.batch_key
        last_key = inherited['last_batch'] if inherited and first.id == last.id else last.batch_key
        result.append(dict(kind=identity.entity_kind, target_id=identity.target_id,
            namespace=identity.namespace, source_id=identity.source_id, source_hash=identity.source_hash,
            source_payload=identity.source_payload, original_payload=identity.original_payload,
            first_batch=first_key, last_batch=last_key))
    return result


def parse_source_metadata(raw, ids):
    from app.services.import_identity import digest
    parsed, seen = {}, set()
    for row in _list(raw, 'source_metadata'):
        allowed = {'kind', 'target_id', 'namespace', 'source_id', 'source_hash', 'source_payload', 'original_payload', 'first_batch', 'last_batch'}
        if not isinstance(row, dict) or set(row) != allowed or not isinstance(row['kind'], str) or row['kind'] not in MODELS or type(row['target_id']) is not int or row['target_id'] not in ids[row['kind']]:
            raise BackupSchemaError('Invalid source metadata target.', 'source_metadata')
        if any(not isinstance(row[key], str) or not 1 <= len(row[key]) <= 160 for key in ('namespace', 'source_id')):
            raise BackupSchemaError('Invalid source identity.', 'source_metadata')
        if not isinstance(row['source_payload'], dict) or not isinstance(row['original_payload'], dict) or digest(row['source_payload']) != row['source_hash']:
            raise BackupSchemaError('Invalid source metadata fingerprint.', 'source_metadata')
        if any(not isinstance(row[key], str) or len(row[key]) != 64 or any(c not in '0123456789abcdef' for c in row[key]) for key in ('first_batch', 'last_batch', 'source_hash')):
            raise BackupSchemaError('Invalid source batch fingerprint.', 'source_metadata')
        key = (row['namespace'], row['kind'], row['source_id'])
        if key in seen:
            raise BackupSchemaError('Duplicate source identity.', 'source_metadata')
        seen.add(key)
        parsed.setdefault((row['kind'], row['target_id']), []).append(deepcopy(row))
    return parsed

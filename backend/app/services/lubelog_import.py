"""
GearCargo - LubeLogger Import Service
Parses LubeLogger backup ZIP files (containing LiteDB database) and converts
the data into GearCargo format for import.

LubeLogger (https://github.com/hargata/lubelog) uses LiteDB (.NET embedded NoSQL)
which stores data in BSON format. This module provides a self-contained BSON/LiteDB
parser that extracts vehicles, fuel records, service records, tax records, and reminders.
"""

import struct
import json
import hashlib
import zipfile
import os
from datetime import date, datetime, timezone
from decimal import Decimal
from app.utils.timeutils import utc_today


# ──────────────────────────────────────────────
#  BSON Parser (self-contained, no dependencies)
# ──────────────────────────────────────────────

def _read_cstring(data, offset):
    """Read a null-terminated C string from data."""
    end = data.index(b'\x00', offset)
    return data[offset:end].decode('utf-8', errors='replace'), end + 1


def _decode_dotnet_decimal(raw_bytes):
    """Decode a .NET decimal stored as 16 bytes in BSON Decimal128 format.

    .NET decimal layout: lo(4) + mid(4) + hi(4) + flags(4)
    - lo/mid/hi form a 96-bit unsigned integer mantissa
    - flags: bit 31 = sign, bits 16-23 = scale (0-28)
    - value = (-1)^sign * mantissa / 10^scale
    """
    if len(raw_bytes) != 16:
        return 0.0
    lo = struct.unpack_from('<I', raw_bytes, 0)[0]
    mid = struct.unpack_from('<I', raw_bytes, 4)[0]
    hi = struct.unpack_from('<I', raw_bytes, 8)[0]
    flags = struct.unpack_from('<I', raw_bytes, 12)[0]

    scale = (flags >> 16) & 0xFF
    sign = (flags >> 31) & 1

    mantissa = lo + (mid << 32) + (hi << 64)
    value = Decimal(mantissa) / Decimal(10 ** scale)
    if sign:
        value = -value
    return float(value)


def _parse_bson_document(data, offset, max_len=None):
    """Parse a single BSON document at the given offset.

    Returns (dict, bytes_consumed) or (None, 0) on failure.
    """
    try:
        doc_len = struct.unpack_from('<i', data, offset)[0]
        if doc_len < 5 or (max_len and doc_len > max_len):
            return None, 0
        if offset + doc_len > len(data):
            return None, 0
        if data[offset + doc_len - 1] != 0x00:
            return None, 0

        result = {}
        pos = offset + 4
        end = offset + doc_len - 1

        while pos < end:
            bson_type = data[pos]
            pos += 1
            if pos >= end:
                break

            field_name, pos = _read_cstring(data, pos)

            if bson_type == 0x01:  # double
                result[field_name] = struct.unpack_from('<d', data, pos)[0]
                pos += 8

            elif bson_type == 0x02:  # string
                str_len = struct.unpack_from('<i', data, pos)[0]
                pos += 4
                result[field_name] = data[pos:pos + str_len - 1].decode('utf-8', errors='replace')
                pos += str_len

            elif bson_type == 0x03:  # embedded document
                sub_doc, sub_len = _parse_bson_document(data, pos, doc_len)
                result[field_name] = sub_doc if sub_doc else {}
                pos += sub_len

            elif bson_type == 0x04:  # array (stored as document with "0", "1", ... keys)
                arr_doc, arr_len = _parse_bson_document(data, pos, doc_len)
                result[field_name] = list(arr_doc.values()) if arr_doc else []
                pos += arr_len

            elif bson_type == 0x05:  # binary
                bin_len = struct.unpack_from('<i', data, pos)[0]
                pos += 4 + 1 + bin_len  # length + subtype + data

            elif bson_type == 0x08:  # boolean
                result[field_name] = data[pos] != 0
                pos += 1

            elif bson_type == 0x09:  # UTC datetime (int64 milliseconds since epoch)
                ts_ms = struct.unpack_from('<q', data, pos)[0]
                try:
                    result[field_name] = datetime.fromtimestamp(
                        ts_ms / 1000, tz=timezone.utc
                    ).replace(tzinfo=None)
                except (OSError, ValueError):
                    result[field_name] = None
                pos += 8

            elif bson_type == 0x0A:  # null
                result[field_name] = None

            elif bson_type == 0x10:  # int32
                result[field_name] = struct.unpack_from('<i', data, pos)[0]
                pos += 4

            elif bson_type == 0x12:  # int64
                result[field_name] = struct.unpack_from('<q', data, pos)[0]
                pos += 8

            elif bson_type == 0x13:  # Decimal128 (.NET decimal in LiteDB)
                raw = data[pos:pos + 16]
                result[field_name] = _decode_dotnet_decimal(raw)
                pos += 16

            else:
                # Unknown type — stop parsing this document
                break

        return result, doc_len

    except (struct.error, ValueError, IndexError):
        return None, 0


def scan_bson_documents(raw_data):
    """Scan raw binary data for valid BSON documents containing an _id field.

    LiteDB stores BSON documents across 8 KB pages. This scanner finds them
    by brute-force checking every byte offset for a valid BSON header.
    """
    docs = []
    seen = set()
    i = 0
    data_len = len(raw_data)

    while i < data_len - 5:
        doc_len = struct.unpack_from('<i', raw_data, i)[0]
        if 10 <= doc_len <= 8192 and i + doc_len <= data_len:
            if raw_data[i + doc_len - 1] == 0x00:
                doc, consumed = _parse_bson_document(raw_data, i, doc_len + 4)
                if doc and len(doc) >= 2 and '_id' in doc:
                    key = (doc.get('_id'), frozenset(doc.keys()))
                    if key not in seen:
                        seen.add(key)
                        docs.append(doc)
                        i += consumed
                        continue
        i += 1

    return docs


# ──────────────────────────────────────────
#  LubeLogger Record Classification
# ──────────────────────────────────────────

def classify_documents(docs):
    """Classify parsed BSON documents into LubeLogger record types.

    LubeLogger collections:
    - vehicles: Make, Model, Year, LicensePlate
    - taxrecords: VehicleId, IsRecurring, RecurringInterval, Description (Road Tax / Insurance)
    - servicerecords: VehicleId, RequisitionHistory, Mileage, Cost
    - gasrecords: VehicleId, Gallons, IsFillToFull, Cost
    - collisionrecords: VehicleId, Cost (no RequisitionHistory, no Gallons, no IsRecurring)
    - reminderrecords: ReminderMileageInterval, ReminderMonthInterval
    """
    result = {
        'vehicles': [],
        'tax_records': [],
        'service_records': [],
        'gas_records': [],
        'collision_records': [],
        'reminder_records': [],
    }

    for doc in docs:
        keys = set(doc.keys())

        if 'Make' in keys or ('Year' in keys and 'LicensePlate' in keys):
            result['vehicles'].append(doc)
        elif 'Gallons' in keys or 'IsFillToFull' in keys:
            result['gas_records'].append(doc)
        elif 'IsRecurring' in keys and 'RecurringInterval' in keys:
            result['tax_records'].append(doc)
        elif 'RequisitionHistory' in keys:
            result['service_records'].append(doc)
        elif 'ReminderMileageInterval' in keys:
            result['reminder_records'].append(doc)
        elif 'VehicleId' in keys and 'Cost' in keys:
            result['collision_records'].append(doc)

    return result


# ──────────────────────────────────────────
#  Data Mapping: LubeLogger → GearCargo
# ──────────────────────────────────────────

def _parse_date(value):
    """Safely parse a date from a datetime or string."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None or value == '':
        return datetime.now(timezone.utc).date()
    from app.utils.entryparse import parse_iso_date
    return parse_iso_date(value)


def _safe_float(value, default=0, field=None):
    """Absent vendor values keep their default; malformed values are never zeroed."""
    from app.utils.entryparse import parse_amount, InvalidFieldError
    try:
        return parse_amount(default if value is None else value)
    except InvalidFieldError as exc:
        exc.field = field
        raise


def parse_lubelog_backup(zip_data):
    """Parse a LubeLogger backup ZIP file.

    Args:
        zip_data: BytesIO or file-like object containing the ZIP

    Returns:
        dict with parsed data organized by type, plus file references
    """
    with zipfile.ZipFile(zip_data, 'r') as zf:
        names = zf.namelist()

        # Find the LiteDB database file
        db_file = None
        for name in names:
            if name.endswith('.db') and 'cartracker' in name.lower():
                db_file = name
                break
        # Fallback: any .db file in data/
        if not db_file:
            for name in names:
                if name.startswith('data/') and name.endswith('.db'):
                    db_file = name
                    break

        if not db_file:
            raise ValueError('No LiteDB database found in backup ZIP')

        # Read and parse the database
        raw_data = zf.read(db_file)
        docs = scan_bson_documents(raw_data)
        classified = classify_documents(docs)

        # Read user config if present
        config = {}
        for name in names:
            if 'userConfig.json' in name:
                try:
                    config = json.loads(zf.read(name).decode('utf-8'))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass
                break

        # Catalog document/image files in the ZIP
        available_files = {}
        for name in names:
            if name.startswith(('documents/', 'images/')):
                # Map LubeLogger path to ZIP entry name
                available_files['/' + name] = name

        return {
            'classified': classified,
            'config': config,
            'available_files': available_files,
            'zip_ref': zf if False else None,  # We'll re-open later for file extraction
        }




def map_to_gearcargo(classified, config=None, distance_unit=None, source_volume_unit=None, source_distance_unit=None):
    """Convert classified LubeLogger data to GearCargo-compatible import format.

    Args:
        classified: Classified LubeLogger documents.
        config: LubeLogger userConfig.json data.
        distance_unit: Target distance unit ('km' or 'miles'). If provided,
            overrides the LubeLogger config. Odometer values will be converted
            if the source and target units differ.
        source_volume_unit: liters, us_gallons or imperial_gallons; required for MPG.
        source_distance_unit: km or miles; overrides config, required if missing.

    Returns a dict matching the GearCargo backup JSON structure that can be
    processed by the existing import_backup_data() function.
    """
    from app.utils.units import distance_unit as normalize_distance, convert_odometer, volume_to_liters
    from app.utils.entryparse import InvalidFieldError
    declared_mpg = (config or {}).get('UseMPG')
    if declared_mpg is not None and not isinstance(declared_mpg, bool):
        raise InvalidFieldError('validation.invalidValue', 'Invalid source unit setting', 'UseMPG')
    source_unit = source_distance_unit or ('miles' if declared_mpg else 'km')
    target_unit = distance_unit or source_unit
    if normalize_distance(source_unit) is None or normalize_distance(target_unit) is None:
        raise InvalidFieldError('validation.invalidValue', 'Choose source and target distance units', 'distance_unit')
    # A metric declaration identifies litres. MPG never identifies US versus
    # imperial gallons; missing source configuration is likewise ambiguous.
    if classified.get('gas_records') and source_volume_unit is None:
        if declared_mpg is False:
            source_volume_unit = 'liters'
        else:
            raise InvalidFieldError('backup.sourceVolumeRequired',
                                    'Choose the fuel volume unit used in the source backup', 'source_volume_unit')
    source_volume_unit = source_volume_unit or 'liters'
    volume_to_liters(0, source_volume_unit)  # validate even an empty backup
    if (declared_mpg is None and source_distance_unit is None
            and any(record.get('Mileage') is not None for kind in ('gas_records', 'service_records', 'collision_records', 'reminder_records')
                    for record in classified.get(kind, []))):
        raise InvalidFieldError('backup.sourceDistanceRequired',
                                'Choose the odometer unit used in the source backup', 'source_distance_unit')

    def source_note(notes, mileage, volume=None):
        parts = []
        if source_unit != target_unit:
            parts.append(f'Source odometer: {mileage} {source_unit}')
        if volume is not None and source_volume_unit != 'liters':
            label = {'us_gallons': 'US gal', 'imperial_gallons': 'imperial gal'}[source_volume_unit]
            parts.append(f'Source fuel volume: {volume} {label}')
        return '\n\n'.join(filter(None, [notes, '; '.join(parts)])) or None

    gearcargo_data = {
        'version': '2.0',
        'source': 'lubelog',
        'unit_conversion': {'source_distance_unit': source_unit, 'target_distance_unit': target_unit,
                            'source_volume_unit': source_volume_unit, 'stored_volume_unit': 'liters'},
        'exported_at': datetime.now(timezone.utc).isoformat(),
        'vehicles': [],
        'reminders': [],
        'insurance_policies': [],
        'todos': [],
        'attachments': [],
    }

    # Map vehicle IDs from LubeLogger to their data
    vehicle_map = {}
    for v in classified['vehicles']:
        ll_id = v.get('_id', 1)
        is_diesel = v.get('IsDiesel', False)
        is_electric = v.get('IsElectric', False)

        fuel_type = 'petrol'
        if is_diesel:
            fuel_type = 'diesel'
        elif is_electric:
            fuel_type = 'electric'

        vehicle_data = {
            'lubelog_id': ll_id,
            '_source_id': v.get('_id'),
            'name': f"{v.get('Year', '')} {v.get('Make', '')} {v.get('Model', '')}".strip() or 'Imported Vehicle',
            'make': v.get('Make'),
            'model': v.get('Model'),
            'year': v.get('Year'),
            'license_plate': v.get('LicensePlate'),
            'fuel_type': fuel_type,
            'distance_unit': target_unit,
            'photo': v.get('ImageLocation'),
            'fuel_entries': [],
            'service_entries': [],
            'repair_entries': [],
            'tax_entries': [],
            'parking_entries': [],
        }
        vehicle_map[ll_id] = vehicle_data
        gearcargo_data['vehicles'].append(vehicle_data)

    # If no vehicles found, create a placeholder
    if not vehicle_map:
        vehicle_map[1] = {
            'lubelog_id': 1,
            'name': 'Imported Vehicle',
            'distance_unit': target_unit,
            'fuel_entries': [],
            'service_entries': [],
            'repair_entries': [],
            'tax_entries': [],
            'parking_entries': [],
        }
        gearcargo_data['vehicles'].append(vehicle_map[1])

    # Track highest mileage per vehicle
    max_mileage = {}

    # R4-14: a record whose VehicleId is not in the backup is dropped below. That
    # is the right call — inventing a vehicle for it would be worse — but it used
    # to happen silently, so the user was told "import completed" while some of
    # their history was discarded. Counted here and reported back.
    skipped_unmatched_records = 0

    # ── Gas records → Fuel entries ──
    for rec in classified['gas_records']:
        vid = rec.get('VehicleId', 1)
        vehicle = vehicle_map.get(vid)
        if not vehicle:
            skipped_unmatched_records += 1
            continue

        from app.services.domain_validation import validate_field
        from app.models import FuelEntry
        raw_mileage = validate_field(FuelEntry, 'odometer', rec.get('Mileage'))
        mileage = convert_odometer(raw_mileage, source_unit, target_unit)
        if mileage and mileage > max_mileage.get(vid, 0):
            max_mileage[vid] = mileage

        # LubeLogger "Gallons" is actually liters when using metric
        raw_volume = _safe_float(rec.get('Gallons'), field='Gallons')
        liters = validate_field(FuelEntry, 'liters', volume_to_liters(raw_volume, source_volume_unit))
        total_cost = validate_field(FuelEntry, 'amount', _safe_float(rec.get('Cost'), field='Cost'))
        price_per_liter = round(total_cost / liters, 3) if liters > 0 else 0

        entry_date = _parse_date(rec.get('Date'))

        fuel_entry = {
            '_source_id': rec.get('_id'),
            'date': entry_date.isoformat(),
            'odometer': mileage,
            'amount': total_cost,
            'total_price': total_cost,
            'liters': liters,
            'price_per_liter': price_per_liter,
            'full_tank': rec.get('IsFillToFull', True),
            'notes': source_note(rec.get('Notes'), raw_mileage, raw_volume),
            '_lubelog_files': rec.get('Files', []),
        }
        vehicle['fuel_entries'].append(fuel_entry)

    # ── Tax records → Tax entries + Insurance policies ──
    # LubeLogger stores both taxes and insurance in taxrecords
    insurance_groups = {}  # Group insurance payments by vehicle

    for rec in classified['tax_records']:
        vid = rec.get('VehicleId', 1)
        vehicle = vehicle_map.get(vid)
        if not vehicle:
            skipped_unmatched_records += 1
            continue

        description = (rec.get('Description') or '').strip()
        cost = _safe_float(rec.get('Cost'), field='Cost')
        entry_date = _parse_date(rec.get('Date'))
        is_recurring = rec.get('IsRecurring', False)

        if 'insurance' in description.lower():
            # Group insurance payments to create an insurance policy
            group_key = (vid, description)
            if group_key not in insurance_groups:
                insurance_groups[group_key] = {
                    'vehicle_lubelog_id': vid,
                    'payments': [],
                    'description': description,
                    'files': rec.get('Files', []),
                }
            insurance_groups[group_key]['payments'].append({
                'date': entry_date,
                'cost': cost,
                'is_recurring': is_recurring,
            })
        else:
            # Regular tax entry (Road Tax, MOT, etc.)
            tax_type = 'road_tax'
            if 'mot' in description.lower():
                tax_type = 'inspection'
            elif 'registration' in description.lower():
                tax_type = 'registration'
            elif 'emission' in description.lower():
                tax_type = 'emissions'

            tax_entry = {
                '_source_id': rec.get('_id'),
                'date': entry_date.isoformat(),
                'amount': cost,
                'tax_type': tax_type,
                'title': description,
                'description': description,
                'status': 'paid',
                'recurring': is_recurring,
                'recurrence_type': _map_interval(rec.get('RecurringInterval')),
                '_lubelog_files': rec.get('Files', []),
            }
            vehicle['tax_entries'].append(tax_entry)

    # Create insurance policies from grouped payments
    for (vid, desc), group in insurance_groups.items():
        payments = sorted(group['payments'], key=lambda p: p['date'])
        if not payments:
            continue

        avg_premium = sum(p['cost'] for p in payments) / len(payments)
        start_date = payments[0]['date']
        end_date = payments[-1]['date']

        # Determine payment frequency from payment intervals
        frequency = 'monthly'
        if len(payments) >= 2:
            avg_days = (end_date - start_date).days / (len(payments) - 1)
            if avg_days > 300:
                frequency = 'annual'
            elif avg_days > 80:
                frequency = 'quarterly'

        policy = {
            'vehicle_lubelog_id': vid,
            'provider': group['description'],
            'policy_type': 'comprehensive',
            'premium': avg_premium,
            'payment_frequency': frequency,
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'status': 'active' if end_date >= utc_today() else 'expired',
            'notes': f'Imported from LubeLogger. {len(payments)} payment(s) found.',
            '_lubelog_files': group.get('files', []),
        }
        gearcargo_data['insurance_policies'].append(policy)

    # ── Service records → Service entries ──
    for rec in classified['service_records']:
        vid = rec.get('VehicleId', 1)
        vehicle = vehicle_map.get(vid)
        if not vehicle:
            skipped_unmatched_records += 1
            continue

        from app.services.domain_validation import validate_field
        from app.models import FuelEntry
        raw_mileage = validate_field(FuelEntry, 'odometer', rec.get('Mileage'))
        mileage = convert_odometer(raw_mileage, source_unit, target_unit)
        if mileage and mileage > max_mileage.get(vid, 0):
            max_mileage[vid] = mileage

        description = rec.get('Description', '')
        cost = _safe_float(rec.get('Cost'), field='Cost')
        entry_date = _parse_date(rec.get('Date'))

        # Guess service type from description
        service_type = _guess_service_type(description)

        service_entry = {
            '_source_id': rec.get('_id'),
            'date': entry_date.isoformat(),
            'odometer': mileage,
            'amount': cost,
            'service_type': service_type,
            'description': description,
            'notes': source_note(rec.get('Notes'), raw_mileage),
            '_lubelog_files': rec.get('Files', []),
        }
        vehicle['service_entries'].append(service_entry)

    # ── Collision records → Repair entries ──
    for rec in classified['collision_records']:
        vid = rec.get('VehicleId', 1)
        vehicle = vehicle_map.get(vid)
        if not vehicle:
            skipped_unmatched_records += 1
            continue

        from app.services.domain_validation import validate_field
        from app.models import FuelEntry
        raw_mileage = validate_field(FuelEntry, 'odometer', rec.get('Mileage'))
        mileage = convert_odometer(raw_mileage, source_unit, target_unit)
        if mileage and mileage > max_mileage.get(vid, 0):
            max_mileage[vid] = mileage

        description = rec.get('Description', '')
        cost = _safe_float(rec.get('Cost'), field='Cost')
        entry_date = _parse_date(rec.get('Date'))

        repair_entry = {
            '_source_id': rec.get('_id'),
            'date': entry_date.isoformat(),
            'odometer': mileage,
            'amount': cost,
            'repair_type': 'collision',
            'description': description,
            'notes': source_note(rec.get('Notes'), raw_mileage),
            '_lubelog_files': rec.get('Files', []),
        }
        vehicle['repair_entries'].append(repair_entry)

    # ── Reminder records → Reminders ──
    for rec in classified['reminder_records']:
        vid = rec.get('VehicleId', 1)
        due_date = _parse_date(rec.get('Date'))
        description = rec.get('Description', 'Reminder')
        is_recurring = rec.get('IsRecurring', False)

        from app.services.domain_validation import validate_field
        from app.models import Reminder
        raw_due_mileage = validate_field(Reminder, 'due_mileage', rec.get('Mileage'))
        reminder = {
            '_source_id': rec.get('_id'),
            'title': description,
            'due_mileage': convert_odometer(raw_due_mileage, source_unit, target_unit),
            'description': f'Imported from LubeLogger. Source mileage: {raw_due_mileage} {source_unit}',
            'reminder_type': _guess_reminder_type(description),
            'due_date': due_date.isoformat(),
            'priority': 'medium',
            'recurring': is_recurring,
            'vehicle_lubelog_id': vid,
        }
        gearcargo_data['reminders'].append(reminder)

    gearcargo_data['skipped_unmatched_records'] = skipped_unmatched_records

    # Set vehicle mileage from highest odometer reading
    for vehicle_data in gearcargo_data['vehicles']:
        ll_id = vehicle_data.get('lubelog_id', 1)
        if ll_id in max_mileage:
            vehicle_data['current_mileage'] = max_mileage[ll_id]

    # Preflight every mapped record before rows or attachment files are written.
    from app.services.domain_validation import validate_field
    from app.services.backup_schema import MODELS, ENTRY_COLLECTIONS
    def normalize(kind, record):
        model = MODELS[kind]
        for field in list(record):
            if field in model.__mapper__.columns:
                parsed = validate_field(model, field, record[field])
                record[field] = parsed.isoformat() if isinstance(parsed, (date, datetime)) else parsed
    for vehicle in gearcargo_data['vehicles']:
        normalize('vehicles', vehicle)
        for kind in ENTRY_COLLECTIONS:
            for record in vehicle.get(kind, []):
                normalize(kind, record)
    for kind in ('reminders', 'insurance_policies'):
        for record in gearcargo_data[kind]:
            normalize(kind, record)
    return gearcargo_data


def _map_interval(lubelog_interval):
    """Map LubeLogger RecurringInterval to GearCargo recurrence_type."""
    mapping = {
        'OneMonth': 'monthly',
        'TwoMonths': 'monthly',
        'ThreeMonths': 'quarterly',
        'SixMonths': 'semi_annual',
        'OneYear': 'annual',
    }
    return mapping.get(lubelog_interval, 'monthly')


def _guess_service_type(description):
    """Guess GearCargo service_type from LubeLogger description."""
    desc_lower = (description or '').lower()
    if 'oil' in desc_lower:
        return 'oil_change'
    if 'brake' in desc_lower or 'disk' in desc_lower or 'pad' in desc_lower:
        return 'brake_service'
    if 'tire' in desc_lower or 'tyre' in desc_lower:
        return 'tire_rotation'
    # R4-37: every branch must return a member of VALID_SERVICE_TYPES. These
    # three used to emit 'battery', 'filter_change' and 'suspension', which the
    # health endpoint's component map does not know — imported rows under them
    # never counted towards a component's wear. 'battery' and 'suspension' have
    # no service-type equivalent, so they fall through to 'other'; the health
    # check still picks them up from the description via SERVICE_KEYWORDS.
    if 'battery' in desc_lower:
        return 'other'
    if 'mot' in desc_lower:
        return 'inspection'
    if 'filter' in desc_lower:
        return 'air_filter'
    if 'full service' in desc_lower or 'service' in desc_lower:
        return 'full_service'
    if 'suspension' in desc_lower:
        return 'other'
    return 'other'


def _guess_reminder_type(description):
    """Guess GearCargo reminder_type from LubeLogger description."""
    desc_lower = (description or '').lower()
    if 'mot' in desc_lower or 'inspection' in desc_lower:
        return 'inspection'
    if 'insurance' in desc_lower:
        return 'insurance'
    if 'service' in desc_lower or 'maintenance' in desc_lower:
        return 'maintenance'
    return 'custom'


# ──────────────────────────────────────────
#  Import Execution
# ──────────────────────────────────────────

def import_lubelog_to_gearcargo(user, zip_data, merge_mode='merge', distance_unit=None,
                                source_volume_unit=None, source_distance_unit=None,
                                source_label=None, preview=False, conflict_policy='reject', preview_token=None):
    """Adapt external IDs/files, then use the shared identity and restore transaction."""
    from copy import deepcopy
    from app import db
    from app.models import Vehicle
    from app.services import restore_transaction as restore_tx
    from app.services.backup_schema import prepare_backup, ENTRY_COLLECTIONS
    from app.services.import_identity import digest, namespace_for, ImportPlan
    from app.routes.backup import _check_zip_budget, _perform_personal_restore
    from app.utils.units import distance_unit as normalize_distance
    from app.utils.entryparse import InvalidFieldError

    zip_data.seek(0)
    with restore_tx.activity_guard(exclusive=True), zipfile.ZipFile(zip_data, 'r') as zf:
        _check_zip_budget(zf)
        names = zf.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate archive member names.')
        db_file = next((name for name in names if name.endswith('.db')), None)
        if not db_file:
            return {'error': 'No database file found in backup ZIP'}
        raw_data = zf.read(db_file)
        classified = classify_documents(scan_bson_documents(raw_data))
        config = {}
        for name in names:
            if 'userConfig.json' in name:
                try:
                    config = json.loads(zf.read(name).decode('utf-8'))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass
                break
        unit_options = {}
        if source_volume_unit is not None:
            unit_options['source_volume_unit'] = source_volume_unit
        if source_distance_unit is not None:
            unit_options['source_distance_unit'] = source_distance_unit
        mapped = map_to_gearcargo(classified, config, distance_unit=distance_unit, **unit_options)
        # Keep GC-015's existing diagnostic before any provenance or file write.
        for vehicle in mapped['vehicles']:
            existing = Vehicle.query.filter_by(user_id=user.id, license_plate=vehicle['license_plate']).first() if vehicle.get('license_plate') else None
            if existing and normalize_distance(existing.distance_unit) != normalize_distance(vehicle.get('distance_unit', 'km')):
                raise InvalidFieldError('backup.distanceUnitMismatch',
                                        'Imported distance unit must match the existing vehicle', 'distance_unit')
        file_hash = digest([(name, hashlib.sha256(zf.read(name)).hexdigest()) for name in sorted(names) if not name.endswith('/')])
        namespace = namespace_for('lubelog', source_label, file_hash)
        data = {'version': '2.0', 'vehicles': [], 'reminders': [], 'insurance_policies': [], 'attachments': []}
        source_keys, vehicles, file_refs, media, photos = {}, {}, {}, {}, {}
        next_id = 0
        def identify(kind, record, source_id=None, owner=None):
            nonlocal next_id
            next_id += 1
            record['id'] = next_id
            if source_id is None:
                key = ('lubelog:file:' + file_hash, str(next_id))
            else:
                key = (namespace, str(source_id) if owner is None else f'{owner}:{source_id}')
            if len(key[1]) > 160:
                raise ValueError('Source record ID is too long.')
            source_keys[(kind, next_id)] = key
            return next_id
        def files_for(record, kind, vehicle_id, entry_id=None):
            for item in record.get('_lubelog_files', []):
                location = item.get('Location', '').lstrip('/')
                if location:
                    file_refs.setdefault(location, []).append((kind, record['id'], vehicle_id, entry_id, item.get('Name')))
        for raw_vehicle in mapped['vehicles']:
            vehicle = deepcopy(raw_vehicle)
            source_id = vehicle.get('lubelog_id')
            vehicle_id = identify('vehicles', vehicle, vehicle.get('_source_id'))
            vehicles[source_id] = vehicle_id
            vehicle.setdefault('distance_unit', distance_unit or 'km')
            vehicle.setdefault('current_mileage', 0)
            if vehicle.get('photo'):
                photos[vehicle['photo'].lstrip('/')] = vehicle_id
            for kind in ENTRY_COLLECTIONS:
                for entry in vehicle.get(kind, []):
                    identify(kind, entry, entry.get('_source_id'), source_id)
                    entry['vehicle_id'] = vehicle_id
                    entry.setdefault('currency', 'EUR')  # existing LubeLogger contract
                    if kind == 'fuel_entries':
                        entry.setdefault('title', 'Fuel')
                    elif kind in ('service_entries', 'repair_entries'):
                        entry.setdefault('title', entry.get('description'))
                    files_for(entry, kind, vehicle_id, entry['id'])
            data['vehicles'].append(vehicle)
        unmatched_policies = 0
        for kind in ('reminders', 'insurance_policies'):
            for source in mapped.get(kind, []):
                source_vehicle = source.get('vehicle_lubelog_id')
                if source_vehicle not in vehicles:
                    unmatched_policies += kind == 'insurance_policies'
                    continue
                row = deepcopy(source)
                identify(kind, row, row.get('_source_id'), source_vehicle)
                row['vehicle_id'] = vehicles[source_vehicle]
                if kind == 'reminders':
                    row.pop('recurring', None)  # retain the existing adapter's contract
                files_for(row, kind, row['vehicle_id'])
                data[kind].append(row)
        for member in sorted(set(file_refs) | set(photos)):
            if member not in names or not member.startswith(('documents/', 'images/')):
                raise ValueError('A referenced source file is missing from the LubeLogger archive.')
            content = zf.read(member)
            checksum = hashlib.sha256(content).hexdigest()
            references = file_refs.get(member) or [('vehicles', photos[member], photos[member], None, None)]
            for parent_kind, parent_id, vehicle_id, entry_id, display_name in references:
                row = dict(filename=os.path.basename(member), original_filename=display_name or os.path.basename(member),
                           vehicle_id=vehicle_id, entry_id=entry_id, file_size=len(content), category='receipt' if entry_id else 'document',
                           description='Imported from LubeLogger')
                parent_key = source_keys[(parent_kind, parent_id)]
                identify('attachments', row, digest([parent_key, parent_kind, member]))
                row['_content_sha256'] = checksum
                data['attachments'].append(row)
                media[('attachments', row['id'])] = dict(collection='attachments', record_id=row['id'], member=member, sha256=checksum, size=len(content))
            if member in photos:
                media[('vehicles', photos[member])] = dict(collection='vehicles', record_id=photos[member], member=member, sha256=checksum, size=len(content))
        prepared = prepare_backup(data)
        # Missing full-backup-only fields are expected in this external adapter.
        prepared.warnings = [warning for warning in prepared.warnings if warning['code'] not in ('legacy_incomplete', 'missing_fields')]
        prepared.namespace, prepared.source_keys = namespace, source_keys
        prepared.batch_key = digest({'file': file_hash, 'namespace': namespace, 'units': mapped.get('unit_conversion')})
        # Archive-local IDs are reassigned during adaptation. Fingerprints use
        # stable source references so adding a row cannot change another car's identity.
        entry_kinds = {row['id']: kind for kind in ENTRY_COLLECTIONS for row in prepared.records[kind]}
        for kind, rows in prepared.records.items():
            for row in rows:
                refs = {}
                for field, target_kind in (('vehicle_id', 'vehicles'), ('entry_id', entry_kinds.get(row.get('entry_id')))):
                    if row.get(field) is not None and target_kind:
                        parent_namespace, parent_id = source_keys[(target_kind, row[field])]
                        refs[field] = [parent_namespace, target_kind, parent_id]
                row['_source_refs'] = refs
        prepared.import_format = 'lubelog'
        prepared.conflict_policy, prepared.preview_token = conflict_policy, preview_token
        prepared.media_included = bool(media)
        # Bytes belong to attachment identity checks, not expense identity.
        from app.routes.backup import _fingerprint_media
        _fingerprint_media(prepared, media)
        plan = ImportPlan(user, prepared)
        if preview:
            return {'preview': plan.preview}
        plan.validate_apply(conflict_policy, preview_token)
        result = _perform_personal_restore(user, data, prepared, merge_mode, media, zf).get_json()
        imported = result['imported']
        imported['skipped_unmatched_records'] = mapped.get('skipped_unmatched_records', 0)
        imported['skipped_unmatched_policies'] += unmatched_policies
        return {'success': True, 'imported': imported, 'summary': {
            'source': 'LubeLogger', 'unit_conversion': mapped.get('unit_conversion'),
            **{kind: imported[kind] for kind in ('vehicles', 'fuel_entries', 'service_entries', 'repair_entries', 'tax_entries', 'insurance_policies', 'reminders', 'attachments')},
            'total_entries': sum(imported[kind] for kind in ENTRY_COLLECTIONS),
        }}

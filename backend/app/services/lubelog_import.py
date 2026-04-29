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
import zipfile
import os
import uuid
import shutil
from datetime import datetime, timezone, date
from decimal import Decimal


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
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00')).date()
        except (ValueError, TypeError):
            pass
    return datetime.now(timezone.utc).date()


def _safe_float(value, default=0.0):
    """Safely convert a value to float."""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


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


KM_TO_MILES = 0.621371
MILES_TO_KM = 1.60934


def map_to_gearcargo(classified, config=None, distance_unit=None):
    """Convert classified LubeLogger data to GearCargo-compatible import format.

    Args:
        classified: Classified LubeLogger documents.
        config: LubeLogger userConfig.json data.
        distance_unit: Target distance unit ('km' or 'miles'). If provided,
            overrides the LubeLogger config. Odometer values will be converted
            if the source and target units differ.

    Returns a dict matching the GearCargo backup JSON structure that can be
    processed by the existing import_backup_data() function.
    """
    source_uses_miles = config.get('UseMPG', False) if config else False
    target_unit = distance_unit or ('miles' if source_uses_miles else 'km')

    # Determine if we need to convert odometer values
    source_unit = 'miles' if source_uses_miles else 'km'
    need_conversion = source_unit != target_unit
    if need_conversion:
        if target_unit == 'miles':
            odo_factor = KM_TO_MILES
        else:
            odo_factor = MILES_TO_KM
    else:
        odo_factor = 1.0

    gearcargo_data = {
        'version': '2.0',
        'source': 'lubelog',
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
            'fuel_entries': [],
            'service_entries': [],
            'repair_entries': [],
            'tax_entries': [],
            'parking_entries': [],
        }
        gearcargo_data['vehicles'].append(vehicle_map[1])

    # Track highest mileage per vehicle
    max_mileage = {}

    # ── Gas records → Fuel entries ──
    for rec in classified['gas_records']:
        vid = rec.get('VehicleId', 1)
        vehicle = vehicle_map.get(vid)
        if not vehicle:
            continue

        raw_mileage = rec.get('Mileage', 0)
        mileage = round(raw_mileage * odo_factor) if raw_mileage else 0
        if mileage and mileage > max_mileage.get(vid, 0):
            max_mileage[vid] = mileage

        # LubeLogger "Gallons" is actually liters when using metric
        liters = _safe_float(rec.get('Gallons'))
        total_cost = _safe_float(rec.get('Cost'))
        price_per_liter = round(total_cost / liters, 3) if liters > 0 else 0

        entry_date = _parse_date(rec.get('Date'))

        fuel_entry = {
            'date': entry_date.isoformat(),
            'odometer': mileage,
            'amount': total_cost,
            'total_price': total_cost,
            'liters': liters,
            'price_per_liter': price_per_liter,
            'full_tank': rec.get('IsFillToFull', True),
            'notes': rec.get('Notes'),
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
            continue

        description = (rec.get('Description') or '').strip()
        cost = _safe_float(rec.get('Cost'))
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
            'status': 'active' if end_date >= date.today() else 'expired',
            'notes': f'Imported from LubeLogger. {len(payments)} payment(s) found.',
            '_lubelog_files': group.get('files', []),
        }
        gearcargo_data['insurance_policies'].append(policy)

    # ── Service records → Service entries ──
    for rec in classified['service_records']:
        vid = rec.get('VehicleId', 1)
        vehicle = vehicle_map.get(vid)
        if not vehicle:
            continue

        raw_mileage = rec.get('Mileage', 0)
        mileage = round(raw_mileage * odo_factor) if raw_mileage else 0
        if mileage and mileage > max_mileage.get(vid, 0):
            max_mileage[vid] = mileage

        description = rec.get('Description', '')
        cost = _safe_float(rec.get('Cost'))
        entry_date = _parse_date(rec.get('Date'))

        # Guess service type from description
        service_type = _guess_service_type(description)

        service_entry = {
            'date': entry_date.isoformat(),
            'odometer': mileage,
            'amount': cost,
            'service_type': service_type,
            'description': description,
            'notes': rec.get('Notes'),
            '_lubelog_files': rec.get('Files', []),
        }
        vehicle['service_entries'].append(service_entry)

    # ── Collision records → Repair entries ──
    for rec in classified['collision_records']:
        vid = rec.get('VehicleId', 1)
        vehicle = vehicle_map.get(vid)
        if not vehicle:
            continue

        raw_mileage = rec.get('Mileage', 0)
        mileage = round(raw_mileage * odo_factor) if raw_mileage else 0
        if mileage and mileage > max_mileage.get(vid, 0):
            max_mileage[vid] = mileage

        description = rec.get('Description', '')
        cost = _safe_float(rec.get('Cost'))
        entry_date = _parse_date(rec.get('Date'))

        repair_entry = {
            'date': entry_date.isoformat(),
            'odometer': mileage,
            'amount': cost,
            'repair_type': 'collision',
            'description': description,
            'notes': rec.get('Notes'),
            '_lubelog_files': rec.get('Files', []),
        }
        vehicle['repair_entries'].append(repair_entry)

    # ── Reminder records → Reminders ──
    for rec in classified['reminder_records']:
        vid = rec.get('VehicleId', 1)
        due_date = _parse_date(rec.get('Date'))
        description = rec.get('Description', 'Reminder')
        is_recurring = rec.get('IsRecurring', False)

        reminder = {
            'title': description,
            'description': f'Imported from LubeLogger. Mileage: {rec.get("Mileage", "N/A")}',
            'reminder_type': _guess_reminder_type(description),
            'due_date': due_date.isoformat(),
            'priority': 'medium',
            'recurring': is_recurring,
            'vehicle_lubelog_id': vid,
        }
        gearcargo_data['reminders'].append(reminder)

    # Set vehicle mileage from highest odometer reading
    for vehicle_data in gearcargo_data['vehicles']:
        ll_id = vehicle_data.get('lubelog_id', 1)
        if ll_id in max_mileage:
            vehicle_data['current_mileage'] = max_mileage[ll_id]

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
    if 'battery' in desc_lower:
        return 'battery'
    if 'mot' in desc_lower:
        return 'inspection'
    if 'filter' in desc_lower:
        return 'filter_change'
    if 'full service' in desc_lower or 'service' in desc_lower:
        return 'full_service'
    if 'suspension' in desc_lower:
        return 'suspension'
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

def import_lubelog_to_gearcargo(user, zip_data, merge_mode='merge', distance_unit=None):
    """Full import pipeline: parse LubeLogger ZIP → create GearCargo records.

    Args:
        user: Current authenticated user (SQLAlchemy model)
        zip_data: BytesIO containing the LubeLogger backup ZIP
        merge_mode: 'merge' (add alongside existing) or 'replace'
        distance_unit: Target distance unit ('km' or 'miles'). If None,
            auto-detected from LubeLogger config.

    Returns:
        dict with import counts and status info
    """
    from app import db
    from app.models import (Vehicle, FuelEntry, ServiceEntry, RepairEntry,
                           TaxEntry, Reminder, InsurancePolicy, Attachment)
    from flask import current_app

    # Step 1: Parse the backup
    zip_data.seek(0)
    with zipfile.ZipFile(zip_data, 'r') as zf:
        names = zf.namelist()

        # Find LiteDB file
        db_file = None
        for name in names:
            if name.endswith('.db'):
                db_file = name
                break
        if not db_file:
            return {'error': 'No database file found in backup ZIP'}

        raw_data = zf.read(db_file)
        docs = scan_bson_documents(raw_data)
        classified = classify_documents(docs)

        # Read config
        config = {}
        for name in names:
            if 'userConfig.json' in name:
                try:
                    config = json.loads(zf.read(name).decode('utf-8'))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass
                break

        # Step 2: Map to GearCargo format
        gearcargo_data = map_to_gearcargo(classified, config, distance_unit=distance_unit)

        # Step 3: Import into database
        imported = {
            'vehicles': 0,
            'fuel_entries': 0,
            'service_entries': 0,
            'repair_entries': 0,
            'tax_entries': 0,
            'reminders': 0,
            'insurance_policies': 0,
            'attachments': 0,
        }

        vehicle_id_map = {}  # lubelog_id → gearcargo vehicle.id

        # Import vehicles
        for v_data in gearcargo_data['vehicles']:
            ll_id = v_data.get('lubelog_id', 0)

            # Check for existing vehicle
            existing = None
            if v_data.get('license_plate'):
                existing = Vehicle.query.filter_by(
                    user_id=user.id,
                    license_plate=v_data['license_plate']
                ).first()

            if existing and merge_mode == 'merge':
                vehicle = existing
            else:
                vehicle = Vehicle(
                    user_id=user.id,
                    name=v_data.get('name', 'Imported Vehicle'),
                    make=v_data.get('make'),
                    model=v_data.get('model'),
                    year=v_data.get('year'),
                    license_plate=v_data.get('license_plate'),
                    fuel_type=v_data.get('fuel_type', 'petrol'),
                    distance_unit=v_data.get('distance_unit', 'km'),
                    current_mileage=v_data.get('current_mileage', 0),
                )
                db.session.add(vehicle)
                db.session.flush()
                imported['vehicles'] += 1

            vehicle_id_map[ll_id] = vehicle.id

            # Update mileage if higher
            if v_data.get('current_mileage'):
                vehicle.update_mileage(v_data['current_mileage'])

            # Import fuel entries
            for entry_data in v_data.get('fuel_entries', []):
                entry_date = _parse_date(entry_data.get('date'))
                entry = FuelEntry(
                    user_id=user.id,
                    vehicle_id=vehicle.id,
                    date=entry_date,
                    odometer=entry_data.get('odometer'),
                    amount=entry_data.get('amount', 0),
                    liters=entry_data.get('liters'),
                    price_per_liter=entry_data.get('price_per_liter'),
                    total_price=entry_data.get('total_price'),
                    full_tank=entry_data.get('full_tank', True),
                    notes=entry_data.get('notes'),
                    title='Fuel',
                )
                db.session.add(entry)
                db.session.flush()
                entry_data['_gc_entry_id'] = entry.id
                imported['fuel_entries'] += 1

            # Import service entries
            for entry_data in v_data.get('service_entries', []):
                entry_date = _parse_date(entry_data.get('date'))
                entry = ServiceEntry(
                    user_id=user.id,
                    vehicle_id=vehicle.id,
                    date=entry_date,
                    odometer=entry_data.get('odometer'),
                    amount=entry_data.get('amount', 0),
                    service_type=entry_data.get('service_type'),
                    description=entry_data.get('description'),
                    notes=entry_data.get('notes'),
                    title=entry_data.get('description', 'Service'),
                )
                db.session.add(entry)
                db.session.flush()
                entry_data['_gc_entry_id'] = entry.id
                imported['service_entries'] += 1

            # Import repair entries
            for entry_data in v_data.get('repair_entries', []):
                entry_date = _parse_date(entry_data.get('date'))
                entry = RepairEntry(
                    user_id=user.id,
                    vehicle_id=vehicle.id,
                    date=entry_date,
                    odometer=entry_data.get('odometer'),
                    amount=entry_data.get('amount', 0),
                    repair_type=entry_data.get('repair_type'),
                    description=entry_data.get('description'),
                    notes=entry_data.get('notes'),
                    title=entry_data.get('description', 'Repair'),
                )
                db.session.add(entry)
                db.session.flush()
                entry_data['_gc_entry_id'] = entry.id
                imported['repair_entries'] += 1

            # Import tax entries
            for entry_data in v_data.get('tax_entries', []):
                entry_date = _parse_date(entry_data.get('date'))
                entry = TaxEntry(
                    user_id=user.id,
                    vehicle_id=vehicle.id,
                    date=entry_date,
                    amount=entry_data.get('amount', 0),
                    tax_type=entry_data.get('tax_type'),
                    title=entry_data.get('title'),
                    description=entry_data.get('description'),
                    status=entry_data.get('status', 'paid'),
                    recurring=entry_data.get('recurring', False),
                    recurrence_type=entry_data.get('recurrence_type'),
                )
                db.session.add(entry)
                db.session.flush()
                entry_data['_gc_entry_id'] = entry.id
                imported['tax_entries'] += 1

        # Import insurance policies
        for policy_data in gearcargo_data.get('insurance_policies', []):
            vid = policy_data.get('vehicle_lubelog_id', 1)
            vehicle_id = vehicle_id_map.get(vid)
            if not vehicle_id:
                vehicle_id = next(iter(vehicle_id_map.values()), None)
            if not vehicle_id:
                continue

            start_date = _parse_date(policy_data.get('start_date'))
            end_date = _parse_date(policy_data.get('end_date'))

            policy = InsurancePolicy(
                user_id=user.id,
                vehicle_id=vehicle_id,
                provider=policy_data.get('provider', 'Unknown'),
                policy_type=policy_data.get('policy_type', 'comprehensive'),
                premium=policy_data.get('premium', 0),
                payment_frequency=policy_data.get('payment_frequency', 'monthly'),
                start_date=start_date,
                end_date=end_date,
                status=policy_data.get('status', 'active'),
                notes=policy_data.get('notes'),
            )
            db.session.add(policy)
            imported['insurance_policies'] += 1

        # Import reminders
        for rem_data in gearcargo_data.get('reminders', []):
            vid = rem_data.get('vehicle_lubelog_id', 1)
            vehicle_id = vehicle_id_map.get(vid)

            reminder = Reminder(
                user_id=user.id,
                vehicle_id=vehicle_id,
                title=rem_data.get('title', 'Reminder'),
                description=rem_data.get('description'),
                reminder_type=rem_data.get('reminder_type', 'custom'),
                due_date=_parse_date(rem_data.get('due_date')),
                priority=rem_data.get('priority', 'medium'),
            )
            db.session.add(reminder)
            imported['reminders'] += 1

        # Flush to get entry IDs before linking attachments
        db.session.flush()

        # Step 4: Import attached documents and images
        upload_folder = current_app.config.get('UPLOAD_FOLDER', '/app/volumes/attachments')
        user_folder = os.path.join(upload_folder, str(user.id))
        os.makedirs(user_folder, exist_ok=True)

        # Build a map: file location → list of (entry_id, vehicle_id) for linking
        file_to_entries = {}  # '/documents/uuid.jpg' → [{'entry_id': N, 'vehicle_id': M}]
        for v_data in gearcargo_data['vehicles']:
            ll_id = v_data.get('lubelog_id', 0)
            gc_vid = vehicle_id_map.get(ll_id)
            for entry_list in ['fuel_entries', 'service_entries', 'repair_entries', 'tax_entries']:
                for entry_data in v_data.get(entry_list, []):
                    entry_id = entry_data.get('_gc_entry_id')
                    for f in entry_data.get('_lubelog_files', []):
                        loc = f.get('Location', '')
                        if loc:
                            file_to_entries.setdefault(loc, []).append({
                                'entry_id': entry_id,
                                'vehicle_id': gc_vid,
                                'original_name': f.get('Name', ''),
                            })

        # Also collect vehicle photo paths
        vehicle_photos = {}
        for v_data in gearcargo_data['vehicles']:
            photo = v_data.get('photo')
            if photo:
                ll_id = v_data.get('lubelog_id', 0)
                vehicle_photos[photo] = vehicle_id_map.get(ll_id)

        # Extract and save files from the ZIP
        for name in names:
            if not name.startswith(('documents/', 'images/')):
                continue
            zip_path = '/' + name

            is_referenced = zip_path in file_to_entries
            is_vehicle_photo = zip_path in vehicle_photos

            if not is_referenced and not is_vehicle_photo:
                continue

            try:
                file_content = zf.read(name)
                original_name = os.path.basename(name)
                safe_name = f"{uuid.uuid4().hex}_{original_name}"
                save_path = os.path.join(user_folder, safe_name)

                with open(save_path, 'wb') as f:
                    f.write(file_content)
                os.chmod(save_path, 0o640)

                # Determine file type
                ext = original_name.rsplit('.', 1)[-1].lower() if '.' in original_name else ''
                mime_map = {
                    'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
                    'png': 'image/png', 'gif': 'image/gif',
                    'pdf': 'application/pdf',
                }
                file_type = mime_map.get(ext, 'application/octet-stream')

                if is_referenced:
                    # Create one attachment per entry that references this file
                    refs = file_to_entries[zip_path]
                    seen_entries = set()
                    for ref in refs:
                        eid = ref.get('entry_id')
                        vid = ref.get('vehicle_id')
                        # Avoid duplicate (same entry_id)
                        entry_key = (eid, vid)
                        if entry_key in seen_entries:
                            continue
                        seen_entries.add(entry_key)

                        display_name = ref.get('original_name') or original_name
                        attachment = Attachment(
                            user_id=user.id,
                            filename=safe_name,
                            original_filename=display_name,
                            filepath=save_path,
                            file_type=file_type,
                            file_size=len(file_content),
                            description='Imported from LubeLogger',
                            category='document' if ext == 'pdf' else 'receipt',
                            entry_id=eid,
                            vehicle_id=vid,
                        )
                        db.session.add(attachment)
                        imported['attachments'] += 1
                elif is_vehicle_photo:
                    # Attachment for the photo
                    gc_vid = vehicle_photos[zip_path]
                    attachment = Attachment(
                        user_id=user.id,
                        filename=safe_name,
                        original_filename=original_name,
                        filepath=save_path,
                        file_type=file_type,
                        file_size=len(file_content),
                        description='Vehicle photo from LubeLogger',
                        category='photo',
                        vehicle_id=gc_vid,
                    )
                    db.session.add(attachment)
                    imported['attachments'] += 1

                # Handle vehicle photo assignment
                if is_vehicle_photo and vehicle_photos[zip_path]:
                    gc_vid = vehicle_photos[zip_path]
                    vehicle_obj = db.session.get(Vehicle, gc_vid)
                    if vehicle_obj:
                        uploads_folder = os.path.join(
                            current_app.root_path, '..', 'uploads', 'vehicles'
                        )
                        os.makedirs(uploads_folder, mode=0o750, exist_ok=True)
                        photo_name = f"{gc_vid}_{uuid.uuid4().hex}.{ext}"
                        photo_path = os.path.join(uploads_folder, photo_name)
                        shutil.copy2(save_path, photo_path)
                        os.chmod(photo_path, 0o640)
                        vehicle_obj.photo = f"/uploads/vehicles/{photo_name}"

            except (KeyError, OSError) as e:
                current_app.logger.warning(f'Failed to extract file {name}: {e}')
                continue

        db.session.commit()

    # Build summary
    total_entries = (imported['fuel_entries'] + imported['service_entries'] +
                    imported['repair_entries'] + imported['tax_entries'])

    return {
        'success': True,
        'imported': imported,
        'summary': {
            'source': 'LubeLogger',
            'vehicles': imported['vehicles'],
            'total_entries': total_entries,
            'fuel_entries': imported['fuel_entries'],
            'service_entries': imported['service_entries'],
            'repair_entries': imported['repair_entries'],
            'tax_entries': imported['tax_entries'],
            'insurance_policies': imported['insurance_policies'],
            'reminders': imported['reminders'],
            'attachments': imported['attachments'],
        }
    }

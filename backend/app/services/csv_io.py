"""
GearCargo - Generic CSV Import / Export (F01, IMPROVEMENTS.md §3.1)

Human-readable, Excel-openable CSV export and import for fuel / service / repair /
tax / parking history. Complements the JSON/ZIP backup (full fidelity) and the
LubeLog importer (vendor-specific) with a portable, GDPR-friendly format users can
open in a spreadsheet.

Design notes
------------
* Export is read-only and per entry-type; columns are a curated, stable subset.
* Import is the inverse of export: the same headers round-trip. Unknown columns
  are ignored; rows are validated individually and a per-row error report is
  returned (no single bad row aborts the whole import).
* `vehicle_id` is required on every import row and is verified to belong to the
  authenticated user (ownership enforcement — never trust the CSV).
* In the default 'merge' mode, rows duplicating an existing entry by
  (vehicle_id, date, rounded amount) are skipped, matching the dedup key used by
  scripts/deduplicate_entries.py.
"""

import csv
import io
from datetime import date, datetime

from app import db
from app.models import (
    FuelEntry, ServiceEntry, RepairEntry, TaxEntry, ParkingEntry,
    ConsumableEntry, Vehicle,
)

# Entry type -> model class. These are the user-facing CSV "types".
TYPE_MODELS = {
    'fuel': FuelEntry,
    'service': ServiceEntry,
    'repair': RepairEntry,
    'tax': TaxEntry,
    'parking': ParkingEntry,
    'consumable': ConsumableEntry,
}

# Columns shared by every entry type: (csv_header, model_attr, kind).
# `kind` drives both export formatting and import parsing/coercion.
_COMMON = [
    ('vehicle_id', 'vehicle_id', 'int'),
    ('date', 'date', 'date'),
    ('odometer', 'odometer', 'int'),
    ('amount', 'amount', 'float'),
    ('currency', 'currency', 'str'),
    ('title', 'title', 'str'),
    ('description', 'description', 'str'),
    ('notes', 'notes', 'str'),
]

# Type-specific columns appended after the common ones.
_EXTRA = {
    'fuel': [
        ('liters', 'liters', 'float'),
        ('price_per_liter', 'price_per_liter', 'float'),
        ('total_price', 'total_price', 'float'),
        ('fuel_type', 'fuel_type', 'str'),
        ('station', 'station', 'str'),
        ('full_tank', 'full_tank', 'bool'),
        ('trip_distance', 'trip_distance', 'int'),
    ],
    'service': [
        ('service_type', 'service_type', 'str'),
        ('provider', 'provider', 'str'),
        ('garage_name', 'garage_name', 'str'),
        ('labor_cost', 'labor_cost', 'float'),
        ('parts_cost', 'parts_cost', 'float'),
        ('next_due_date', 'next_due_date', 'date'),
        ('next_due_mileage', 'next_due_mileage', 'int'),
    ],
    'repair': [
        ('repair_type', 'repair_type', 'str'),
        ('provider', 'provider', 'str'),
        ('garage_name', 'garage_name', 'str'),
        ('labor_cost', 'labor_cost', 'float'),
        ('parts_cost', 'parts_cost', 'float'),
        ('severity', 'severity', 'str'),
    ],
    'tax': [
        ('tax_type', 'tax_type', 'str'),
        ('tax_year', 'tax_year', 'int'),
        ('status', 'status', 'str'),
        ('due_date', 'due_date', 'date'),
        ('paid_date', 'paid_date', 'date'),
        ('reference_number', 'reference_number', 'str'),
    ],
    'parking': [
        ('parking_type', 'parking_type', 'str'),
        ('location', 'location', 'str'),
        ('start_datetime', 'start_datetime', 'datetime'),
        ('end_datetime', 'end_datetime', 'datetime'),
        ('duration_minutes', 'duration_minutes', 'int'),
    ],
    'consumable': [
        ('consumable_type', 'consumable_type', 'str'),
        ('brand', 'brand', 'str'),
        ('quantity', 'quantity', 'int'),
        ('install_date', 'install_date', 'date'),
        ('install_odometer', 'install_odometer', 'int'),
        ('expected_lifespan_km', 'expected_lifespan_km', 'int'),
        ('expected_lifespan_months', 'expected_lifespan_months', 'int'),
        ('warranty_months', 'warranty_months', 'int'),
    ],
}


def columns_for(entry_type):
    """Ordered column spec (header, attr, kind) for an entry type."""
    return _COMMON + _EXTRA.get(entry_type, [])


# --------------------------------------------------------------------------
# Value formatting (export) and parsing (import)
# --------------------------------------------------------------------------

# Characters that trigger formula evaluation in spreadsheet apps (Excel/Sheets).
# Text cells beginning with one of these are CSV-injection vectors (CWE-1236).
_FORMULA_TRIGGERS = ('=', '+', '-', '@', '\t', '\r')


def _fmt(value, kind):
    if value is None:
        return ''
    if kind == 'bool':
        return 'true' if value else 'false'
    if kind in ('date', 'datetime'):
        return value.isoformat()
    s = str(value)
    # CSV-injection guard: neutralise formula-leading TEXT cells by prefixing an
    # apostrophe (Excel then treats the cell as literal text). Numeric/date kinds
    # are unaffected. _parse() strips this apostrophe back off on import so the
    # value round-trips unchanged.
    if kind == 'str' and s and s[0] in _FORMULA_TRIGGERS:
        s = "'" + s
    return s


# Accepted date input formats on import (export always writes ISO).
_DATE_FORMATS = ('%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y')


def _parse(value, kind):
    """Coerce a CSV cell to the column's python type. Empty -> None.
    Raises ValueError on malformed input (caught per-row by the importer)."""
    v = (value or '').strip()
    if v == '':
        return None
    if kind == 'int':
        return int(float(v))  # tolerate "12000.0"
    if kind == 'float':
        return float(v)
    if kind == 'bool':
        return v.lower() in ('1', 'true', 'yes', 'y', 'on')
    if kind == 'date':
        try:
            return date.fromisoformat(v)
        except ValueError:
            for fmt in _DATE_FORMATS:
                try:
                    return datetime.strptime(v, fmt).date()
                except ValueError:
                    continue
            raise ValueError(f'invalid date: {v!r}')
    if kind == 'datetime':
        try:
            return datetime.fromisoformat(v)
        except ValueError:
            return datetime.strptime(v, '%Y-%m-%d %H:%M:%S')
    # str: undo the export-side CSV-injection guard so values round-trip exactly.
    if v.startswith("'") and len(v) > 1 and v[1] in _FORMULA_TRIGGERS:
        v = v[1:]
    return v


# --------------------------------------------------------------------------
# Export
# --------------------------------------------------------------------------

def export_entries_csv(user, entry_type, vehicle_id=None):
    """Return CSV text for *entry_type*, optionally scoped to one vehicle.

    Always filtered to the authenticated user's own data.
    """
    if entry_type not in TYPE_MODELS:
        raise ValueError(f'unknown entry type: {entry_type}')
    model = TYPE_MODELS[entry_type]
    cols = columns_for(entry_type)

    query = model.query.filter_by(user_id=user.id)
    if vehicle_id is not None:
        query = query.filter_by(vehicle_id=vehicle_id)
    query = query.order_by(model.date.asc(), model.id.asc())

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([header for header, _, _ in cols])
    for entry in query.all():
        writer.writerow([_fmt(getattr(entry, attr, None), kind) for _, attr, kind in cols])
    return out.getvalue()


# --------------------------------------------------------------------------
# Import
# --------------------------------------------------------------------------

def _dedup_key(vehicle_id, the_date, amount):
    rounded = round(float(amount), 2) if amount is not None else None
    return (vehicle_id, the_date, rounded)


def import_entries_csv(user, entry_type, csv_text, merge_mode='merge'):
    """Create entries from CSV text. Returns a summary dict:
        {created, skipped, error_count, errors:[{row, error}], total}

    - vehicle_id is required per row and must belong to *user*.
    - 'merge' (default) skips rows duplicating an existing entry; 'replace' is
      treated like merge here (we never delete on CSV import — non-destructive).
    """
    if entry_type not in TYPE_MODELS:
        raise ValueError(f'unknown entry type: {entry_type}')
    model = TYPE_MODELS[entry_type]
    header_to_spec = {h: (attr, kind) for h, attr, kind in columns_for(entry_type)}

    # Ownership allowlist — never trust vehicle_id from the file.
    owned_vehicle_ids = {v.id for v in Vehicle.query.filter_by(user_id=user.id).all()}

    # Existing-entry dedup set for merge mode.
    existing = {
        _dedup_key(e.vehicle_id, e.date, e.amount)
        for e in model.query.filter_by(user_id=user.id).all()
    }

    reader = csv.DictReader(io.StringIO(csv_text))
    if reader.fieldnames is None or 'vehicle_id' not in reader.fieldnames or 'date' not in reader.fieldnames:
        raise ValueError("CSV must include at least 'vehicle_id' and 'date' columns")

    created = skipped = 0
    errors = []
    total = 0

    # enumerate from 2: row 1 is the header line (for human-friendly error rows)
    for line_no, row in enumerate(reader, start=2):
        total += 1
        try:
            vid_raw = (row.get('vehicle_id') or '').strip()
            if not vid_raw:
                errors.append({'row': line_no, 'error': 'missing vehicle_id'})
                continue
            vehicle_id = int(float(vid_raw))
            if vehicle_id not in owned_vehicle_ids:
                errors.append({'row': line_no, 'error': f'unknown or unauthorized vehicle_id {vehicle_id}'})
                continue

            kwargs = {}
            for header, raw in row.items():
                spec = header_to_spec.get(header)
                if not spec:
                    continue  # ignore unknown / extra columns
                attr, kind = spec
                if attr == 'vehicle_id':
                    continue  # handled explicitly above
                parsed = _parse(raw, kind)
                if parsed is not None:
                    kwargs[attr] = parsed

            if not kwargs.get('date'):
                errors.append({'row': line_no, 'error': 'missing or invalid date'})
                continue

            key = _dedup_key(vehicle_id, kwargs['date'], kwargs.get('amount'))
            if key in existing:
                skipped += 1
                continue

            entry = model(user_id=user.id, vehicle_id=vehicle_id, **kwargs)
            db.session.add(entry)
            existing.add(key)
            created += 1
        except Exception as ex:  # noqa: BLE001 — per-row isolation
            errors.append({'row': line_no, 'error': str(ex)[:200]})

    if created:
        db.session.commit()
    else:
        db.session.rollback()

    return {
        'created': created,
        'skipped': skipped,
        'error_count': len(errors),
        'errors': errors[:50],   # cap payload
        'total': total,
    }

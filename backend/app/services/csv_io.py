"""
GearCargo - Generic CSV Import / Export (F01)

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
* Source IDs identify exact repeats. Identity-free rows use file + row position,
  so equal-cost rows remain distinct. Similar content is review information.
"""

import csv
import io
from datetime import date, datetime

from app import db
from app.services.domain_validation import validate_field
from app.utils.entryparse import parse_amount, parse_optional_int, InvalidFieldError
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
        ('station_address', 'station_address', 'str'),
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
        return parse_optional_int(v)
    if kind == 'float':
        return parse_amount(v)
    if kind == 'bool':
        if v.lower() not in ('1', 'true', 'yes', 'y', 'on', '0', 'false', 'no', 'n', 'off'):
            raise ValueError('Invalid boolean')
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
    from app.services.import_identity import native_namespace
    writer.writerow(['source_namespace', 'source_id'] + [header for header, _, _ in cols])
    for entry in query.all():
        writer.writerow([native_namespace(user), entry.id] + [_fmt(getattr(entry, attr, None), kind) for _, attr, kind in cols])
    return out.getvalue()


# --------------------------------------------------------------------------
# Import
# --------------------------------------------------------------------------

def import_entries_csv(user, entry_type, csv_text, merge_mode='merge', *, source_label=None,
                       preview=False, conflict_policy='reject', preview_token=None):
    """Create entries from CSV text. Returns a summary dict:
        {created, skipped, error_count, errors:[{row, error}], total}

    - vehicle_id is required per row and must belong to *user*.
    - 'merge' (default) skips proven source replays; 'replace' is
      treated like merge here (we never delete on CSV import — non-destructive).
    """
    if entry_type not in TYPE_MODELS:
        raise ValueError(f'unknown entry type: {entry_type}')
    model = TYPE_MODELS[entry_type]
    header_to_spec = {h: (attr, kind) for h, attr, kind in columns_for(entry_type)}

    # Ownership allowlist — never trust vehicle_id from the file.
    owned_vehicle_ids = {v.id for v in Vehicle.query.filter_by(user_id=user.id).all()}

    from app.services.backup_schema import PreparedBackup
    from app.services.import_identity import ImportPlan, digest, namespace_for, lock_imports
    if merge_mode not in ('merge', 'replace'):
        raise ValueError('Unsupported merge mode.')
    file_key = digest(csv_text)
    namespace = namespace_for('csv:' + entry_type, source_label, file_key)
    kind = entry_type + '_entries' if entry_type != 'consumable' else 'consumable_entries'
    rows, source_keys = [], {}
    reader = csv.DictReader(io.StringIO(csv_text))
    if reader.fieldnames is None or 'vehicle_id' not in reader.fieldnames or 'date' not in reader.fieldnames:
        raise ValueError("CSV must include at least 'vehicle_id' and 'date' columns")

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
            vehicle_id = validate_field(model, 'vehicle_id', vid_raw)
            if vehicle_id not in owned_vehicle_ids:
                errors.append({'row': line_no, 'error': f'unknown or unauthorized vehicle_id {vehicle_id}'})
                continue

            kwargs = {}
            empty_fields = []
            for header, raw in row.items():
                spec = header_to_spec.get(header)
                if not spec:
                    continue  # ignore unknown / extra columns
                attr, field_kind = spec
                if attr == 'vehicle_id':
                    continue  # handled explicitly above
                try:
                    parsed = _parse(raw, field_kind)
                    if parsed is None:
                        empty_fields.append(attr)
                    else:
                        kwargs[attr] = validate_field(model, attr, parsed)
                except InvalidFieldError as exc:
                    exc.field = attr
                    raise

            if not kwargs.get('date'):
                errors.append({'row': line_no, 'error': 'missing or invalid date'})
                continue

            source_id = (row.get('source_id') or '').strip()
            source_namespace = (row.get('source_namespace') or '').strip() or namespace
            if len(source_id) > 160 or len(source_namespace) > 160:
                raise ValueError('Source identity is too long.')
            source_keys[(kind, line_no)] = ((source_namespace, source_id) if source_id else
                                          ('csv:' + entry_type + ':file:' + file_key, str(line_no)))
            rows.append(dict(id=line_no, vehicle_id=vehicle_id, _empty_fields=empty_fields, **kwargs))
        except Exception as ex:  # noqa: BLE001 — per-row isolation
            issue = {'row': line_no, 'error': str(ex)[:200]}
            if isinstance(ex, InvalidFieldError):
                issue.update(field=ex.field, message_key=ex.message_key)
            errors.append(issue)

    prepared = PreparedBackup('csv', {kind: rows}, {}, [], False, namespace=namespace,
                              batch_key=digest({'format': kind, 'file': file_key, 'namespace': namespace}),
                              import_format='csv', source_keys=source_keys)
    if not preview:
        lock_imports(user.id)
    plan = ImportPlan(user, prepared)
    if preview:
        return {'preview': {**plan.preview, 'error_count': len(errors), 'errors': errors[:50]}}
    plan.validate_apply(conflict_policy, preview_token)
    plan.begin(conflict_policy)
    created = skipped = kept = 0
    affected_vehicles = set()
    for row in rows:
        key = (kind, row['id'])
        decision = plan.actions[key]
        entry = decision['target']
        if decision['action'] == 'create':
            entry = model(user_id=user.id, **{key: value for key, value in row.items() if key != 'id' and not key.startswith('_')})
            db.session.add(entry)
            db.session.flush()
            affected_vehicles.add(entry.vehicle_id)
            created += 1
        elif decision['action'] == 'exact_repeat':
            skipped += 1
        else:
            kept += 1
        plan.remember(key, entry)
    if entry_type == 'fuel':
        from app.services.fuel_efficiency import recalculate_efficiencies
        for vehicle_id in affected_vehicles:
            recalculate_efficiencies(vehicle_id, user.id)
    db.session.commit()
    return {**plan.result(), 'created': created, 'new_records': created, 'skipped': skipped,
            'skipped_conflicts': kept, 'error_count': len(errors), 'errors': errors[:50], 'total': total}

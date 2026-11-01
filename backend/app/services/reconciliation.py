"""Exact original-currency allocations; no automatic creation or FX conversion."""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
import re
from app import db
from app.models import Entry, StatementBatch, StatementTransaction, StatementMatch
from app.services.import_identity import digest
from app.utils.entryparse import InvalidFieldError, CURRENCY_CODES

TYPES = ('fuel', 'service', 'repair', 'tax', 'parking', 'consumable')
ZERO = Decimal('0.00')


def invalid(field='statement', key='invalid'):
    raise InvalidFieldError(field=field, message_key='reconciliation.' + key, error='Invalid reconciliation data.')


def amount(value):
    if not isinstance(value, str) or not re.fullmatch(r'-?\d{1,8}(\.\d{1,2})?', value): invalid('amount')
    try: result = Decimal(value)
    except InvalidOperation: invalid('amount')
    if not result or abs(result) >= 100000000: invalid('amount')
    return result.quantize(Decimal('.01'))


def selected(data):
    if not isinstance(data, dict) or set(data) != {'name', 'source_key', 'rows'}: invalid()
    name = data['name']; key = data['source_key']; rows = data['rows']
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100: invalid('name')
    if not isinstance(key, str) or not re.fullmatch('[a-f0-9]{64}', key): invalid('source_key')
    if not isinstance(rows, list) or not 1 <= len(rows) <= 2000: invalid('rows')
    normalized, seen = [], set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'row_number', 'date', 'amount', 'currency', 'vendor'}: invalid('rows')
        number = row['row_number']
        if type(number) is not int or not 1 <= number <= 10000 or number in seen: invalid('row_number')
        seen.add(number)
        try: day = date.fromisoformat(row['date'])
        except (TypeError, ValueError): invalid('date')
        if day.isoformat() != row['date'] or not 1900 <= day.year <= 2100: invalid('date')
        currency = row['currency']; vendor = row['vendor']
        if not isinstance(currency, str) or currency not in CURRENCY_CODES: invalid('currency')
        if not isinstance(vendor, str) or len(vendor) > 120 or any(ord(c) < 32 for c in vendor): invalid('vendor')
        normalized.append(dict(row_number=number, date=day, amount=amount(row['amount']), currency=currency, vendor=vendor.strip()))
    normalized.sort(key=lambda r: r['row_number'])
    return name.strip(), key, normalized, digest(normalized)


def expense_amount(entry):
    value = entry.total_price if entry.type == 'fuel' and entry.total_price is not None else entry.amount
    return Decimal(value) if value is not None else ZERO


def signature(entry):
    # Preserve edit history across portable restores. Reverting an amount must
    # not revive an older allocation after that amount has been reallocated.
    return digest(dict(created_at=entry.created_at, updated_at=entry.updated_at, type=entry.type, date=entry.date,
        amount=expense_amount(entry), currency=entry.currency))


def valid_match(match):
    entry = match.entry
    return bool(entry and entry.user_id == match.user_id and entry.type in TYPES and signature(entry) == match.entry_signature)


def transaction_view(row):
    matches = [dict(id=m.id, entry_id=m.entry_id, amount=str(m.amount), valid=valid_match(m)) for m in row.matches]
    allocated = sum((m.amount for m in row.matches if valid_match(m)), ZERO)
    stale = any(not m['valid'] for m in matches)
    status = 'excluded' if row.exclusion_reason else 'needs_review' if stale else 'matched' if allocated == row.amount else 'unmatched'
    return dict(id=row.id, row_number=row.row_number, date=row.date.isoformat(), amount=str(row.amount), currency=row.currency,
        vendor=row.vendor, exclusion_reason=row.exclusion_reason, matches=matches, allocated=str(allocated), remaining=str(row.amount - allocated), status=status)


def batch_view(batch):
    rows = [transaction_view(row) for row in batch.transactions]
    resolved = all(row['status'] in ('matched', 'excluded') for row in rows) and bool(rows)
    totals = defaultdict(lambda: dict(statement=ZERO, allocated=ZERO, excluded=ZERO, remaining=ZERO))
    for row in rows:
        total = totals[row['currency']]
        total['statement'] += Decimal(row['amount']); total['allocated'] += Decimal(row['allocated'])
        if row['status'] == 'excluded': total['excluded'] += Decimal(row['amount'])
        else: total['remaining'] += Decimal(row['remaining'])
    return dict(**batch.to_dict(), name=batch.name, effective_status='needs_review' if batch.status == 'reconciled' and not resolved else batch.status,
        resolved=resolved, transactions=rows, totals={c: {k: str(v) for k, v in t.items()} for c, t in totals.items()})


def candidates(user_id, row, *, page=1, search=''):
    query = Entry.query.filter(Entry.user_id == user_id, Entry.type.in_(TYPES), Entry.currency == row.currency)
    # Suggestions use a deterministic seven-day window. Explicit search may
    # include older invoices; it is paginated, still owner/currency scoped.
    if search:
        query = query.filter(Entry.title.ilike('%' + search.replace('%', r'\%').replace('_', r'\_') + '%', escape='\\'))
    else:
        query = query.filter(Entry.date.between(row.date - timedelta(days=7), row.date + timedelta(days=7)))
    entries = query.order_by(Entry.date.desc(), Entry.id).offset((page - 1) * 50).limit(51).all()
    result = []
    for entry in entries[:50]:
        value = expense_amount(entry)
        if value * row.amount <= 0: continue
        allocations = StatementMatch.query.filter_by(user_id=user_id, entry_id=entry.id).all()
        allocated = sum((m.amount for m in allocations if valid_match(m) and m.transaction_id != row.id), ZERO)
        vendor = getattr(entry, 'station', None) or getattr(entry, 'garage_name', None) or getattr(entry, 'provider', None) or ''
        exact = value - allocated == row.amount
        vendor_match = bool(row.vendor and vendor and row.vendor.casefold() == vendor.casefold())
        result.append(dict(id=entry.id, revision=entry.revision, vehicle_id=entry.vehicle_id, title=entry.title, type=entry.type,
            date=entry.date.isoformat(), currency=entry.currency, amount=str(value), available=str(value-allocated),
            vendor=vendor, exact=exact, vendor_match=vendor_match, date_distance=abs((entry.date-row.date).days),
            attachments=[a.to_dict() for a in entry.attachments if a.user_id == user_id]))
    result.sort(key=lambda e: (not e['exact'], not e['vendor_match'], e['date_distance'], e['id']))
    return dict(candidates=result, more=len(entries)>50, page=page)


def replace_matches(user_id, row, data):
    if not isinstance(data, dict) or set(data) - {'matches', 'exclusion_reason'}: invalid()
    values = data.get('matches', []); reason = data.get('exclusion_reason')
    if reason is not None and (not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 255): invalid('exclusion_reason')
    if not isinstance(values, list) or len(values) > 100 or (values and reason): invalid('matches')
    seen, prepared, total = set(), [], ZERO
    for value in values:
        if not isinstance(value, dict) or set(value) != {'entry_id', 'revision', 'amount'}: invalid('matches')
        ident = value['entry_id']
        if type(ident) is not int or ident in seen or type(value['revision']) is not int: invalid('entry_id')
        seen.add(ident)
    # Serialize allocations across batches at the expense row, in stable order.
    entries = {e.id: e for e in Entry.query.filter(Entry.user_id == user_id, Entry.id.in_(sorted(seen))).order_by(Entry.id).with_for_update(of=Entry).all()}
    for value in values:
        entry = entries.get(value['entry_id']); allocated = amount(value['amount'])
        if not entry or entry.type not in TYPES or entry.currency != row.currency: invalid('entry_id')
        if entry.revision != value['revision']: invalid('revision', 'changed')
        if allocated * row.amount <= 0 or allocated * expense_amount(entry) <= 0: invalid('amount', 'balance')
        others = StatementMatch.query.filter(StatementMatch.user_id == user_id, StatementMatch.entry_id == entry.id, StatementMatch.transaction_id != row.id).all()
        used = sum((m.amount for m in others if valid_match(m)), ZERO)
        if abs(used + allocated) > abs(expense_amount(entry)): invalid('amount', 'balance')
        total += allocated
        prepared.append(StatementMatch(user_id=user_id, entry_id=entry.id, amount=allocated, entry_signature=signature(entry)))
    if abs(total) > abs(row.amount): invalid('amount', 'balance')
    row.matches.clear(); db.session.flush()
    row.matches.extend(prepared)
    row.exclusion_reason = reason.strip() if reason else None


def validate_backup_reconciliation(records):
    from app.services.backup_schema import BackupSchemaError
    batches = {r['id']: r for r in records['statement_batches']}
    rows = {r['id']: r for r in records['statement_transactions']}
    sources, fingerprints, positions, pairs = set(), set(), set(), set()
    totals = defaultdict(lambda: ZERO)
    try:
        for batch in batches.values():
            if batch['source_key'] in sources or batch['status'] not in ('open', 'reconciled'): invalid()
            sources.add(batch['source_key'])
            for key in ('source_key', 'selection_hash'):
                if not re.fullmatch('[a-f0-9]{64}', batch[key]): invalid()
            if not batch['name'].strip(): invalid()
        for row in rows.values():
            pos = (row['batch_id'], row['row_number'])
            if row['batch_id'] not in batches or row['fingerprint'] in fingerprints or pos in positions: invalid()
            fingerprints.add(row['fingerprint']); positions.add(pos)
            if row['exclusion_reason'] is not None and not row['exclusion_reason'].strip(): invalid()
            if row['fingerprint'] != digest([batches[row['batch_id']]['source_key'], row['row_number']]): invalid()
            selected(dict(name='validate', source_key=batches[row['batch_id']]['source_key'], rows=[{k: str(row[k]) if k in ('date', 'amount') else row[k] for k in ('row_number','date','amount','currency','vendor')}]))
        for match in records['statement_matches']:
            amount(str(match['amount']))
            row = rows[match['transaction_id']]; pair = (row['id'], match['entry_id'])
            if (match['entry_id'] is not None and pair in pairs) or row['exclusion_reason'] or match['amount'] * row['amount'] <= 0: invalid()
            pairs.add(pair); totals[row['id']] += match['amount']
            if not re.fullmatch('[a-f0-9]{64}', match['entry_signature']): invalid()
        for ident, total in totals.items():
            if abs(total) > abs(rows[ident]['amount']): invalid()
        for batch in batches.values():
            selected_rows = sorted((r for r in rows.values() if r['batch_id'] == batch['id']), key=lambda r: r['row_number'])
            if not 1 <= len(selected_rows) <= 2000 or batch['selection_hash'] != digest([{k:r[k] for k in ('row_number','date','amount','currency','vendor')} for r in selected_rows]): invalid()
    except (InvalidFieldError, KeyError, TypeError):
        raise BackupSchemaError('Invalid statement reconciliation graph.', 'statement_batches') from None


def validate_restored_allocations(user_id):
    """Cross-batch balance checks after archive IDs have been remapped."""
    from app.services.backup_schema import BackupSchemaError
    used = defaultdict(lambda: ZERO)
    for match in StatementMatch.query.filter_by(user_id=user_id):
        if not valid_match(match): continue  # Historical stale evidence remains reviewable.
        row = db.session.get(StatementTransaction, match.transaction_id)
        if row.currency != match.entry.currency or match.amount * expense_amount(match.entry) <= 0:
            raise BackupSchemaError('Statement and expense signs/currencies differ.', 'statement_matches')
        used[match.entry_id] += match.amount
        if abs(used[match.entry_id]) > abs(expense_amount(match.entry)):
            raise BackupSchemaError('Statement allocations exceed the expense.', 'statement_matches')

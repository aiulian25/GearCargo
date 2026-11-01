"""Shared dated operating costs. Insurance rows are scheduled estimates, not payments.

Inclusive dates, capped at UTC today. Purchase cost is separate from operating
cost. Conversion uses the current rate snapshot, never historical exchange rates.
Unknown currencies/rates are excluded from numeric subtotals and disclosed.
"""
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import selectin_polymorphic

from app.models import (Entry, FuelEntry, ServiceEntry, RepairEntry, TaxEntry,
                        ParkingEntry, ConsumableEntry, InsurancePolicy)
from app.utils.timeutils import utc_today

CATEGORIES = ('fuel', 'service', 'repair', 'tax', 'parking', 'consumable', 'insurance')
BASIS = 'recorded_expenses_plus_scheduled_insurance'
BASIS_LABEL = ('Recorded expenses plus scheduled insurance estimates through the as-of date; '
               'purchase price excluded. Insurance payments are not verified.')


@dataclass(frozen=True)
class Expense:
    date: date
    category: str
    amount: Decimal
    currency: str | None
    source: object


def as_date(value):
    return value.date() if isinstance(value, datetime) else value


def money(value):
    return Decimal(str(value or 0)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)


def convert(amount, source, target, rates):
    """Return rounded display amount or None; never sum unlike currencies."""
    amount = money(amount)
    source = (source or '').upper()
    target = target.upper()
    if not amount or source == target:
        return amount
    def rate(ccy):
        try:
            result = Decimal(str(1 if ccy == 'EUR' else rates.get(ccy)))
            return result if result.is_finite() and result > 0 else None
        except Exception:
            return None
    src, dst = rate(source), rate(target)
    return money(amount / src * dst) if src and dst else None


def scheduled_dates(policy, start, end):
    """Anniversaries anchored to the original day (Jan 31 -> Feb 28 -> Mar 31).

    Stored coverage end is inclusive, including a cancellation's stored end date.
    Status is never evidence of payment; no implicit renewal is projected.
    Legacy blank/unknown frequencies follow the existing annual fallback.
    """
    if not policy.start_date or not policy.end_date:
        return
    first, last = policy.start_date, min(policy.end_date, end)
    if first > last:
        return
    if policy.payment_frequency == 'one_time':
        if start <= first <= last:
            yield first
        return
    step = {'monthly': 1, 'quarterly': 3, 'semi-annual': 6, 'semi_annual': 6}.get(policy.payment_frequency, 12)
    offset = max(0, ((start.year - first.year) * 12 + start.month - first.month) // step)
    while True:
        try:
            occurrence = first + relativedelta(months=offset * step)
        except (ValueError, OverflowError):
            break
        if occurrence > last:
            break
        if occurrence >= start:
            yield occurrence
        offset += 1


def load_expenses(vehicle_ids, start=None, end=None):
    start = as_date(start) or date.min
    end = min(as_date(end) or utc_today(), utc_today())
    if not vehicle_ids or start > end:
        return []
    entries = Entry.query.options(selectin_polymorphic(Entry, [FuelEntry, ServiceEntry,
        RepairEntry, TaxEntry, ParkingEntry, ConsumableEntry])).filter(
        Entry.vehicle_id.in_(vehicle_ids), Entry.date >= start, Entry.date <= end,
        Entry.type.in_(CATEGORIES[:-1])).order_by(Entry.date, Entry.id).all()
    rows = [Expense(e.date, e.type, money(e.total_price if isinstance(e, FuelEntry)
        and e.total_price is not None else e.amount), e.currency, e) for e in entries]
    policies = InsurancePolicy.query.filter(InsurancePolicy.vehicle_id.in_(vehicle_ids),
        InsurancePolicy.start_date <= end, InsurancePolicy.end_date >= start).all()
    for policy in policies:
        rows.extend(Expense(d, 'insurance', money(policy.premium), policy.currency, policy)
                    for d in scheduled_dates(policy, start, end))
    return sorted(rows, key=lambda row: (row.date, row.category, row.source.id))


def aggregate(rows, currency, rates, start=None, end=None):
    start = as_date(start) or date.min
    end = min(as_date(end) or utc_today(), utc_today())
    totals = {key: Decimal(0) for key in CATEGORIES}
    counts = {key: 0 for key in CATEGORIES}
    missing = {}
    monthly = {}
    fx_applied = False
    for row in rows:
        if not start <= row.date <= end:
            continue
        counts[row.category] += 1
        value = convert(row.amount, row.currency, currency, rates)
        key = row.date.strftime('%Y-%m')
        bucket = monthly.setdefault(key, {c: Decimal(0) for c in CATEGORIES})
        fx_applied |= bool(row.amount and row.currency != currency)
        if value is None:
            ccy = row.currency or 'UNKNOWN'
            missing[ccy] = missing.get(ccy, Decimal(0)) + row.amount
            continue
        totals[row.category] += value
        bucket[row.category] += value
    recorded = sum(v for k, v in totals.items() if k != 'insurance')
    totals['grand_total'] = sum(totals.values())
    counts['total'] = sum(counts.values())
    return {
        'basis': BASIS, 'basis_label': BASIS_LABEL,
        'start_date': start.isoformat() if start != date.min else None,
        'end_date': end.isoformat(), 'as_of': utc_today().isoformat(),
        'display_currency': currency, 'currency': currency,
        'converted': not missing, 'fx_applied': fx_applied,
        'unconverted': {k: float(v) for k, v in missing.items()},
        'totals': {k: float(v) for k, v in totals.items()}, 'entry_counts': counts,
        'recorded_total': float(recorded), 'insurance_estimate': float(totals['insurance']),
        'monthly': [{'month': key, 'total': float(sum(values.values())),
                     'breakdown': {k: float(v) for k, v in values.items()}}
                    for key, values in sorted(monthly.items())],
    }


def annualized_total(policies, currency, rates, today=None):
    today = today or utc_today()
    rows = [Expense(today, 'insurance', money(p.annualized_premium), p.currency, p)
            for p in policies if p.status == 'active' and p.start_date <= today <= p.end_date]
    return aggregate(rows, currency, rates)

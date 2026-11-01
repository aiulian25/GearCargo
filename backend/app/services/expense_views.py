"""Period options and bounded detail pages for the shared expense ledger (GC-020)."""
from calendar import monthrange
from datetime import date
from types import SimpleNamespace
from sqlalchemy import extract, false, or_
from sqlalchemy.orm import selectinload

from app import db
from app.models import (Entry, FuelEntry, ServiceEntry, RepairEntry, TaxEntry, ParkingEntry,
                        ConsumableEntry, InsurancePolicy, Reminder, Todo)
from app.services.expense_ledger import CATEGORIES, Expense, aggregate, money, scheduled_dates
from app.utils.timeutils import utc_today

MODELS = dict(zip(CATEGORIES, (FuelEntry, ServiceEntry, RepairEntry, TaxEntry,
                              ParkingEntry, ConsumableEntry, InsurancePolicy)))
MODELS.update(reminder=Reminder, todo=Todo)


def period_bounds(year, month=None):
    year = int(year)
    month = int(month) if month not in (None, '') else None
    if not 1 <= year <= 9999 or (month is not None and not 1 <= month <= 12):
        raise ValueError('Invalid period')
    start = date(year, month or 1, 1)
    end = date(year, month, monthrange(year, month)[1]) if month else date(year, 12, 31)
    return start, min(end, utc_today())


def available_years(vehicle_id):
    """Read distinct dates/coverage shapes, never whole-history expense objects."""
    today = utc_today()
    years = {today.year}
    years.update(int(year) for (year,) in db.session.query(extract('year', Entry.date))
                 .filter(Entry.vehicle_id == vehicle_id, Entry.date <= today,
                         Entry.type.in_(CATEGORIES[:-1])).distinct())
    periods = db.session.query(InsurancePolicy.start_date, InsurancePolicy.end_date,
                               InsurancePolicy.payment_frequency).filter(
        InsurancePolicy.vehicle_id == vehicle_id, InsurancePolicy.start_date <= today).distinct()
    for start, end, frequency in periods:
        if not start or not end or start > end:
            continue
        policy = SimpleNamespace(start_date=start, end_date=end, payment_frequency=frequency)
        if frequency == 'one_time':
            years.add(start.year)
            continue
        for year in range(start.year, min(today, end).year + 1):
            if next(scheduled_dates(policy, date(year, 1, 1), min(today, date(year, 12, 31))), None):
                years.add(year)
    return sorted(years, reverse=True)


def detail_page(vehicle, user, category, start, end, page=1, per_page=20, scope='period', rates=None):
    """One page of source records; policy rows carry a separate period estimate.

    Task lists and outstanding fines are explicitly independent of the chart
    period. Existing category list routes and their response contracts stay intact.
    """
    if category not in MODELS or scope not in ('period', 'outstanding'):
        raise ValueError('Invalid category or scope')
    if scope == 'outstanding' and category != 'parking':
        raise ValueError('Outstanding scope requires parking')
    model = MODELS[category]
    query = model.query.filter(model.vehicle_id == vehicle.id, model.user_id == user.id)
    task = category in ('todo', 'reminder')
    if task:
        query = query.order_by(model.due_date.asc().nullslast(), model.id.desc())
    elif scope == 'outstanding':
        query = query.filter(ParkingEntry.parking_type == 'fine',
                             or_(ParkingEntry.fine_status.in_(('pending', 'contested')), ParkingEntry.fine_status.is_(None)))
        query = query.order_by(model.date.desc(), model.id.desc())
    elif category == 'insurance':
        query = query.filter(model.start_date <= end, model.end_date >= start)
        if start > end:
            query = query.filter(false())
        query = query.order_by(model.end_date.desc(), model.id.desc())
    else:
        query = query.filter(model.date >= start, model.date <= end)
        query = query.order_by(model.date.desc(), model.id.desc())
    if category == 'insurance':
        query = query.options(selectinload(InsurancePolicy.document))
    elif not task:
        query = query.options(selectinload(model.attachments))
    result = query.paginate(page=page, per_page=per_page, error_out=False)
    currency = (user.currency or 'GBP').upper()
    records, page_rows = [], []
    calculation_start, calculation_end = (None, utc_today()) if scope == 'outstanding' else (start, end)
    for record in result.items:
        data = record.to_dict()
        rows = []
        if category == 'insurance':
            rows = [Expense(d, category, money(record.premium), record.currency, record)
                    for d in scheduled_dates(record, start, end)]
        elif not task:
            amount = (record.total_price if category == 'fuel' and record.total_price is not None else record.amount)
            rows = [Expense(utc_today() if scope == 'outstanding' else record.date, category, money(amount), record.currency, record)]
        if not task:
            row_total = aggregate(rows, currency, rates or {}, calculation_start, calculation_end)
            data['period_amount'] = row_total['totals']['grand_total'] if row_total['converted'] else None
            data['period_occurrences'] = len(rows)
            page_rows.extend(rows)
        records.append(data)
    page_money = aggregate(page_rows, currency, rates or {}, calculation_start, calculation_end)
    return {
        'category': category, 'scope': 'all_dates' if task else scope,
        'records': records, 'total': result.total, 'pages': result.pages,
        'current_page': page, 'per_page': per_page,
        'display_currency': currency,
        'page_total': None if task else page_money['totals']['grand_total'],
        'converted': page_money['converted'], 'fx_applied': page_money['fx_applied'],
        'unconverted': page_money['unconverted'],
        'start_date': None if task or scope == 'outstanding' else start.isoformat(),
        'end_date': None if task or scope == 'outstanding' else end.isoformat(),
    }

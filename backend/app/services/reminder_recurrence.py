"""Advance calendar dates from an anchor and mileage from completed maintenance."""
from dateutil.relativedelta import relativedelta


def next_date(reminder):
    anchor = reminder.recurrence_anchor_date or reminder.due_date
    current = reminder.due_date
    step = reminder.frequency_value or 1
    if not anchor or not current or step < 1:
        return None
    if reminder.frequency in ('daily', 'weekly'):
        days = step * (7 if reminder.frequency == 'weekly' else 1)
        count = max(1, (current - anchor).days // days + 1)
        return anchor + relativedelta(days=count * days)
    if reminder.frequency in ('monthly', 'yearly'):
        months = step * (12 if reminder.frequency == 'yearly' else 1)
        count = max(1, ((current.year - anchor.year) * 12 + current.month - anchor.month) // months + 1)
        return anchor + relativedelta(months=count * months)
    return None

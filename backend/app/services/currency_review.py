"""Money records still labelled with a built-in currency their owner never chose.

Until late July 2026 every expense was saved as EUR and every policy as USD, whatever the
person paid in. The label is corrected only when the person confirms, and amounts are never
converted.
"""
from sqlalchemy import func, select, update

from app import db
from app.models import Entry
from app.models.insurance import InsurancePolicy
from app.models.reconciliation import StatementMatch

LEGACY_ENTRY_CURRENCY = 'EUR'
LEGACY_POLICY_CURRENCY = 'USD'
KEPT_CURRENCIES_PREFERENCE = 'currency_review_kept'


def _sources(user):
    # A statement match proves the expense really was paid in its recorded currency.
    matched_entries = select(StatementMatch.entry_id).where(StatementMatch.entry_id.isnot(None))
    return (
        (LEGACY_ENTRY_CURRENCY, Entry, Entry.date, (
            Entry.user_id == user.id, Entry.currency == LEGACY_ENTRY_CURRENCY,
            Entry.id.notin_(matched_entries))),
        (LEGACY_POLICY_CURRENCY, InsurancePolicy, InsurancePolicy.start_date, (
            InsurancePolicy.user_id == user.id, InsurancePolicy.currency == LEGACY_POLICY_CURRENCY)),
    )


def _kept_currencies(user):
    return set((user.preferences or {}).get(KEPT_CURRENCIES_PREFERENCE) or [])


def _open_sources(user):
    settled = _kept_currencies(user) | {user.chosen_currency}
    return [source for source in _sources(user) if source[0] not in settled]


def review_groups(user):
    """Record groups whose label differs from the person's currency and awaits their decision."""
    groups = []
    for currency, model, date_column, criteria in _open_sources(user):
        count, first_date, last_date = db.session.execute(
            select(func.count(model.id), func.min(date_column), func.max(date_column)).where(*criteria)).one()
        if count:
            groups.append({'currency': currency, 'count': count,
                           'first_date': first_date.isoformat(), 'last_date': last_date.isoformat()})
    return groups


def relabel(user, currency):
    """Mark the group as the person's currency. Returns how many records changed."""
    relabelled = 0
    for legacy_currency, model, _date_column, criteria in _open_sources(user):
        if legacy_currency != currency:
            continue
        # The revision moves so a form opened before the change cannot put the old label back.
        relabelled += db.session.execute(
            update(model).where(*criteria)
            .values(currency=user.chosen_currency, revision=model.revision + 1)
            .execution_options(synchronize_session=False)).rowcount
    db.session.commit()
    db.session.expire_all()
    return relabelled


def keep(user, currency):
    """Remember that this group really is in its recorded currency, so it is not asked again."""
    user.preferences = {**(user.preferences or {}),
                        KEPT_CURRENCIES_PREFERENCE: sorted(_kept_currencies(user) | {currency})}
    db.session.commit()

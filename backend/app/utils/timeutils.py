"""Time helpers.

R10: ``datetime.utcnow()`` is deprecated since Python 3.12 and scheduled for
removal. The drop-in below returns the SAME value — naive UTC — so column
defaults and stored timestamps keep their existing semantics.

Deliberately naive, not aware: the ``db.DateTime`` columns are tz-naive, so
returning an aware datetime would reintroduce the naive/aware comparison
TypeError that took down every token-verification path in round 1 (C1). Read
sides that need an aware value keep using ``app.models.user._as_utc``.

API contract: date columns serialize as YYYY-MM-DD, with no timezone conversion.
True instants serialize with ``isoformat_utc`` (an explicit Z). Legacy offsetless
ISO timestamps from older API responses still mean UTC; clients must append Z
before parsing those instants. Neither convention changes stored values. Parking
start/end clock fields are wall times paired with an entry date, not UTC instants.

This module imports nothing from the app, so any model/route/service can use it
without an import cycle.
"""

from datetime import date, datetime, timezone


def utc_naive_now() -> datetime:
    """Current UTC time as a naive datetime (drop-in for datetime.utcnow())."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_today() -> date:
    """Today's date in UTC (drop-in for date.today(), which uses LOCAL time).

    R6: the API computes "today" as ``datetime.now(timezone.utc).date()``. Any
    caller using ``date.today()`` disagrees with it whenever the server's local
    date differs from the UTC date — a window of up to several hours a day for
    non-UTC timezones — which made date-sensitive tests randomly red.
    """
    return datetime.now(timezone.utc).date()


def isoformat_utc(value: datetime | None) -> str | None:
    """Serialize an instant, interpreting legacy naive database values as UTC."""
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError("An instant must be a datetime, not a calendar date")
    aware = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    return aware.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')

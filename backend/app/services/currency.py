"""
GearCargo - Currency normalization (F1).

Per-entry amounts are stored in whatever currency the user logged them in
(Entry.currency defaults 'EUR', InsurancePolicy.currency defaults 'USD'), while
each user has a preferred display currency (User.currency defaults 'GBP').
Aggregations that sum amounts across entries must therefore convert each amount
into the display currency BEFORE summing — otherwise GBP + EUR + USD are added
as if identical.

Conversion pivots through EUR using the ECB rates already fetched (and Redis
cached 24h) by fuel_price_service.get_live_eur_rates: an EUR-based dict of the
form {'GBP': 0.86, 'USD': 1.08, ...} = "units of X per 1 EUR". EUR is the base
and is treated as rate 1.0 (it is not a key in that dict).

A missing/invalid rate degrades gracefully: the amount is passed through
unconverted and the result is flagged so callers can surface an "≈"/"rate
unavailable" hint instead of dropping money from a total.
"""

from datetime import timedelta

# Pivot base for all conversions (matches get_live_eur_rates).
BASE_CURRENCY = 'EUR'


def _rate(rates, ccy):
    """Return the EUR→ccy rate as a positive float, or None if unusable.

    EUR (the base) is always 1.0. Any missing / non-numeric / non-positive rate
    returns None so the caller can flag the amount as unconverted.
    """
    if not ccy or ccy == BASE_CURRENCY:
        return 1.0
    if not rates:
        return None
    raw = rates.get(ccy)
    if raw is None:
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    return val if val > 0 else None


def to_display(amount, from_ccy, to_ccy, rates):
    """Convert ``amount`` from ``from_ccy`` into ``to_ccy`` via EUR-based ``rates``.

    Returns ``(converted_amount: float, ok: bool)``. ``ok`` is False only when a
    needed rate is missing/invalid — in that case the amount is returned
    UNCHANGED (never silently dropped) so the caller can show a "rate
    unavailable" hint. A same-currency or zero conversion is always ok.
    """
    amt = float(amount or 0)
    src = (from_ccy or BASE_CURRENCY).upper()
    dst = (to_ccy or BASE_CURRENCY).upper()
    if amt == 0 or src == dst:
        return amt, True
    r_from = _rate(rates, src)
    r_to = _rate(rates, dst)
    if r_from is None or r_to is None:
        return amt, False
    # amount(src) -> EUR -> amount(dst)
    return (amt / r_from) * r_to, True


def sum_to_display(pairs, to_ccy, rates):
    """Convert and sum ``(currency, amount)`` pairs into ``to_ccy``.

    Returns ``(total: float, converted: bool, fx_applied: bool)`` where:
      * ``converted`` is False if ANY pair needed a rate that was unavailable
        (the total is then only an approximation — some amounts unconverted);
      * ``fx_applied`` is True if ANY pair was in a currency other than
        ``to_ccy`` (i.e. a real FX conversion happened, so the total is an
        approximation subject to exchange rates).
    """
    dst = (to_ccy or BASE_CURRENCY).upper()
    total = 0.0
    converted = True
    fx_applied = False
    for ccy, amount in pairs:
        src = (ccy or BASE_CURRENCY).upper()
        conv, ok = to_display(amount, src, dst, rates)
        total += conv
        if not ok:
            converted = False
        if src != dst:
            fx_applied = True
    return total, converted, fx_applied


def get_rates_cached(app):
    """EUR-based ECB rates, Redis-cached 24h.

    Reuses the exact cache key + fetcher already used by the /currency-rates
    route so there is a single shared cache entry across the app. Never raises:
    on total failure it returns an empty dict, which makes conversions of any
    non-EUR amount fall back to unconverted (flagged) rather than error.
    """
    # Imported lazily to avoid a circular import at module load: get_cached lives
    # in the external route blueprint (which imports auth), and get_live_eur_rates
    # in the fuel-price service.
    from app.routes.external import get_cached
    from app.services.fuel_price_service import get_live_eur_rates

    try:
        return get_cached(
            'currency_rates_eur',
            lambda: get_live_eur_rates(app),
            timedelta(hours=24),
        ) or {}
    except Exception:  # pragma: no cover - defensive; conversions degrade gracefully
        return {}

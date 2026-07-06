"""
GearCargo - External API Routes (Fuel Prices, Currency)
"""

import json
import threading
from collections import OrderedDict
from datetime import datetime, timedelta, timezone

import requests
from flask import Blueprint, request, jsonify, current_app

from app.routes.auth import token_required

external_bp = Blueprint('external', __name__)

CACHE_DURATION = timedelta(minutes=30)

# S10: external-API response cache.
#
# Previously this was a plain module-level dict keyed by rounded lat/lon, which
# (a) grew without bound as users queried distinct coordinates (a slow memory
# leak) and (b) was per-worker (cross-worker inconsistency). It is now backed by
# Redis (shared across workers, evicted by TTL) with a BOUNDED in-process
# LRU+TTL fallback used only when Redis is unavailable.
#
# Entries are retained for up to _STALE_TTL_SECONDS so a cached value can still
# be served stale if the upstream API later fails (preserving the original
# stale-on-error resilience), while freshness is judged against the caller's
# cache_duration via an embedded timestamp.
_REDIS_PREFIX = 'extcache:'
_STALE_TTL_SECONDS = 24 * 3600          # keep up to 24h for stale-on-error
_FALLBACK_MAX_ENTRIES = 256             # hard cap on the in-process fallback
_fallback_cache = OrderedDict()         # key -> (data, timestamp)
_fallback_lock = threading.Lock()


def _get_redis():
    """Return the shared app Redis client, or None. Imported lazily because the
    module-level `redis_client` is only populated once create_app() has run."""
    try:
        from app import redis_client
        return redis_client
    except Exception:
        return None


def _store_get(key):
    """Return (data, timestamp) for *key*, or None. Redis preferred, else the
    bounded in-process fallback."""
    rc = _get_redis()
    if rc is not None:
        try:
            raw = rc.get(_REDIS_PREFIX + key)
            if raw:
                env = json.loads(raw)
                return env['data'], datetime.fromisoformat(env['ts'])
        except Exception as e:
            current_app.logger.debug(f"extcache redis get failed for {key}: {e}")
        return None
    with _fallback_lock:
        item = _fallback_cache.get(key)
        if item is not None:
            _fallback_cache.move_to_end(key)  # LRU touch
        return item


def _store_set(key, data, timestamp):
    """Persist (data, timestamp). Redis (TTL-evicted) preferred; otherwise the
    in-process fallback, which is capped at _FALLBACK_MAX_ENTRIES (LRU eviction)
    so distinct coordinates can never grow memory without bound."""
    rc = _get_redis()
    if rc is not None:
        try:
            rc.setex(
                _REDIS_PREFIX + key,
                _STALE_TTL_SECONDS,
                json.dumps({'data': data, 'ts': timestamp.isoformat()}),
            )
        except Exception as e:
            current_app.logger.debug(f"extcache redis set failed for {key}: {e}")
        return
    with _fallback_lock:
        _fallback_cache[key] = (data, timestamp)
        _fallback_cache.move_to_end(key)
        while len(_fallback_cache) > _FALLBACK_MAX_ENTRIES:
            _fallback_cache.popitem(last=False)  # evict least-recently-used


def get_cached(key, fetch_func, cache_duration=CACHE_DURATION):
    """Return cached data for *key*, fetching via *fetch_func* on miss/expiry.

    Bounded + cross-worker (Redis) cache. On upstream fetch failure, returns the
    last cached value (even if stale) when one is still retained, else None.
    """
    now = datetime.now(timezone.utc)

    cached = _store_get(key)
    if cached is not None:
        data, timestamp = cached
        if now - timestamp < cache_duration:
            return data  # still fresh

    try:
        data = fetch_func()
        _store_set(key, data, now)
        return data
    except Exception as e:
        current_app.logger.error(f"Cache fetch error for {key}: {e}")
        # Return stale data if we still have any retained.
        return cached[0] if cached is not None else None


@external_bp.route('/fuel-prices', methods=['GET'])
@token_required
def get_fuel_prices(current_user):
    """Get fuel prices from live government data sources.

    Data sources:
    - UK: https://www.gov.uk/government/statistics/weekly-road-fuel-prices
    - EU: https://energy.ec.europa.eu/data-and-analysis/weekly-oil-bulletin_en

    Prices are national averages updated weekly (typically Monday).
    Supports force_refresh=true to bypass cache and fetch live data.
    """
    from app.services.fuel_price_service import get_prices

    country = request.args.get('country', 'UK').upper()
    location = request.args.get('location', 'United Kingdom')
    lat = request.args.get('lat', type=float)
    lon = request.args.get('lon', type=float)
    force_refresh = request.args.get('force_refresh', 'false').lower() == 'true'

    # Auto-detect country from coordinates if provided
    if lat and lon:
        detected_country = detect_country_from_coords(lat, lon)
        if detected_country:
            country = detected_country

    cache_key = f"fuel_prices_{country}"

    # On force refresh, clear in-memory cache so we go to the service
    if force_refresh:
        _cache.pop(cache_key, None)

    def fetch_fuel_prices():
        return get_prices(country, current_app._get_current_object(), force=force_refresh)

    # In-memory cache (30 min) backed by Redis (7 days) + live API in the service
    prices = get_cached(cache_key, fetch_fuel_prices, CACHE_DURATION)

    if not prices:
        return jsonify({'error': 'Fuel price service unavailable'}), 503

    return jsonify({
        'location': location,
        'country': country,
        'currency': prices.get('currency', '£'),
        'currency_code': prices.get('currency_code', 'GBP'),
        'prices': {
            'diesel': prices.get('diesel'),
            'petrol': prices.get('petrol'),
            'lpg': prices.get('lpg'),
            'premium': prices.get('premium'),
        },
        'source': prices.get('source', 'EU Weekly Oil Bulletin'),
        'last_update': prices.get('last_update'),
        'fetched_at': datetime.now(timezone.utc).isoformat()
    })


# Nominatim Usage Policy: max 1 request/second, descriptive User-Agent required.
# See: https://operations.osmfoundation.org/policies/nominatim/
_NOMINATIM_USER_AGENT = 'GearCargo/1.0 (https://github.com/gearcargo; gearcargo-app@proton.me)'
_NOMINATIM_THROTTLE_KEY = 'nominatim_throttle'
_NOMINATIM_MIN_INTERVAL_MS = 1100  # 1.1 s — slightly above the 1 req/s policy limit


def detect_country_from_coords(lat, lon):
    """Detect country code from coordinates using Nominatim reverse geocoding.

    Complies with the Nominatim Usage Policy (max 1 req/s) by acquiring a
    short-lived Redis lock before each request.  If the lock is already held
    by another worker the call is skipped gracefully and None is returned so
    the caller falls back to the user-supplied country value.
    """
    try:
        from app import redis_client
        if redis_client:
            # SET NX with automatic expiry — acts as a cross-worker throttle
            acquired = redis_client.set(
                _NOMINATIM_THROTTLE_KEY, 1,
                px=_NOMINATIM_MIN_INTERVAL_MS,
                nx=True,
            )
            if not acquired:
                current_app.logger.debug(
                    'Nominatim throttle active — skipping reverse-geocode request'
                )
                return None

        # S07: pass query params via `params=` rather than f-string interpolation.
        # lat/lon are already coerced to float by the caller, but letting requests
        # build and url-encode the query string is correct-by-construction and
        # prevents any future caller from injecting into the URL.
        response = requests.get(
            'https://nominatim.openstreetmap.org/reverse',
            params={'lat': lat, 'lon': lon, 'format': 'json'},
            headers={'User-Agent': _NOMINATIM_USER_AGENT},
            timeout=5,
        )
        if response.status_code == 200:
            data = response.json()
            country_code = data.get('address', {}).get('country_code', '').upper()
            return country_code if country_code else None
    except Exception as e:
        current_app.logger.warning(f'Country detection failed: {e}')
    return None


@external_bp.route('/currency-rates', methods=['GET'])
@token_required
def get_currency_rates(current_user):
    """Return live EUR-based exchange rates (ECB source via frankfurter.app).

    Rates are cached in Redis for 24 hours.  Falls back to hardcoded
    approximations when the upstream API is unavailable.

    Response:
      { "base": "EUR", "rates": { "GBP": 0.86, "RON": 5.0, ... },
        "source": "...", "fetched_at": "..." }
    """
    from app.services.fuel_price_service import get_live_eur_rates

    cache_key = 'currency_rates_eur'
    rates = get_cached(cache_key, lambda: get_live_eur_rates(current_app._get_current_object()),
                       timedelta(hours=24))

    if not rates:
        return jsonify({'error': 'Currency rate service unavailable'}), 503

    return jsonify({
        'base': 'EUR',
        'rates': rates,
        'source': 'European Central Bank via frankfurter.app',
        'fetched_at': datetime.now(timezone.utc).isoformat(),
    })

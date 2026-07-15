"""
GearCargo - Fuel Price Service

Fetches live fuel prices from official government sources with multi-level caching.

Data flow:
  1. In-memory cache (30 min) - handled by caller in external.py
  2. Redis cache (7 days) - persistent across restarts
  3. Live API fetch (GOV.UK for UK, EU Oil Bulletin for EU)
  4. Baseline hardcoded data (last resort)

Sources:
  - UK: https://www.gov.uk/government/statistics/weekly-road-fuel-prices
  - EU: https://energy.ec.europa.eu/data-and-analysis/weekly-oil-bulletin_en
"""

import csv
import json
import re
import io
from datetime import datetime, date, timezone
import requests
import redis as redis_mod


REDIS_PREFIX = "gearcargo:fuel:"
PRICE_TTL = 7 * 24 * 3600  # 7 days
FETCH_HEADERS = {
    'User-Agent': 'GearCargo/1.0 (car-management-app)',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

# ──────────────────────────────────────────────
#  Baseline prices — last known official data
#  Used ONLY when both API and Redis are empty
# ──────────────────────────────────────────────

BASELINE_PRICES = {
    'UK': {
        'currency': '£', 'currency_code': 'GBP',
        'diesel': 1.38, 'petrol': 1.34, 'lpg': 0.65, 'premium': 1.45,
        'source': 'UK Gov Weekly Statistics', 'last_update': '2026-02-03',
    },
    'GB': {
        'currency': '£', 'currency_code': 'GBP',
        'diesel': 1.38, 'petrol': 1.34, 'lpg': 0.65, 'premium': 1.45,
        'source': 'UK Gov Weekly Statistics', 'last_update': '2026-02-03',
    },
    'DE': {
        'currency': '€', 'currency_code': 'EUR',
        'diesel': 1.52, 'petrol': 1.68, 'lpg': 0.72, 'premium': 1.78,
        'source': 'EU Weekly Oil Bulletin', 'last_update': '2026-02-03',
    },
    'FR': {
        'currency': '€', 'currency_code': 'EUR',
        'diesel': 1.58, 'petrol': 1.72, 'lpg': 0.85, 'premium': 1.82,
        'source': 'EU Weekly Oil Bulletin', 'last_update': '2026-02-03',
    },
    'ES': {
        'currency': '€', 'currency_code': 'EUR',
        'diesel': 1.42, 'petrol': 1.52, 'lpg': 0.78, 'premium': 1.62,
        'source': 'EU Weekly Oil Bulletin', 'last_update': '2026-02-03',
    },
    'IT': {
        'currency': '€', 'currency_code': 'EUR',
        'diesel': 1.62, 'petrol': 1.78, 'lpg': 0.72, 'premium': 1.88,
        'source': 'EU Weekly Oil Bulletin', 'last_update': '2026-02-03',
    },
    'RO': {
        'currency': 'RON', 'currency_code': 'RON',
        'diesel': 7.20, 'petrol': 6.95, 'lpg': 3.50, 'premium': 7.85,
        'source': 'EU Weekly Oil Bulletin', 'last_update': '2026-02-03',
    },
    'PL': {
        'currency': 'PLN', 'currency_code': 'PLN',
        'diesel': 6.20, 'petrol': 6.05, 'lpg': 2.85, 'premium': 6.90,
        'source': 'EU Weekly Oil Bulletin', 'last_update': '2026-02-03',
    },
    'NL': {
        'currency': '€', 'currency_code': 'EUR',
        'diesel': 1.65, 'petrol': 1.95, 'lpg': 0.95, 'premium': 2.05,
        'source': 'EU Weekly Oil Bulletin', 'last_update': '2026-02-03',
    },
    'BE': {
        'currency': '€', 'currency_code': 'EUR',
        'diesel': 1.58, 'petrol': 1.72, 'lpg': 0.68, 'premium': 1.82,
        'source': 'EU Weekly Oil Bulletin', 'last_update': '2026-02-03',
    },
    'AT': {
        'currency': '€', 'currency_code': 'EUR',
        'diesel': 1.48, 'petrol': 1.58, 'lpg': 0.92, 'premium': 1.68,
        'source': 'EU Weekly Oil Bulletin', 'last_update': '2026-02-03',
    },
    'PT': {
        'currency': '€', 'currency_code': 'EUR',
        'diesel': 1.55, 'petrol': 1.68, 'lpg': 0.82, 'premium': 1.78,
        'source': 'EU Weekly Oil Bulletin', 'last_update': '2026-02-03',
    },
    'GR': {
        'currency': '€', 'currency_code': 'EUR',
        'diesel': 1.62, 'petrol': 1.75, 'lpg': 0.88, 'premium': 1.85,
        'source': 'EU Weekly Oil Bulletin', 'last_update': '2026-02-03',
    },
    'IE': {
        'currency': '€', 'currency_code': 'EUR',
        'diesel': 1.52, 'petrol': 1.65, 'lpg': 0.78, 'premium': 1.75,
        'source': 'EU Weekly Oil Bulletin', 'last_update': '2026-02-03',
    },
    'CZ': {
        'currency': 'CZK', 'currency_code': 'CZK',
        'diesel': 35.50, 'petrol': 36.20, 'lpg': 17.50, 'premium': 42.00,
        'source': 'EU Weekly Oil Bulletin', 'last_update': '2026-02-03',
    },
    'HU': {
        'currency': 'HUF', 'currency_code': 'HUF',
        'diesel': 595, 'petrol': 585, 'lpg': 285, 'premium': 645,
        'source': 'EU Weekly Oil Bulletin', 'last_update': '2026-02-03',
    },
    'SE': {
        'currency': 'SEK', 'currency_code': 'SEK',
        'diesel': 18.95, 'petrol': 18.25, 'lpg': 12.50, 'premium': 19.85,
        'source': 'EU Weekly Oil Bulletin', 'last_update': '2026-02-03',
    },
    'DK': {
        'currency': 'DKK', 'currency_code': 'DKK',
        'diesel': 12.85, 'petrol': 13.25, 'lpg': 8.50, 'premium': 14.50,
        'source': 'EU Weekly Oil Bulletin', 'last_update': '2026-02-03',
    },
    'FI': {
        'currency': '€', 'currency_code': 'EUR',
        'diesel': 1.72, 'petrol': 1.85, 'lpg': 0.95, 'premium': 1.95,
        'source': 'EU Weekly Oil Bulletin', 'last_update': '2026-02-03',
    },
    'BG': {
        'currency': 'BGN', 'currency_code': 'BGN',
        'diesel': 2.65, 'petrol': 2.55, 'lpg': 1.35, 'premium': 2.85,
        'source': 'EU Weekly Oil Bulletin', 'last_update': '2026-02-03',
    },
    'HR': {
        'currency': '€', 'currency_code': 'EUR',
        'diesel': 1.45, 'petrol': 1.52, 'lpg': 0.75, 'premium': 1.62,
        'source': 'EU Weekly Oil Bulletin', 'last_update': '2026-02-03',
    },
    'SK': {
        'currency': '€', 'currency_code': 'EUR',
        'diesel': 1.42, 'petrol': 1.55, 'lpg': 0.72, 'premium': 1.65,
        'source': 'EU Weekly Oil Bulletin', 'last_update': '2026-02-03',
    },
    'SI': {
        'currency': '€', 'currency_code': 'EUR',
        'diesel': 1.48, 'petrol': 1.52, 'lpg': 0.82, 'premium': 1.62,
        'source': 'EU Weekly Oil Bulletin', 'last_update': '2026-02-03',
    },
    'LU': {
        'currency': '€', 'currency_code': 'EUR',
        'diesel': 1.35, 'petrol': 1.45, 'lpg': 0.65, 'premium': 1.55,
        'source': 'EU Weekly Oil Bulletin', 'last_update': '2026-02-03',
    },
    'LT': {
        'currency': '€', 'currency_code': 'EUR',
        'diesel': 1.38, 'petrol': 1.48, 'lpg': 0.72, 'premium': 1.58,
        'source': 'EU Weekly Oil Bulletin', 'last_update': '2026-02-03',
    },
    'LV': {
        'currency': '€', 'currency_code': 'EUR',
        'diesel': 1.42, 'petrol': 1.52, 'lpg': 0.75, 'premium': 1.62,
        'source': 'EU Weekly Oil Bulletin', 'last_update': '2026-02-03',
    },
    'EE': {
        'currency': '€', 'currency_code': 'EUR',
        'diesel': 1.45, 'petrol': 1.55, 'lpg': 0.78, 'premium': 1.65,
        'source': 'EU Weekly Oil Bulletin', 'last_update': '2026-02-03',
    },
    'CY': {
        'currency': '€', 'currency_code': 'EUR',
        'diesel': 1.38, 'petrol': 1.42, 'lpg': 0.75, 'premium': 1.52,
        'source': 'EU Weekly Oil Bulletin', 'last_update': '2026-02-03',
    },
    'MT': {
        'currency': '€', 'currency_code': 'EUR',
        'diesel': 1.21, 'petrol': 1.34, 'lpg': 0.65, 'premium': 1.44,
        'source': 'EU Weekly Oil Bulletin', 'last_update': '2026-02-03',
    },
    'NO': {
        'currency': 'NOK', 'currency_code': 'NOK',
        'diesel': 19.50, 'petrol': 19.80, 'lpg': 12.50, 'premium': 21.50,
        'source': 'Norway Statistics', 'last_update': '2026-02-03',
    },
    'CH': {
        'currency': 'CHF', 'currency_code': 'CHF',
        'diesel': 1.82, 'petrol': 1.75, 'lpg': 1.15, 'premium': 1.95,
        'source': 'Swiss Federal Statistics', 'last_update': '2026-02-03',
    },
}

# Fallback EUR → local-currency exchange rates.
# These are only used when the live frankfurter.app API is unreachable.
_EUR_RATES_FALLBACK = {
    'BGN': 1.95583,  # Fixed peg since 1999
    'CZK': 25.3,
    'DKK': 7.46,     # Near-fixed peg
    'HUF': 400.0,
    'PLN': 4.25,
    'RON': 5.0,
    'SEK': 11.0,
    'NOK': 11.8,
    'CHF': 0.94,
    'GBP': 0.86,
    'USD': 1.08,
}

# Redis key for caching live currency rates (24-hour TTL)
_RATES_REDIS_KEY = 'gearcargo:currency_rates'
_RATES_TTL = 24 * 3600


def get_live_eur_rates(app=None):
    """
    Return a dict of EUR → foreign currency conversion rates.

    Fetch from frankfurter.app (ECB-backed, free, no API key).
    Result is cached in Redis for 24 hours; falls back to hardcoded
    approximations if the API and Redis are both unavailable.
    """
    # Try Redis cache first
    if app is not None:
        r = _redis_client(app)
        if r:
            try:
                raw = r.get(_RATES_REDIS_KEY)
                if raw:
                    return json.loads(raw)
            except Exception:
                pass

    # Fetch live rates from frankfurter.app (ECB source, free, no key)
    try:
        resp = requests.get(
            'https://api.frankfurter.app/latest',
            params={'from': 'EUR'},
            headers={'User-Agent': 'GearCargo/1.0'},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        rates = data.get('rates', {})
        # API returns X units of each currency per 1 EUR
        if rates:
            if app is not None:
                r = _redis_client(app)
                if r:
                    try:
                        r.setex(_RATES_REDIS_KEY, _RATES_TTL, json.dumps(rates))
                    except Exception:
                        pass
            return rates
    except Exception as exc:
        if app is not None:
            try:
                app.logger.warning(f'Currency rate fetch failed: {exc}')
            except Exception:
                pass

    return _EUR_RATES_FALLBACK

# Country code → country name for the EU Oil Bulletin
EU_COUNTRY_NAMES = {
    'AT': 'Austria', 'BE': 'Belgium', 'BG': 'Bulgaria', 'CY': 'Cyprus',
    'CZ': 'Czech Republic', 'DE': 'Germany', 'DK': 'Denmark', 'EE': 'Estonia',
    'ES': 'Spain', 'FI': 'Finland', 'FR': 'France', 'GR': 'Greece',
    'HR': 'Croatia', 'HU': 'Hungary', 'IE': 'Ireland', 'IT': 'Italy',
    'LT': 'Lithuania', 'LU': 'Luxembourg', 'LV': 'Latvia', 'MT': 'Malta',
    'NL': 'Netherlands', 'PL': 'Poland', 'PT': 'Portugal', 'RO': 'Romania',
    'SE': 'Sweden', 'SI': 'Slovenia', 'SK': 'Slovakia',
    'NO': 'Norway', 'CH': 'Switzerland',
}


# ──────────────────────────────────────────────
#  Redis helpers
# ──────────────────────────────────────────────

def _redis_client(app):
    """Get Redis client for fuel price persistence."""
    try:
        url = app.config.get('REDIS_URL', 'redis://localhost:6379/0')
        return redis_mod.from_url(url, decode_responses=True)
    except Exception:
        return None


def _redis_get(country, app):
    """Load cached prices from Redis."""
    r = _redis_client(app)
    if not r:
        return None
    try:
        raw = r.get(f"{REDIS_PREFIX}{country}")
        return json.loads(raw) if raw else None
    except Exception:
        return None


def _redis_set(country, data, app):
    """Persist prices in Redis with 7-day TTL."""
    r = _redis_client(app)
    if not r:
        return
    try:
        r.setex(f"{REDIS_PREFIX}{country}", PRICE_TTL, json.dumps(data))
    except Exception:
        pass


# ──────────────────────────────────────────────
#  Public API
# ──────────────────────────────────────────────

def record_price_history(country, data, app):
    """Persist one weekly national price point (F25) — idempotent per
    (country, last_update date). Called after successful live fetches only;
    baseline fallback data is NEVER recorded. Any failure is logged and
    swallowed so history can never break price serving.
    """
    try:
        raw = data.get('last_update')
        if not raw:
            return
        price_date = datetime.strptime(_normalize_date(str(raw)), '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return

    from flask import has_app_context
    from app import db

    def _upsert():
        from app.models import FuelPriceHistory
        row = FuelPriceHistory.query.filter_by(
            country=country, price_date=price_date).first()
        if row is None:
            row = FuelPriceHistory(country=country, price_date=price_date)
            db.session.add(row)
        row.diesel = data.get('diesel')
        row.petrol = data.get('petrol')
        row.lpg = data.get('lpg')
        row.premium = data.get('premium')
        row.currency_code = data.get('currency_code')
        row.source = (data.get('source') or '')[:64] or None
        db.session.commit()

    try:
        if has_app_context():
            _upsert()
        else:
            with app.app_context():
                _upsert()
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        app.logger.warning(f"Fuel price history record failed for {country}: {e}")


def _tag_freshness(data, baseline=False):
    """Return a tagged copy with machine-readable freshness markers (F20).

    ``baseline`` marks hardcoded fallback data; ``stale`` is computed at
    return time (never persisted) from ``last_update`` being older than 14
    days — so a cached entry's staleness is re-judged on every read.
    """
    out = dict(data)
    out['baseline'] = bool(baseline)
    stale = False
    raw = out.get('last_update')
    if raw:
        try:
            updated = datetime.strptime(_normalize_date(str(raw)), '%Y-%m-%d').date()
            stale = (date.today() - updated).days > 14
        except ValueError:
            pass  # unparseable date — don't guess
    out['stale'] = stale
    return out


def get_prices(country, app, force=False):
    """
    Get fuel prices for a country with multi-level fallback.

    Priority: Redis cache → Live API → Stale Redis → Baseline data.
    On force=True: skips Redis, goes straight to API.
    """
    country = country.upper()

    # 1. Redis cache (skip on force refresh)
    if not force:
        cached = _redis_get(country, app)
        if cached:
            app.logger.debug(f"Fuel prices [{country}]: Redis cache hit")
            return _tag_freshness(cached)

    # 2. Live API fetch
    fetched = None
    try:
        if country in ('UK', 'GB'):
            fetched = _fetch_uk_prices(app)
        else:
            fetched = _fetch_eu_prices_for_country(country, app)

        if fetched:
            _redis_set(country, fetched, app)
            record_price_history(country, fetched, app)   # F25 — live data only
            # Also update GB/UK alias
            if country in ('UK', 'GB'):
                alias = 'GB' if country == 'UK' else 'UK'
                _redis_set(alias, fetched, app)
                record_price_history(alias, fetched, app)
            app.logger.info(
                f"Fuel prices [{country}]: fresh data fetched, "
                f"last_update={fetched.get('last_update')}"
            )
            return _tag_freshness(fetched)
    except Exception as e:
        app.logger.warning(f"Fuel prices [{country}]: API fetch failed — {e}")

    # 3. Stale Redis (only if we skipped it above due to force=True)
    if force:
        cached = _redis_get(country, app)
        if cached:
            app.logger.info(f"Fuel prices [{country}]: using stale Redis after fetch failure")
            return _tag_freshness(cached)

    # 4. Baseline hardcoded data
    app.logger.info(f"Fuel prices [{country}]: using baseline data")
    return _tag_freshness(BASELINE_PRICES.get(country, BASELINE_PRICES.get('UK', {})),
                          baseline=True)


def refresh_all_prices(app):
    """
    Refresh prices for all supported countries.
    Called by the weekly scheduler job.
    Returns (updated_count, failed_count).
    """
    updated = 0
    failed = 0

    # Fetch UK first
    try:
        data = _fetch_uk_prices(app)
        if data:
            _redis_set('UK', data, app)
            _redis_set('GB', data, app)
            record_price_history('UK', data, app)   # F25 — accrue the series
            record_price_history('GB', data, app)
            updated += 1
    except Exception as e:
        app.logger.warning(f"Scheduled refresh failed for UK: {e}")
        failed += 1

    # Fetch EU countries
    try:
        eu_data = _fetch_eu_bulletin_all(app)
        if eu_data:
            for cc, prices in eu_data.items():
                _redis_set(cc, prices, app)
                record_price_history(cc, prices, app)   # F25
                updated += 1
        else:
            failed += len(EU_COUNTRY_NAMES)
    except Exception as e:
        app.logger.warning(f"Scheduled refresh failed for EU: {e}")
        failed += len(EU_COUNTRY_NAMES)

    app.logger.info(f"Fuel price refresh complete: {updated} updated, {failed} failed")
    return updated, failed


# ──────────────────────────────────────────────
#  UK Fetcher — GOV.UK Weekly Road Fuel Prices
# ──────────────────────────────────────────────

def _fetch_uk_prices(app):
    """
    Fetch latest UK fuel prices from GOV.UK.

    Flow:
      1. Hit the GOV.UK Content API for the statistics page metadata
      2. Extract the CSV attachment URL
      3. Download and parse the CSV
    """
    meta_url = "https://www.gov.uk/api/content/government/statistics/weekly-road-fuel-prices"
    resp = requests.get(meta_url, headers=FETCH_HEADERS, timeout=15)
    resp.raise_for_status()
    meta = resp.json()

    csv_url = _find_govuk_csv_url(meta)
    if not csv_url:
        raise ValueError("No CSV attachment found in GOV.UK statistics page")

    app.logger.debug(f"UK fuel CSV URL: {csv_url}")
    csv_resp = requests.get(csv_url, headers=FETCH_HEADERS, timeout=15)
    csv_resp.raise_for_status()

    return _parse_uk_csv(csv_resp.text)


def _find_govuk_csv_url(meta):
    """Extract CSV download URL from GOV.UK Content API response."""
    # Method 1: links → documents → details → attachments
    for doc in meta.get('links', {}).get('documents', []):
        for att in doc.get('details', {}).get('attachments', []):
            url = att.get('url', '')
            if '.csv' in url.lower():
                return _absolute_govuk(url)

    # Method 2: parse HTML fragments in details.documents
    for html_frag in meta.get('details', {}).get('documents', []):
        if isinstance(html_frag, str):
            urls = re.findall(r'href="([^"]*\.csv[^"]*)"', html_frag, re.I)
            if urls:
                return _absolute_govuk(urls[0])

    # Method 3: details.attachments directly
    for att in meta.get('details', {}).get('attachments', []):
        url = att.get('url', '')
        if '.csv' in url.lower():
            return _absolute_govuk(url)

    return None


def _absolute_govuk(url):
    """Ensure a GOV.UK URL is absolute."""
    if url.startswith('http'):
        return url
    return f"https://www.gov.uk{url}"


def _parse_uk_csv(text):
    """
    Parse the GOV.UK weekly road fuel prices CSV.
    
    Typical columns: Date, ULSP (pence/litre), ULSD (pence/litre),
    Super unleaded (pence/litre), ...
    Prices are in pence per litre → divide by 100 for pounds.
    """
    lines = text.strip().split('\n')
    reader = csv.reader(lines)

    headers = None
    latest_row = None

    for row in reader:
        if not row or all(not c.strip() for c in row):
            continue

        joined = ' '.join(row).lower()

        # Detect header row
        if not headers:
            if ('ulsp' in joined or 'ulsd' in joined or 'diesel' in joined or
                    ('date' in joined and ('price' in joined or 'pence' in joined or 'litre' in joined))):
                headers = [h.strip() for h in row]
                continue
        else:
            # Data rows — the last valid row is the most recent
            first = row[0].strip()
            if first and len(row) >= 2:
                # Accept rows starting with a date-like value
                if (re.match(r'\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}', first) or
                        re.match(r'\d{4}[/.-]\d{1,2}[/.-]\d{1,2}', first)):
                    latest_row = row

    if not headers or not latest_row:
        raise ValueError("Could not find valid data in GOV.UK CSV")

    # Map header → value
    col = {}
    for i, h in enumerate(headers):
        if i < len(latest_row) and latest_row[i].strip():
            col[h.lower()] = latest_row[i].strip()

    diesel = petrol = premium = None
    date_val = None

    for key, val in col.items():
        kl = key.lower()

        # Date column
        if 'date' in kl:
            date_val = _normalize_date(val)
            continue

        # Skip non-price columns (duty rates, VAT rates, etc.)
        if any(skip in kl for skip in ('duty', 'vat', 'rate', 'tax')):
            continue

        # Only match columns that look like pump/retail prices
        if not any(tag in kl for tag in ('price', 'pump', 'ulsp', 'ulsd',
                                          'diesel', 'petrol', 'unleaded',
                                          'super', 'premium')):
            continue

        # Numeric value
        try:
            num = float(val.replace(',', ''))
        except (ValueError, TypeError):
            continue

        # Prices >10 are in pence → convert to pounds
        price = round(num / 100, 2) if num > 10 else round(num, 2)

        if 'ulsd' in kl or 'diesel' in kl:
            diesel = price
        elif 'ulsp' in kl or 'petrol' in kl or ('unleaded' in kl and 'super' not in kl):
            petrol = price
        elif 'super' in kl or 'premium' in kl:
            premium = price

    if not date_val:
        date_val = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    return {
        'currency': '£',
        'currency_code': 'GBP',
        'diesel': diesel or BASELINE_PRICES['UK']['diesel'],
        'petrol': petrol or BASELINE_PRICES['UK']['petrol'],
        'lpg': BASELINE_PRICES['UK']['lpg'],  # LPG not published by GOV.UK
        'premium': premium or BASELINE_PRICES['UK']['premium'],
        'source': 'UK Gov Weekly Statistics',
        'last_update': date_val,
    }


# ──────────────────────────────────────────────
#  EU Fetcher — Weekly Oil Bulletin
# ──────────────────────────────────────────────

# The EU Oil Bulletin page where the weekly data is published
EU_BULLETIN_PAGE = (
    "https://energy.ec.europa.eu/data-and-analysis/weekly-oil-bulletin_en"
)

# Country name patterns used in the Oil Bulletin (mapped to ISO codes)
_BULLETIN_COUNTRY_MAP = {
    'austria': 'AT', 'belgium': 'BE', 'bulgaria': 'BG', 'croatia': 'HR',
    'cyprus': 'CY', 'czech': 'CZ', 'denmark': 'DK', 'estonia': 'EE',
    'finland': 'FI', 'france': 'FR', 'germany': 'DE', 'greece': 'GR',
    'hungary': 'HU', 'ireland': 'IE', 'italy': 'IT', 'latvia': 'LV',
    'lithuania': 'LT', 'luxembourg': 'LU', 'malta': 'MT',
    'netherlands': 'NL', 'poland': 'PL', 'portugal': 'PT',
    'romania': 'RO', 'slovakia': 'SK', 'slovenia': 'SI', 'spain': 'ES',
    'sweden': 'SE',
}


def _fetch_eu_prices_for_country(country, app):
    """Fetch prices for a specific EU country."""
    all_prices = _fetch_eu_bulletin_all(app)
    if all_prices and country in all_prices:
        return all_prices[country]
    return None


def _fetch_eu_bulletin_all(app):
    """
    Fetch EU Oil Bulletin data for all EU countries.

    The EC publishes weekly retail prices (with taxes) as an XLSX file.
    We parse it using Python's built-in zipfile + ElementTree — no extra deps.

    Prices in the spreadsheet are EUR per 1000 litres; we divide by 1000
    to get EUR/L, then apply approximate exchange rates for non-EUR countries.
    """
    try:
        resp = requests.get(EU_BULLETIN_PAGE, headers=FETCH_HEADERS, timeout=20)
        resp.raise_for_status()
        page_html = resp.text

        # Find the XLSX download link.
        # We prefer the "with Taxes" file (retail pump prices incl. VAT/duty).
        xlsx_links = re.findall(
            r'href="(/document/download/[^"]*\.xlsx[^"]*)"',
            page_html, re.I
        )

        xlsx_url = None
        for link in xlsx_links:
            decoded = link.lower()
            # Pick the weekly-prices-with-taxes file; skip history and duty files
            if 'without' in decoded or 'histor' in decoded or 'dut' in decoded:
                continue
            if 'price' in decoded or 'bulletin' in decoded:
                xlsx_url = link
                break
        # Fallback: first XLSX link that isn't the history/duties file
        if not xlsx_url:
            for link in xlsx_links:
                if 'histor' not in link.lower() and 'dut' not in link.lower():
                    xlsx_url = link
                    break

        if not xlsx_url:
            app.logger.info("EU Oil Bulletin: no XLSX link found on page")
            return None

        full_url = f"https://energy.ec.europa.eu{xlsx_url}"
        app.logger.debug(f"EU Oil Bulletin XLSX URL: {full_url}")
        data_resp = requests.get(full_url, headers=FETCH_HEADERS, timeout=30)
        data_resp.raise_for_status()

        return _parse_eu_bulletin_xlsx(data_resp.content, app)

    except Exception as e:
        app.logger.warning(f"EU Oil Bulletin fetch failed: {e}")
        return None


def _parse_eu_bulletin_xlsx(content, app):
    """
    Parse the EU Oil Bulletin XLSX using only Python built-ins.

    Spreadsheet layout (one sheet):
      Row 1:  column headers — B=Euro-super 95, C=Gas oil auto, G=LPG
      Row 2:  units row — column A holds an Excel date serial
      Row 3+: one row per member state

    All prices are in EUR per 1000 litres.  We divide by 1000 to get EUR/L
    and then multiply by the local exchange rate where applicable.
    """
    import zipfile
    import xml.etree.ElementTree as ET

    NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'

    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except Exception as e:
        app.logger.warning(f"EU Oil Bulletin: could not open XLSX as ZIP: {e}")
        return None

    # --- Shared strings ---
    shared = []
    if 'xl/sharedStrings.xml' in zf.namelist():
        ss_root = ET.fromstring(zf.read('xl/sharedStrings.xml'))
        for si in ss_root.findall(f'.//{{{NS}}}si'):
            text = ''.join(t.text or '' for t in si.findall(f'.//{{{NS}}}t')).strip()
            shared.append(text)

    # --- Worksheet ---
    sheet_files = [
        n for n in zf.namelist()
        if n.startswith('xl/worksheets/sheet') and n.endswith('.xml')
    ]
    if not sheet_files:
        app.logger.warning("EU Oil Bulletin XLSX: no worksheet found")
        return None

    ws_root = ET.fromstring(zf.read(sheet_files[0]))

    petrol_col = diesel_col = lpg_col = None
    date_val = None
    results = {}

    def _cell_val(c_el):
        """Return (is_string, value) for a cell element."""
        v = c_el.find(f'{{{NS}}}v')
        if v is None or not v.text:
            return False, None
        if c_el.get('t') == 's':
            idx = int(v.text)
            return True, shared[idx] if idx < len(shared) else ''
        return False, v.text

    def _col_letter(cell_ref):
        """Extract column letter(s) from a cell reference like 'AB12'."""
        return re.sub(r'\d', '', cell_ref)

    def _eur_per_litre(num_str):
        """Convert a '1000 L' string value to EUR/L."""
        try:
            return float(num_str) / 1000.0
        except (ValueError, TypeError):
            return None

    for row_el in ws_root.findall(f'.//{{{NS}}}row'):
        r = int(row_el.get('r', 0))

        cells = {}  # col_letter → (is_string, value)
        for c in row_el.findall(f'{{{NS}}}c'):
            col = _col_letter(c.get('r', ''))
            is_str, val = _cell_val(c)
            if val is not None:
                cells[col] = (is_str, val)

        if r == 1:
            # Identify price columns from header text
            for col, (is_str, val) in cells.items():
                if not is_str:
                    continue
                vl = val.lower()
                if ('super 95' in vl or 'euro-super' in vl or 'eurosuper' in vl) and petrol_col is None:
                    petrol_col = col
                elif ('gas oil auto' in vl or ('gas oil' in vl and 'chauf' not in vl and 'heat' not in vl)) and diesel_col is None:
                    diesel_col = col
                elif ('gpl' in vl or 'lpg' in vl) and lpg_col is None:
                    lpg_col = col

        elif r == 2:
            # Column A in the units row holds the Excel date serial
            a = cells.get('A')
            if a and not a[0] and a[1]:
                try:
                    from datetime import date as _dt, timedelta
                    serial = int(float(a[1]))
                    d = _dt(1899, 12, 30) + timedelta(days=serial)
                    date_val = d.strftime('%Y-%m-%d')
                except (ValueError, TypeError):
                    pass

        elif r >= 3:
            # Data row — column A is the country name (string)
            a = cells.get('A')
            if not a or not a[0]:
                continue
            country_name = a[1].strip().lower()

            cc = _BULLETIN_COUNTRY_MAP.get(country_name)
            if not cc:
                for name, code in _BULLETIN_COUNTRY_MAP.items():
                    if name in country_name:
                        cc = code
                        break
            if not cc:
                continue

            # Extract EUR/1000L values → EUR/L
            def _get(col):
                if col and col in cells:
                    is_str, val = cells[col]
                    if not is_str and val:
                        return _eur_per_litre(val)
                return None

            petrol_eur = _get(petrol_col)
            diesel_eur = _get(diesel_col)
            lpg_eur = _get(lpg_col)

            baseline = BASELINE_PRICES.get(cc, {})
            local_cc = baseline.get('currency_code', 'EUR')
            local_sym = baseline.get('currency', '\u20ac')

            # Apply local exchange rate so non-EUR users see local currency prices
            _rates = get_live_eur_rates(app)
            rate = _rates.get(local_cc, 1.0)

            results[cc] = {
                'currency': local_sym,
                'currency_code': local_cc,
                'diesel': round(diesel_eur * rate, 2) if diesel_eur else baseline.get('diesel'),
                'petrol': round(petrol_eur * rate, 2) if petrol_eur else baseline.get('petrol'),
                'lpg': round(lpg_eur * rate, 2) if lpg_eur else baseline.get('lpg'),
                'premium': baseline.get('premium'),  # Bulletin does not publish premium
                'source': 'EU Weekly Oil Bulletin',
                'last_update': date_val or datetime.now(timezone.utc).strftime('%Y-%m-%d'),
            }

    if results:
        app.logger.info(
            f"EU Oil Bulletin XLSX: parsed {len(results)} countries, date={date_val}"
        )
    return results if results else None


# ──────────────────────────────────────────────
#  Utilities
# ──────────────────────────────────────────────

def _normalize_date(s):
    """Try various date formats → YYYY-MM-DD."""
    s = s.strip()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%d %b %Y',
                '%d %B %Y', '%m/%d/%Y', '%Y/%m/%d', '%d.%m.%Y'):
        try:
            return datetime.strptime(s, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return s

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

import json
import re
import csv
import io
import time
from datetime import datetime
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
            return cached

    # 2. Live API fetch
    fetched = None
    try:
        if country in ('UK', 'GB'):
            fetched = _fetch_uk_prices(app)
        else:
            fetched = _fetch_eu_prices_for_country(country, app)

        if fetched:
            _redis_set(country, fetched, app)
            # Also update GB/UK alias
            if country in ('UK', 'GB'):
                alias = 'GB' if country == 'UK' else 'UK'
                _redis_set(alias, fetched, app)
            app.logger.info(
                f"Fuel prices [{country}]: fresh data fetched, "
                f"last_update={fetched.get('last_update')}"
            )
            return fetched
    except Exception as e:
        app.logger.warning(f"Fuel prices [{country}]: API fetch failed — {e}")

    # 3. Stale Redis (only if we skipped it above due to force=True)
    if force:
        cached = _redis_get(country, app)
        if cached:
            app.logger.info(f"Fuel prices [{country}]: using stale Redis after fetch failure")
            return cached

    # 4. Baseline hardcoded data
    app.logger.info(f"Fuel prices [{country}]: using baseline data")
    return BASELINE_PRICES.get(country, BASELINE_PRICES.get('UK', {}))


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
        date_val = datetime.utcnow().strftime('%Y-%m-%d')

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

    Strategy:
      1. Fetch the Oil Bulletin page
      2. Find the download link for the latest data file (CSV or XLS)
      3. Download and parse it

    If the page structure changes, this degrades gracefully to None.
    """
    try:
        resp = requests.get(EU_BULLETIN_PAGE, headers=FETCH_HEADERS, timeout=20)
        resp.raise_for_status()
        page_html = resp.text

        # Look for CSV download link first (preferred — no extra deps needed)
        csv_links = re.findall(
            r'href="([^"]*(?:price|bulletin|fuel)[^"]*\.csv)"',
            page_html, re.I
        )

        if csv_links:
            csv_url = csv_links[0]
            if not csv_url.startswith('http'):
                csv_url = f"https://energy.ec.europa.eu{csv_url}"
            data_resp = requests.get(csv_url, headers=FETCH_HEADERS, timeout=20)
            data_resp.raise_for_status()
            return _parse_eu_csv(data_resp.text, app)

        # Try to find the JSON data embedded in the page (some EC pages
        # include inline JSON for their visualization widgets)
        json_blocks = re.findall(
            r'var\s+(?:data|prices|oilData)\s*=\s*(\{.*?\});',
            page_html, re.S
        )
        for block in json_blocks:
            try:
                data = json.loads(block)
                parsed = _parse_eu_inline_json(data, app)
                if parsed:
                    return parsed
            except (json.JSONDecodeError, ValueError):
                continue

        app.logger.info("EU Oil Bulletin: no parseable data found on page")
        return None

    except Exception as e:
        app.logger.warning(f"EU Oil Bulletin fetch failed: {e}")
        return None


def _parse_eu_csv(text, app):
    """
    Parse EU Oil Bulletin CSV into per-country price dicts.
    The CSV format varies but typically has columns for country + fuel types.
    """
    results = {}
    reader = csv.DictReader(io.StringIO(text))

    for row in reader:
        # Try to identify the country column
        country_val = None
        for key in ('country', 'Country', 'member_state', 'Member State', 'COUNTRY'):
            if key in row and row[key]:
                country_val = row[key].strip().lower()
                break

        if not country_val:
            continue

        # Map country name to ISO code
        cc = _BULLETIN_COUNTRY_MAP.get(country_val)
        if not cc:
            # Try partial match
            for name, code in _BULLETIN_COUNTRY_MAP.items():
                if name in country_val or country_val in name:
                    cc = code
                    break
        if not cc:
            continue

        # Extract prices (try various column names)
        diesel = _extract_price(row, ['diesel', 'gas oil', 'gasoil', 'automotive diesel'])
        petrol = _extract_price(row, ['petrol', 'gasoline', 'euro 95', 'eurosuper 95', 'e10', 'unleaded'])
        lpg = _extract_price(row, ['lpg', 'autogas', 'auto gas'])
        premium = _extract_price(row, ['premium', 'super', 'euro 98', 'e5', 'super 98'])
        date_str = None
        for key in ('date', 'Date', 'DATE', 'week', 'Week', 'period', 'Period'):
            if key in row and row[key]:
                date_str = _normalize_date(row[key])
                break

        baseline = BASELINE_PRICES.get(cc, {})
        results[cc] = {
            'currency': baseline.get('currency', '€'),
            'currency_code': baseline.get('currency_code', 'EUR'),
            'diesel': diesel or baseline.get('diesel'),
            'petrol': petrol or baseline.get('petrol'),
            'lpg': lpg or baseline.get('lpg'),
            'premium': premium or baseline.get('premium'),
            'source': 'EU Weekly Oil Bulletin',
            'last_update': date_str or datetime.utcnow().strftime('%Y-%m-%d'),
        }

    if results:
        app.logger.info(f"EU Oil Bulletin: parsed prices for {len(results)} countries")
    return results if results else None


def _parse_eu_inline_json(data, app):
    """Parse inline JSON from the Oil Bulletin page visualization."""
    # This handles the case where the page embeds data for its charts
    # Structure varies — try common patterns
    results = {}

    if isinstance(data, dict):
        for key, val in data.items():
            key_lower = key.lower()
            cc = _BULLETIN_COUNTRY_MAP.get(key_lower)
            if cc and isinstance(val, dict):
                baseline = BASELINE_PRICES.get(cc, {})
                results[cc] = {
                    'currency': baseline.get('currency', '€'),
                    'currency_code': baseline.get('currency_code', 'EUR'),
                    'diesel': val.get('diesel') or baseline.get('diesel'),
                    'petrol': val.get('petrol') or val.get('gasoline') or baseline.get('petrol'),
                    'lpg': val.get('lpg') or baseline.get('lpg'),
                    'premium': val.get('premium') or val.get('super') or baseline.get('premium'),
                    'source': 'EU Weekly Oil Bulletin',
                    'last_update': val.get('date', datetime.utcnow().strftime('%Y-%m-%d')),
                }

    return results if results else None


def _extract_price(row, patterns):
    """Extract a numeric price from a CSV row by trying multiple column name patterns."""
    for col_name, col_val in row.items():
        cl = col_name.lower().strip()
        for pattern in patterns:
            if pattern in cl:
                try:
                    val = float(col_val.strip().replace(',', '.'))
                    return round(val, 2)
                except (ValueError, TypeError, AttributeError):
                    pass
    return None


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

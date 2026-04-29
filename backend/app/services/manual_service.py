"""
GearCargo - Vehicle Manual Resolver Service

Dynamically resolves owner's manual URLs for any vehicle based on
make/model/year from the database and the user's language preference.
Only returns links to official OEM portals or reputable aggregators.
Never downloads, caches, or redistributes PDF content.
"""

import re
import json
import logging
from urllib.parse import quote_plus

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Language → country TLD / full name mappings
# ---------------------------------------------------------------------------

LANG_TO_TLD = {
    'ro': 'ro',
    'es': 'es',
    'en': 'co.uk',
}

LANG_TO_NAME = {
    'ro': 'romanian',
    'es': 'spanish',
    'en': 'english',
}

# ---------------------------------------------------------------------------
# OEM URL templates – {tld}, {model}, {year} are filled at runtime from DB
# ---------------------------------------------------------------------------

OEM_TEMPLATES = {
    'nissan': [
        'https://www.nissan.{tld}/owners/manuals/{model}/{year}.html',
        'https://www.nissan.{tld}/owners/manuals/{model}.html',
        'https://www.nissan.{tld}/owners/manuals.html',
    ],
    'toyota': [
        'https://www.toyota.{tld}/owners/manuals/{model}/{year}',
        'https://www.toyota.{tld}/owners/manuals/{model}',
        'https://www.toyota.{tld}/owners/manuals',
    ],
    'volkswagen': [
        'https://www.volkswagen.{tld}/owners/manuals/{model}/{year}',
        'https://www.volkswagen.{tld}/owners/manuals',
    ],
    'dacia': [
        'https://www.dacia.{tld}/owners/manuals/{model}/{year}',
        'https://www.dacia.{tld}/owners/manuals',
    ],
    'renault': [
        'https://www.renault.{tld}/owners/manuals/{model}/{year}',
        'https://www.renault.{tld}/owners/manuals',
    ],
    'ford': [
        'https://www.ford.{tld}/owners/manuals/{model}/{year}',
        'https://www.ford.{tld}/support/vehicle-manuals',
    ],
    'bmw': [
        'https://www.bmw.{tld}/owners/manuals/{model}/{year}',
        'https://www.bmw.{tld}/owners/manuals',
    ],
    'skoda': [
        'https://www.skoda.{tld}/owners/manuals/{model}/{year}',
        'https://www.skoda.{tld}/owners/manuals',
    ],
    'hyundai': [
        'https://www.hyundai.{tld}/owners/manuals/{model}/{year}',
        'https://www.hyundai.{tld}/owners/manuals',
    ],
    'kia': [
        'https://www.kia.{tld}/owners/manuals/{model}/{year}',
        'https://www.kia.com/owners/manuals',
    ],
    'mercedes-benz': [
        'https://www.mercedes-benz.{tld}/owners/manuals/{model}/{year}',
        'https://www.mercedes-benz.{tld}/owners/manuals',
    ],
    'mercedes': [
        'https://www.mercedes-benz.{tld}/owners/manuals/{model}/{year}',
        'https://www.mercedes-benz.{tld}/owners/manuals',
    ],
    'peugeot': [
        'https://www.peugeot.{tld}/owners/manuals/{model}/{year}',
        'https://www.peugeot.{tld}/owners/manuals',
    ],
    'opel': [
        'https://www.opel.{tld}/owners/manuals/{model}/{year}',
        'https://www.opel.{tld}/owners/manuals',
    ],
    'audi': [
        'https://www.audi.{tld}/owners/manuals/{model}/{year}',
        'https://www.audi.{tld}/owners/manuals',
    ],
    'fiat': [
        'https://www.fiat.{tld}/owners/manuals/{model}/{year}',
        'https://www.fiat.{tld}/owners/manuals',
    ],
    'seat': [
        'https://www.seat.{tld}/owners/manuals/{model}/{year}',
        'https://www.seat.{tld}/owners/manuals',
    ],
    'volvo': [
        'https://www.volvocars.com/{tld}/support/manuals/{model}/{year}',
        'https://www.volvocars.com/{tld}/support/manuals',
    ],
    'mazda': [
        'https://www.mazda.{tld}/owners/manuals/{model}/{year}',
        'https://www.mazda.{tld}/owners/manuals',
    ],
    'honda': [
        'https://www.honda.{tld}/owners/manuals/{model}/{year}',
        'https://www.honda.{tld}/owners/manuals',
    ],
    'suzuki': [
        'https://www.suzuki.{tld}/owners/manuals/{model}/{year}',
        'https://www.suzuki.{tld}/owners/manuals',
    ],
    'citroen': [
        'https://www.citroen.{tld}/owners/manuals/{model}/{year}',
        'https://www.citroen.{tld}/owners/manuals',
    ],
    'mitsubishi': [
        'https://www.mitsubishi-motors.{tld}/owners/manuals/{model}/{year}',
        'https://www.mitsubishi-motors.{tld}/owners/manuals',
    ],
}

# Aggregator search templates
AGGREGATOR_TEMPLATES = [
    {
        'name': 'CARMANS.NET',
        'url': 'https://www.carmans.net/manual/{make}/{model}/{year}',
    },
]

# Redis cache key prefix and TTL
CACHE_PREFIX = 'manual:'
CACHE_TTL = 7 * 24 * 60 * 60  # 7 days


# ---------------------------------------------------------------------------
# Input sanitisation — SSRF / injection prevention
# ---------------------------------------------------------------------------

_SAFE_RE = re.compile(r'[^a-zA-Z0-9 \-]')


def _sanitize(value: str) -> str:
    """Allow only alphanumeric, spaces, and hyphens."""
    return _SAFE_RE.sub('', str(value).strip())


def _slug(value: str) -> str:
    """Lowercase slug for URL path segments (spaces → hyphens)."""
    return _sanitize(value).lower().replace(' ', '-')


# ---------------------------------------------------------------------------
# URL checker
# ---------------------------------------------------------------------------

def _url_reachable(url: str, timeout: int = 5) -> bool:
    """HEAD-check a URL; fall back to GET if HEAD is blocked."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (compatible; GearCargo/1.0)',
    }
    try:
        resp = requests.head(url, headers=headers, timeout=timeout, allow_redirects=True)
        if resp.status_code < 400:
            return True
        # Some servers block HEAD — try GET with stream
        resp = requests.get(url, headers=headers, timeout=timeout, stream=True, allow_redirects=True)
        resp.close()
        return resp.status_code < 400
    except (requests.RequestException, Exception):
        return False


# ---------------------------------------------------------------------------
# Redis helpers
# ---------------------------------------------------------------------------

def _get_redis():
    """Safely obtain the app-level Redis client (may be None)."""
    try:
        from app import redis_client
        return redis_client
    except Exception:
        return None


def _cache_key(make: str, model: str, year: int, lang: str) -> str:
    return f"{CACHE_PREFIX}{make.lower()}:{model.lower()}:{year}:{lang}"


def _cache_get(make: str, model: str, year: int, lang: str) -> dict | None:
    r = _get_redis()
    if not r:
        return None
    try:
        raw = r.get(_cache_key(make, model, year, lang))
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return None


def _cache_set(make: str, model: str, year: int, lang: str, data: dict):
    r = _get_redis()
    if not r:
        return
    try:
        r.setex(
            _cache_key(make, model, year, lang),
            CACHE_TTL,
            json.dumps(data),
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_manual_url(make: str, model: str, year: int, lang: str) -> dict:
    """
    Resolve an owner's manual URL for the given vehicle + language.

    Parameters come directly from the vehicle's DB record and the user's
    language preference — nothing is hardcoded.

    Returns a dict with:
      - manual_url: str | None
      - source: 'oem' | 'aggregator' | None
      - fallback_search: str  (always provided as last resort)
    """
    safe_make = _sanitize(make)
    safe_model = _sanitize(model)
    safe_year = int(year) if str(year).isdigit() else 0
    lang = lang if lang in LANG_TO_TLD else 'en'

    # 1. Check Redis cache
    cached = _cache_get(safe_make, safe_model, safe_year, lang)
    if cached:
        cached['cached'] = True
        return cached

    tld = LANG_TO_TLD[lang]
    model_slug = _slug(safe_model)
    make_lower = safe_make.lower().replace(' ', '-')

    # 2. Try OEM templates
    templates = OEM_TEMPLATES.get(make_lower, [])
    for tmpl in templates:
        url = tmpl.format(tld=tld, model=model_slug, year=safe_year)
        if _url_reachable(url):
            result = {
                'manual_url': url,
                'source': 'oem',
                'fallback_search': _build_search_url(safe_make, safe_model, safe_year, lang),
                'cached': False,
            }
            _cache_set(safe_make, safe_model, safe_year, lang, result)
            return result

    # 3. Try aggregator templates
    for agg in AGGREGATOR_TEMPLATES:
        url = agg['url'].format(
            make=quote_plus(safe_make),
            model=quote_plus(safe_model),
            year=safe_year,
            lang=lang,
            lang_upper=lang.upper(),
        )
        if _url_reachable(url):
            result = {
                'manual_url': url,
                'source': 'aggregator',
                'fallback_search': _build_search_url(safe_make, safe_model, safe_year, lang),
                'cached': False,
            }
            _cache_set(safe_make, safe_model, safe_year, lang, result)
            return result

    # 4. Nothing found — return Google search fallback
    result = {
        'manual_url': None,
        'source': None,
        'fallback_search': _build_search_url(safe_make, safe_model, safe_year, lang),
        'cached': False,
    }
    # Cache the "not found" result for a shorter TTL (1 day) to retry sooner
    r = _get_redis()
    if r:
        try:
            r.setex(
                _cache_key(safe_make, safe_model, safe_year, lang),
                24 * 60 * 60,
                json.dumps(result),
            )
        except Exception:
            pass
    return result


def _build_search_url(make: str, model: str, year: int, lang: str) -> str:
    lang_name = LANG_TO_NAME.get(lang, 'english')
    query = f"{make} {model} {year} owner manual PDF {lang_name}"
    return f"https://www.google.com/search?q={quote_plus(query)}"

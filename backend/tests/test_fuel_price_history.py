"""Tests for F25 — weekly fuel-price history accrual + endpoint."""

from datetime import date, timedelta

from app import db
from app.models import FuelPriceHistory
from app.services.fuel_price_service import record_price_history

TODAY = date.today()


def _payload(last_update, diesel=1.50, petrol=1.40):
    return {
        'diesel': diesel, 'petrol': petrol, 'lpg': 0.80, 'premium': None,
        'currency_code': 'GBP', 'source': 'GOV.UK weekly road fuel prices',
        'last_update': last_update,
    }


def test_record_is_idempotent_per_country_and_date(app):
    with app.app_context():
        record_price_history('UK', _payload(TODAY.isoformat(), diesel=1.50), app)
        # Same (country, date) again — e.g. two scheduler runs in one week.
        record_price_history('UK', _payload(TODAY.isoformat(), diesel=1.55), app)

        rows = FuelPriceHistory.query.filter_by(country='UK').all()
        assert len(rows) == 1
        assert float(rows[0].diesel) == 1.55       # updated in place


def test_distinct_weeks_accrue_rows(app):
    with app.app_context():
        record_price_history('UK', _payload((TODAY - timedelta(weeks=1)).isoformat()), app)
        record_price_history('UK', _payload(TODAY.isoformat()), app)
        assert FuelPriceHistory.query.filter_by(country='UK').count() == 2


def test_missing_or_bogus_date_is_skipped(app):
    with app.app_context():
        record_price_history('UK', {'diesel': 1.5}, app)                       # no date
        record_price_history('UK', _payload('not-a-date-at-all'), app)        # unparseable
        assert FuelPriceHistory.query.count() == 0


def test_history_endpoint_orders_and_clamps(app, client, user, auth_headers):
    with app.app_context():
        for weeks_ago in (10, 2, 0):
            record_price_history(
                'RO', _payload((TODAY - timedelta(weeks=weeks_ago)).isoformat(),
                               diesel=1.0 + weeks_ago), app)

    # Auth required.
    assert client.get('/api/external/fuel-prices/history').status_code == 401

    resp = client.get('/api/external/fuel-prices/history?country=ro&weeks=12',
                      headers=auth_headers(user.id))
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['country'] == 'RO'
    dates = [p['date'] for p in body['points']]
    assert dates == sorted(dates) and len(dates) == 3
    assert body['points'][0]['diesel'] == 11.0     # oldest first

    # weeks=4 drops the 10-weeks-ago point; clamp keeps silly values sane.
    resp = client.get('/api/external/fuel-prices/history?country=RO&weeks=4',
                      headers=auth_headers(user.id))
    assert len(resp.get_json()['points']) == 2
    resp = client.get('/api/external/fuel-prices/history?country=RO&weeks=9999',
                      headers=auth_headers(user.id))
    assert resp.get_json()['weeks'] == 52


# ---------------------------------------------------------------------------
# R4-19 — `_redis_client` built a fresh `redis.from_url` client (and therefore a
# fresh connection pool) on EVERY call, and `_parse_eu_bulletin_xlsx` looked up
# the EUR exchange rates inside its per-country loop, repeating the same Redis
# read ~27 times per bulletin parse.
# ---------------------------------------------------------------------------

import os

import pytest

import app.services.fuel_price_service as fps


class _FakeRedis:
    """Minimal stand-in — records nothing, answers nothing."""

    def get(self, key):
        return None

    def setex(self, key, ttl, value):
        return True


@pytest.fixture(autouse=True)
def _reset_redis_cache():
    """The client cache is module state — never leak it between tests.

    Tolerates the helper being absent so these tests fail on their own
    assertions (30 clients built instead of 1) rather than on a missing symbol.
    """
    reset = getattr(fps, '_reset_redis_client_cache', lambda: None)
    reset()
    yield
    reset()


def test_redis_client_is_constructed_once_per_process(app, monkeypatch):
    constructions = []

    def _counting_from_url(url, **kwargs):
        constructions.append((url, kwargs))
        return _FakeRedis()

    monkeypatch.setattr(fps.redis_mod, 'from_url', _counting_from_url)

    with app.app_context():
        for _ in range(30):
            fps._redis_get('UK', app)

    assert len(constructions) == 1, f'{len(constructions)} clients built for 30 reads'
    # The module decodes responses itself — the shared app-level client does not.
    assert constructions[0][1].get('decode_responses') is True


def test_redis_client_is_rebuilt_after_a_fork(app, monkeypatch):
    """A pooled client must never be inherited across a fork (gunicorn workers)."""
    constructions = []
    monkeypatch.setattr(fps.redis_mod, 'from_url',
                        lambda url, **kwargs: constructions.append(url) or _FakeRedis())

    with app.app_context():
        fps._redis_get('UK', app)
        assert len(constructions) == 1

        # Simulate the child process seeing a different PID. The real pid is
        # captured first — reading os.getpid() inside the lambda would call the
        # patched function itself.
        child_pid = os.getpid() + 1
        monkeypatch.setattr(os, 'getpid', lambda: child_pid)
        fps._redis_get('UK', app)

    assert len(constructions) == 2


def test_redis_client_is_rebuilt_when_the_url_changes(app, monkeypatch):
    constructions = []
    monkeypatch.setattr(fps.redis_mod, 'from_url',
                        lambda url, **kwargs: constructions.append(url) or _FakeRedis())

    with app.app_context():
        fps._redis_get('UK', app)
        app.config['REDIS_URL'] = 'redis://elsewhere:6379/1'
        fps._redis_get('UK', app)

    assert constructions == [
        app.config.get('REDIS_URL') and constructions[0],
        'redis://elsewhere:6379/1',
    ]


def test_a_failing_client_construction_still_degrades_to_none(app, monkeypatch):
    def _boom(url, **kwargs):
        raise RuntimeError('no redis here')

    monkeypatch.setattr(fps.redis_mod, 'from_url', _boom)

    with app.app_context():
        assert fps._redis_get('UK', app) is None      # never raises
        fps._redis_set('UK', {'diesel': 1.5}, app)    # never raises


def test_bulletin_parse_looks_up_the_exchange_rates_once(app, monkeypatch):
    """The rate lookup was inside the per-country loop (~27 repeats per parse)."""
    lookups = []

    def _counting_rates(passed_app=None):
        lookups.append(passed_app)
        return {'GBP': 0.85, 'RON': 4.97}

    monkeypatch.setattr(fps, 'get_live_eur_rates', _counting_rates)

    with app.app_context():
        results = fps._parse_eu_bulletin_xlsx(_bulletin_xlsx_bytes(), app)

    assert results, 'the fixture spreadsheet should parse'
    assert len(results) >= 2, f'expected several countries, got {list(results)}'
    assert len(lookups) == 1, f'{len(lookups)} rate lookups for {len(results)} countries'


def _bulletin_xlsx_bytes():
    """A minimal EU Oil Bulletin workbook: header, units row, three countries."""
    import io
    import zipfile

    rows = [
        # r=1 header: B = Euro-super 95, C = Gas oil auto, G = LPG
        [('A', 'Country', True), ('B', 'Euro-super 95', True),
         ('C', 'Gas oil auto', True), ('G', 'LPG', True)],
        # r=2 units row: column A holds the Excel date serial (2026-01-05)
        [('A', '46027', False)],
        [('A', 'Germany', True), ('B', '1700', False), ('C', '1600', False),
         ('G', '900', False)],
        [('A', 'France', True), ('B', '1800', False), ('C', '1700', False),
         ('G', '950', False)],
        [('A', 'Romania', True), ('B', '1500', False), ('C', '1450', False),
         ('G', '700', False)],
    ]

    shared = []

    def _cell(ref, value, is_string, row_index):
        if not is_string:
            return f'<c r="{ref}{row_index}"><v>{value}</v></c>'
        if value not in shared:
            shared.append(value)
        return (f'<c r="{ref}{row_index}" t="s">'
                f'<v>{shared.index(value)}</v></c>')

    body = []
    for row_index, row in enumerate(rows, start=1):
        cells = ''.join(_cell(ref, value, is_string, row_index)
                        for ref, value, is_string in row)
        body.append(f'<row r="{row_index}">{cells}</row>')

    sheet = ('<?xml version="1.0"?>'
             '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
             f'<sheetData>{"".join(body)}</sheetData></worksheet>')
    shared_strings = (
        '<?xml version="1.0"?>'
        '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        f'count="{len(shared)}" uniqueCount="{len(shared)}">'
        + ''.join(f'<si><t>{value}</t></si>' for value in shared)
        + '</sst>')

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as zf:
        zf.writestr('xl/worksheets/sheet1.xml', sheet)
        zf.writestr('xl/sharedStrings.xml', shared_strings)
    return buffer.getvalue()

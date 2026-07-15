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

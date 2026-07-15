"""Tests for F20 — fuel-price force refresh + stale/baseline markers.

Before the fix, ?force_refresh=true hit a deleted `_cache` dict and raised
NameError → 500 for every press of the dashboard refresh button.
"""

from datetime import date, timedelta

import app.services.fuel_price_service as fps


SENTINEL = {
    'diesel': 1.11, 'petrol': 2.22, 'lpg': None, 'premium': None,
    'currency': '£', 'currency_code': 'GBP',
    'source': 'sentinel-source', 'last_update': date.today().isoformat(),
}


def test_force_refresh_returns_200_with_fresh_data(app, client, user, auth_headers, monkeypatch):
    monkeypatch.setattr(fps, 'get_prices', lambda *_a, **_k: dict(SENTINEL))

    resp = client.get('/api/external/fuel-prices?country=UK&force_refresh=true',
                      headers=auth_headers(user.id))
    assert resp.status_code == 200          # was 500 (NameError: _cache)
    body = resp.get_json()
    assert body['prices']['diesel'] == 1.11
    assert body['source'] == 'sentinel-source'
    # Machine-readable freshness markers are always present as booleans.
    assert body['stale'] is False
    assert body['baseline'] is False


def test_baseline_fallback_is_tagged(app, monkeypatch):
    """Redis empty + upstream down → baseline data, tagged baseline+stale."""
    monkeypatch.setattr(fps, '_redis_get', lambda *_a, **_k: None)
    monkeypatch.setattr(fps, '_fetch_uk_prices',
                        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError('down')))

    with app.app_context():
        result = fps.get_prices('UK', app)

    assert result['baseline'] is True
    # BASELINE_PRICES carries a hardcoded past last_update → stale.
    assert result['stale'] is True
    assert result.get('diesel') is not None


def test_fresh_fetch_is_not_stale(app, monkeypatch):
    fresh = dict(SENTINEL)
    monkeypatch.setattr(fps, '_redis_get', lambda *_a, **_k: None)
    monkeypatch.setattr(fps, '_redis_set', lambda *_a, **_k: None)
    monkeypatch.setattr(fps, '_fetch_uk_prices', lambda *_a, **_k: fresh)

    with app.app_context():
        result = fps.get_prices('UK', app)

    assert result['baseline'] is False
    assert result['stale'] is False


def test_old_last_update_is_stale(app, monkeypatch):
    old = dict(SENTINEL, last_update=(date.today() - timedelta(days=30)).isoformat())
    monkeypatch.setattr(fps, '_redis_get', lambda *_a, **_k: None)
    monkeypatch.setattr(fps, '_redis_set', lambda *_a, **_k: None)
    monkeypatch.setattr(fps, '_fetch_uk_prices', lambda *_a, **_k: old)

    with app.app_context():
        result = fps.get_prices('UK', app)

    assert result['stale'] is True
    assert result['baseline'] is False

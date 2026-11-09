"""GC-103: the dashboard's location lookups and the origins the browser may contact.

The browser never calls a geocoder. One server-side Nominatim lookup names both
the country and the place, ``country_detected`` says whether it really did, and
the CSP ``connect-src`` lists only origins the browser itself uses.
"""

from collections import OrderedDict

import pytest
import requests

import app.routes.external as external
import app.services.fuel_price_service as fuel_price_service
from app import db

FUEL_PRICES_URL = '/api/external/fuel-prices'
WESTMINSTER_ADDRESS = {
    'suburb': 'Westminster', 'city': 'London',
    'country': 'United Kingdom', 'country_code': 'gb',
}
# The dashboard's first request from a Romanian-language account without a country_preference:
# the fallback country, its name in the app language, and the device position.
DASHBOARD_QUERY = '?country=UK&location=Regatul+Unit&lat=44.43&lon=26.1'
PRICES = {
    'diesel': 1.50, 'petrol': 1.60, 'lpg': None, 'premium': None,
    'currency': '£', 'currency_code': 'GBP',
    'source': 'test-source', 'last_update': '2026-11-02',
}
REMOVED_ORIGINS = (
    'https://vpic.nhtsa.dot.gov',
    'https://nominatim.openstreetmap.org',
    'https://api.pwnedpasswords.com',
)
BROWSER_ORIGINS = ("'self'", 'https://fonts.googleapis.com', 'https://fonts.gstatic.com')


class FakeResponse:
    def __init__(self, payload, status_code=requests.codes.ok):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload


class Geocoder:
    """Stands in for requests.get and records every Nominatim request."""

    def __init__(self):
        self.calls = []
        self.reply = FakeResponse({'address': WESTMINSTER_ADDRESS})

    def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


class HeldThrottle:
    """A Redis whose Nominatim slot another worker already holds."""

    def set(self, *args, **kwargs):
        return False

    def get(self, key):
        return None

    def setex(self, *args, **kwargs):
        return None


@pytest.fixture()
def geocoder(monkeypatch):
    monkeypatch.setattr('app.redis_client', None)
    monkeypatch.setattr(external, '_fallback_cache', OrderedDict())
    monkeypatch.setattr(fuel_price_service, 'get_prices', lambda *args, **kwargs: dict(PRICES))
    fake = Geocoder()
    monkeypatch.setattr(requests, 'get', fake)
    return fake


def fuel_prices(client, user, auth_headers, query):
    response = client.get(FUEL_PRICES_URL + query, headers=auth_headers(user.id))
    assert response.status_code == 200
    return response.get_json()


def test_coordinates_give_country_and_place_from_one_lookup(client, user, auth_headers, geocoder):
    user.language = 'ro'
    db.session.commit()

    body = fuel_prices(client, user, auth_headers, '?country=UK&location=Regatul+Unit&lat=51.5074&lon=-0.1278')

    assert (body['country'], body['location'], body['country_detected']) == ('GB', 'Westminster, United Kingdom', True)
    assert len(geocoder.calls) == 1
    url, request_options = geocoder.calls[0]
    assert url == external._NOMINATIM_REVERSE_URL
    assert request_options['params'] == {'lat': 51.5074, 'lon': -0.1278, 'format': 'json', 'accept-language': 'ro'}
    assert request_options['headers']['User-Agent'] == external._NOMINATIM_USER_AGENT


@pytest.mark.parametrize('address, expected', [
    (WESTMINSTER_ADDRESS, 'Westminster, United Kingdom'),
    ({'town': 'Exampleton', 'county': 'Exampleshire', 'country': 'United Kingdom'}, 'Exampleton, United Kingdom'),
    ({'state': 'Bavaria', 'country': 'Germany'}, 'Bavaria, Germany'),
    ({'country': 'Romania'}, 'Romania'),
    ({}, None),
])
def test_place_name_uses_the_most_specific_field(address, expected):
    assert external._place_name(address) == expected


def test_throttled_lookup_keeps_the_client_country_and_label(client, user, auth_headers, geocoder, monkeypatch):
    monkeypatch.setattr('app.redis_client', HeldThrottle())

    body = fuel_prices(client, user, auth_headers, DASHBOARD_QUERY)

    assert (body['country'], body['location'], body['country_detected']) == ('UK', 'Regatul Unit', False)
    assert geocoder.calls == []


@pytest.mark.parametrize('reply', [
    FakeResponse({}, status_code=requests.codes.service_unavailable),
    FakeResponse({'error': 'Unable to geocode'}),
    requests.ConnectionError('Max retries exceeded with url: /reverse?lat=44.43&lon=26.1&format=json'),
], ids=['http-error', 'no-address', 'connection-error'])
def test_failed_lookup_keeps_the_client_values_without_logging_coordinates(
        app, client, user, auth_headers, geocoder, monkeypatch, reply):
    geocoder.reply = reply
    warnings = []
    monkeypatch.setattr(app.logger, 'warning', lambda message, *args, **kwargs: warnings.append(message))

    body = fuel_prices(client, user, auth_headers, DASHBOARD_QUERY)

    assert (body['country'], body['location'], body['country_detected']) == ('UK', 'Regatul Unit', False)
    assert not [message for message in warnings if '44.43' in str(message)]


@pytest.mark.parametrize('query, expected', [
    ('?country=RO&location=Cluj', ('RO', 'Cluj')),
    ('?country=RO', ('RO', 'Romania')),
    ('?country=UK', ('UK', 'United Kingdom')),
])
def test_no_coordinates_means_no_geocoder_request(client, user, auth_headers, geocoder, query, expected):
    body = fuel_prices(client, user, auth_headers, query)

    assert (body['country'], body['location']) == expected
    assert body['country_detected'] is False
    assert geocoder.calls == []


def test_connect_src_lists_only_origins_the_browser_uses(client):
    policy = client.get('/api/csrf-token').headers['Content-Security-Policy']
    connect_src = next(directive for directive in policy.split('; ') if directive.startswith('connect-src '))
    origins = connect_src.split()[1:]

    assert all(origin in origins for origin in BROWSER_ORIGINS)
    assert not [origin for origin in REMOVED_ORIGINS if origin in origins]

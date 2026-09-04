"""Regression tests for R4-12 — preference writes on /auth/me and register.

`PUT /auth/me` applied `language` (String(10)), `timezone` (String(50)),
`currency` (String(5)) and the rest of the preference list verbatim, so an
over-long value was a `DataError` 500. `alert_days_before` went through the
notification loop with no coercion at all, and `services/due.py:91` later feeds
it to `timedelta(days=max(0, days))` — so a string stored here broke `/due`,
the dashboard widget and the e-mail digest long after the request that caused
it. Register had the same gap on `language` / `timezone`.

The identity fields were already guarded by R2; these tests cover the
preference half and assert the same "validate everything before writing
anything" rule.
"""

import pytest

from app import db
from app.models import User


def _register(client, **overrides):
    payload = {
        'email': 'newuser@example.com',
        'password': 'StrongPass123!',
        'username': 'newuser',
    }
    payload.update(overrides)
    return client.post('/api/auth/register', json=payload)


@pytest.mark.parametrize('field, bad_value', [
    ('language', 'en-GB-oxendict-x-toolong'),   # String(10)
    ('timezone', 'Europe/' + 'x' * 60),         # String(50)
    ('theme', 'ultra-dark-mode'),               # String(10)
    ('currency', 'EUROSS'),                     # String(5)
    ('distance_unit', 'kilometres!'),           # String(10)
    ('volume_unit', 'hectolitres'),             # String(10)
    ('date_format', 'DD/MM/YYYY HH:MM:SS.mmm'),  # String(20)
    ('country_preference', 'ROU1'),             # String(3)
])
def test_update_profile_rejects_over_long_preferences(app, client, user, auth_headers,
                                                      field, bad_value):
    response = client.put('/api/auth/me', headers=auth_headers(user.id),
                          json={field: bad_value})

    assert response.status_code == 400, response.get_json()   # was: DataError 500
    payload = response.get_json()
    assert payload['message_key'] == 'validation.maxLength'
    assert payload['field'] == field


def test_update_profile_does_not_half_apply_a_rejected_request(app, client, user, auth_headers):
    response = client.put('/api/auth/me', headers=auth_headers(user.id),
                          json={'theme': 'light', 'currency': 'EUROSS'})

    assert response.status_code == 400, response.get_json()
    with app.app_context():
        # The valid field in the same request must not survive the rejection.
        assert db.session.get(User, user.id).theme != 'light'


def test_update_profile_still_stores_valid_preferences(app, client, user, auth_headers):
    response = client.put('/api/auth/me', headers=auth_headers(user.id),
                          json={'language': 'ro', 'currency': 'RON', 'theme': 'light',
                                'timezone': 'Europe/Bucharest', 'distance_unit': 'km',
                                'date_format': 'DD/MM/YYYY', 'country_preference': 'RO'})

    assert response.status_code == 200, response.get_json()
    with app.app_context():
        stored = db.session.get(User, user.id)
        assert stored.language == 'ro'
        assert stored.currency == 'RON'
        assert stored.theme == 'light'
        assert stored.timezone == 'Europe/Bucharest'
        assert stored.country_preference == 'RO'


# --- alert_days_before: the value /due, the widget and the digest consume ----

@pytest.mark.parametrize('bad_value', ['abc', {}, [1]])
def test_update_profile_rejects_a_non_numeric_alert_window(app, client, user, auth_headers,
                                                           bad_value):
    response = client.put('/api/auth/me', headers=auth_headers(user.id),
                          json={'alert_days_before': bad_value})

    assert response.status_code == 400, response.get_json()
    assert response.get_json()['message_key'] == 'validation.invalidNumber'


def test_a_rejected_alert_window_leaves_due_working(app, client, user, auth_headers):
    """The 500 this prevents surfaced in /due, not in the request that caused it."""
    rejected = client.put('/api/auth/me', headers=auth_headers(user.id),
                          json={'alert_days_before': 'abc'})
    assert rejected.status_code == 400

    due = client.get('/api/due', headers=auth_headers(user.id))

    assert due.status_code == 200, due.get_json()             # was: TypeError 500


@pytest.mark.parametrize('sent, stored', [
    ('21', 21),        # the string a number input submits
    (0, 1),            # clamped up — 0 would mean "no horizon at all"
    (-5, 1),
    (99999, 365),      # clamped down
])
def test_update_profile_clamps_the_alert_window(app, client, user, auth_headers, sent, stored):
    response = client.put('/api/auth/me', headers=auth_headers(user.id),
                          json={'alert_days_before': sent})

    assert response.status_code == 200, response.get_json()
    with app.app_context():
        assert db.session.get(User, user.id).alert_days_before == stored


# --- location coordinates ---------------------------------------------------

def test_update_profile_stores_coordinates_with_a_decimal_comma(app, client, user, auth_headers):
    response = client.put('/api/auth/me', headers=auth_headers(user.id),
                          json={'location_lat': '44,4268', 'location_lon': '26,1025'})

    assert response.status_code == 200, response.get_json()
    with app.app_context():
        stored = db.session.get(User, user.id)
        assert round(stored.location_lat, 4) == 44.4268
        assert round(stored.location_lon, 4) == 26.1025


@pytest.mark.parametrize('field, bad_value', [
    ('location_lat', 'abc'),
    ('location_lat', 91),          # out of range
    ('location_lon', -181),
])
def test_update_profile_rejects_impossible_coordinates(app, client, user, auth_headers,
                                                       field, bad_value):
    response = client.put('/api/auth/me', headers=auth_headers(user.id),
                          json={field: bad_value})

    assert response.status_code == 400, response.get_json()   # was: silently discarded
    with app.app_context():
        assert getattr(db.session.get(User, user.id), field) is None


def test_update_profile_clears_a_coordinate_with_an_empty_string(app, client, user, auth_headers):
    client.put('/api/auth/me', headers=auth_headers(user.id),
               json={'location_lat': 44.4268})

    response = client.put('/api/auth/me', headers=auth_headers(user.id),
                          json={'location_lat': ''})

    assert response.status_code == 200, response.get_json()
    with app.app_context():
        assert db.session.get(User, user.id).location_lat is None


# --- register ---------------------------------------------------------------

@pytest.mark.parametrize('field, bad_value', [
    ('language', 'en-GB-oxendict-x-toolong'),
    ('timezone', 'Europe/' + 'x' * 60),
])
def test_register_rejects_over_long_preferences(app, client, field, bad_value):
    response = _register(client, **{field: bad_value})

    assert response.status_code == 400, response.get_json()   # was: DataError 500
    assert response.get_json()['message_key'] == 'validation.maxLength'
    with app.app_context():
        assert User.query.filter_by(email='newuser@example.com').first() is None


def test_register_still_accepts_valid_preferences(app, client):
    response = _register(client, language='ro', timezone='Europe/Bucharest')

    assert response.status_code == 201, response.get_json()
    with app.app_context():
        created = User.query.filter_by(email='newuser@example.com').first()
        assert created.language == 'ro'
        assert created.timezone == 'Europe/Bucharest'

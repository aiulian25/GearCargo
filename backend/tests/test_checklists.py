"""Tests for F54 — user-configurable seasonal checklists.

Covers: state-inspection month settings round-trip + is_in_season honoring,
custom items (add → appears with custom flag, toggle persists, remove),
and validation (bad month 400, label caps, cross-user isolation).
"""

from datetime import datetime

from app import db
from app.models import User


def _mk_user(email, username):
    u = User(email=email, username=username, is_active=True)
    u.set_password('Str0ng!Passw0rd')
    db.session.add(u)
    db.session.commit()
    return u


def _state_inspection(body):
    return next(c for c in body['checklists'] if c['id'] == 'state_inspection')


# --- Settings (inspection months) -------------------------------------------

def test_inspection_months_roundtrip_and_in_season(app, client, user, auth_headers):
    current_month = datetime.now().month

    # Default: no months set → year-round (not seasonal, always in season).
    body = client.get('/api/predictions/checklists', headers=auth_headers(user.id)).get_json()
    si = _state_inspection(body)
    assert si['is_seasonal'] is False
    assert si['is_in_season'] is True

    # Restrict to a month that is NOT the current one → hidden (out of season).
    other_month = 12 if current_month != 12 else 6
    resp = client.put('/api/predictions/checklists/settings',
                      headers=auth_headers(user.id),
                      json={'state_inspection_months': [other_month]})
    assert resp.status_code == 200
    assert resp.get_json()['settings']['state_inspection_months'] == [other_month]

    body = client.get('/api/predictions/checklists', headers=auth_headers(user.id)).get_json()
    si = _state_inspection(body)
    assert si['is_seasonal'] is True
    assert si['season_months'] == [other_month]
    assert si['is_in_season'] is False  # acceptance: hidden outside chosen months

    # Include the current month → in season again.
    client.put('/api/predictions/checklists/settings', headers=auth_headers(user.id),
               json={'state_inspection_months': [current_month]})
    si = _state_inspection(
        client.get('/api/predictions/checklists', headers=auth_headers(user.id)).get_json())
    assert si['is_in_season'] is True

    # Empty list clears the restriction → back to year-round.
    client.put('/api/predictions/checklists/settings', headers=auth_headers(user.id),
               json={'state_inspection_months': []})
    si = _state_inspection(
        client.get('/api/predictions/checklists', headers=auth_headers(user.id)).get_json())
    assert si['is_seasonal'] is False


def test_invalid_month_rejected(app, client, user, auth_headers):
    for bad in ([0], [13], ['x'], [3, 99]):
        resp = client.put('/api/predictions/checklists/settings',
                          headers=auth_headers(user.id),
                          json={'state_inspection_months': bad})
        assert resp.status_code == 400, bad


def test_months_deduped_and_sorted(app, client, user, auth_headers):
    resp = client.put('/api/predictions/checklists/settings',
                      headers=auth_headers(user.id),
                      json={'state_inspection_months': [5, 3, 5, 1]})
    assert resp.get_json()['settings']['state_inspection_months'] == [1, 3, 5]


# --- Custom items -----------------------------------------------------------

def test_add_custom_item_appears_with_flag(app, client, user, auth_headers):
    resp = client.post('/api/predictions/checklists/winter/custom-items',
                       headers=auth_headers(user.id), json={'label': 'Check tow-bar wiring'})
    assert resp.status_code == 200
    new_id = resp.get_json()['item']['id']
    assert new_id.startswith('custom_')

    body = client.get('/api/predictions/checklists', headers=auth_headers(user.id)).get_json()
    winter = next(c for c in body['checklists'] if c['id'] == 'winter')
    custom = next(i for i in winter['items'] if i['id'] == new_id)
    assert custom['custom'] is True
    assert custom['label'] == 'Check tow-bar wiring'
    assert custom['completed'] is False
    # Built-ins still present; total grew by one.
    assert winter['total_count'] == 9


def test_toggle_custom_item_persists(app, client, user, auth_headers):
    new_id = client.post('/api/predictions/checklists/winter/custom-items',
                         headers=auth_headers(user.id),
                         json={'label': 'Tow-bar'}).get_json()['item']['id']

    resp = client.post(f'/api/predictions/checklists/winter/items/{new_id}',
                       headers=auth_headers(user.id))
    assert resp.status_code == 200
    assert resp.get_json()['completed'] is True

    body = client.get('/api/predictions/checklists', headers=auth_headers(user.id)).get_json()
    winter = next(c for c in body['checklists'] if c['id'] == 'winter')
    assert next(i for i in winter['items'] if i['id'] == new_id)['completed'] is True


def test_remove_custom_item_clears_completion(app, client, user, auth_headers):
    new_id = client.post('/api/predictions/checklists/winter/custom-items',
                         headers=auth_headers(user.id),
                         json={'label': 'Temp'}).get_json()['item']['id']
    client.post(f'/api/predictions/checklists/winter/items/{new_id}', headers=auth_headers(user.id))

    resp = client.delete('/api/predictions/checklists/winter/custom-items',
                        headers=auth_headers(user.id), json={'id': new_id})
    assert resp.status_code == 200

    body = client.get('/api/predictions/checklists', headers=auth_headers(user.id)).get_json()
    winter = next(c for c in body['checklists'] if c['id'] == 'winter')
    assert all(i['id'] != new_id for i in winter['items'])
    assert winter['total_count'] == 8  # back to the built-in count


def test_custom_item_label_validation(app, client, user, auth_headers):
    # Empty label rejected.
    assert client.post('/api/predictions/checklists/winter/custom-items',
                       headers=auth_headers(user.id), json={'label': '   '}).status_code == 400
    # Over 80 chars rejected.
    assert client.post('/api/predictions/checklists/winter/custom-items',
                       headers=auth_headers(user.id), json={'label': 'x' * 81}).status_code == 400


def test_custom_item_cap_enforced(app, client, user, auth_headers):
    for i in range(20):
        r = client.post('/api/predictions/checklists/summer/custom-items',
                        headers=auth_headers(user.id), json={'label': f'Item {i}'})
        assert r.status_code == 200
    over = client.post('/api/predictions/checklists/summer/custom-items',
                       headers=auth_headers(user.id), json={'label': 'One too many'})
    assert over.status_code == 400


def test_custom_item_isolated_per_user(app, client, user, auth_headers):
    with app.app_context():
        other = _mk_user('clother@example.com', 'clother')
        other_id = other.id
    client.post('/api/predictions/checklists/winter/custom-items',
                headers=auth_headers(other_id), json={'label': 'Their item'})

    body = client.get('/api/predictions/checklists', headers=auth_headers(user.id)).get_json()
    winter = next(c for c in body['checklists'] if c['id'] == 'winter')
    assert all(not i.get('custom') for i in winter['items'])


def test_invalid_checklist_and_item_rejected(app, client, user, auth_headers):
    assert client.post('/api/predictions/checklists/nope/custom-items',
                       headers=auth_headers(user.id), json={'label': 'x'}).status_code == 400
    # A custom id from nowhere cannot be toggled.
    assert client.post('/api/predictions/checklists/winter/items/custom_deadbeef',
                       headers=auth_headers(user.id)).status_code == 400

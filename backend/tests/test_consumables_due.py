"""Tests for F3 — consumable "due for replacement" endpoint + push job."""

from datetime import date

import pytest

from app import db
from app.models import User, Vehicle, ConsumableEntry


def _mk_vehicle(user_id, name='Focus', mileage=0):
    v = Vehicle(user_id=user_id, name=name, make='Ford', model='Focus',
                current_mileage=mileage)
    db.session.add(v)
    db.session.commit()
    db.session.refresh(v)
    return v


def _mk_consumable(user_id, vehicle_id, ctype='tire', install_odo=0,
                   expected_km=1000):
    """A purely mileage-based consumable (no month lifespan → time wear is None)."""
    c = ConsumableEntry(
        user_id=user_id, vehicle_id=vehicle_id, date=date.today(),
        consumable_type=ctype, install_odometer=install_odo, odometer=install_odo,
        expected_lifespan_km=expected_km, amount=200,
    )
    db.session.add(c)
    db.session.commit()
    db.session.refresh(c)
    return c


def test_requires_auth(client):
    assert client.get('/api/consumables/due').status_code == 401


def test_due_lists_monitor_and_replace_with_vehicle_name(app, client, user, auth_headers):
    with app.app_context():
        # 80% worn → 'monitor'; 100% → 'replace'; 0% → excluded.
        v_monitor = _mk_vehicle(user.id, 'Golf', mileage=800)
        v_replace = _mk_vehicle(user.id, 'Passat', mileage=1000)
        v_fresh = _mk_vehicle(user.id, 'Polo', mileage=0)
        _mk_consumable(user.id, v_monitor.id, ctype='tire', expected_km=1000)
        _mk_consumable(user.id, v_replace.id, ctype='battery', expected_km=1000)
        _mk_consumable(user.id, v_fresh.id, ctype='wipers', expected_km=1000)

    resp = client.get('/api/consumables/due', headers=auth_headers(user.id))
    assert resp.status_code == 200
    items = resp.get_json()['items']

    # Only the monitor + replace items appear (fresh 0%-wear one excluded).
    assert len(items) == 2
    # Sorted most-worn first → replace (100%) before monitor (80%).
    assert items[0]['wear']['status'] == 'replace'
    assert items[0]['vehicle_name'] == 'Passat'
    assert items[1]['wear']['status'] == 'monitor'
    assert items[1]['vehicle_name'] == 'Golf'
    assert items[1]['wear']['wear_percent'] == 80.0


def test_due_excludes_fresh_and_unknown(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id, 'Focus', mileage=100)
        # Fresh (10% worn) → good → excluded.
        _mk_consumable(user.id, v.id, ctype='tire', expected_km=1000)
        # No expected lifespan at all → 'unknown' → excluded.
        c = ConsumableEntry(user_id=user.id, vehicle_id=v.id, date=date.today(),
                            consumable_type='other', amount=10)
        db.session.add(c)
        db.session.commit()

    items = client.get('/api/consumables/due', headers=auth_headers(user.id)).get_json()['items']
    assert items == []


def test_due_scoped_to_owner(app, client, user, auth_headers):
    with app.app_context():
        other = User(email='other@example.com', username='other', is_active=True)
        other.set_password('Str0ng!Passw0rd')
        db.session.add(other)
        db.session.commit()
        v_other = _mk_vehicle(other.id, 'Other Car', mileage=2000)
        _mk_consumable(other.id, v_other.id, expected_km=1000)  # 200% worn

    # The requesting user has no consumables → sees nothing from the other user.
    items = client.get('/api/consumables/due', headers=auth_headers(user.id)).get_json()['items']
    assert items == []


def test_check_consumables_due_pushes_once_on_replace(app, monkeypatch):
    """The daily job pushes exactly once when an item is 'replace', then never again."""
    from app.services import check_consumables_due
    import app.routes.push as push_mod

    calls = []
    monkeypatch.setattr(push_mod, 'send_push_to_user',
                        lambda *a, **k: calls.append((a, k)) or 1)

    with app.app_context():
        u = User(email='p@example.com', username='pusher', is_active=True)
        u.set_password('Str0ng!Passw0rd')
        db.session.add(u)
        db.session.commit()
        v = _mk_vehicle(u.id, 'Focus', mileage=1200)     # past 100% of 1000
        c = _mk_consumable(u.id, v.id, ctype='brake_pads', expected_km=1000)
        cid = c.id

    check_consumables_due(app)
    assert len(calls) == 1                       # pushed once
    with app.app_context():
        assert db.session.get(ConsumableEntry, cid).replace_notified is True

    check_consumables_due(app)
    assert len(calls) == 1                       # not pushed again (sentinel set)


def test_check_consumables_due_no_push_when_only_monitor(app, monkeypatch):
    from app.services import check_consumables_due
    import app.routes.push as push_mod
    calls = []
    monkeypatch.setattr(push_mod, 'send_push_to_user',
                        lambda *a, **k: calls.append(1) or 1)

    with app.app_context():
        u = User(email='m@example.com', username='monitor', is_active=True)
        u.set_password('Str0ng!Passw0rd')
        db.session.add(u)
        db.session.commit()
        v = _mk_vehicle(u.id, 'Focus', mileage=800)      # 80% → monitor only
        _mk_consumable(u.id, v.id, expected_km=1000)

    check_consumables_due(app)
    assert calls == []                           # monitor does not push


# --- F43: a replaced consumable supersedes the old worn one -------------------

from datetime import timedelta  # noqa: E402


def _mk_dated_consumable(user_id, vehicle_id, ctype, install_odo, expected_km,
                         install_date, amount=200):
    c = ConsumableEntry(
        user_id=user_id, vehicle_id=vehicle_id, date=install_date,
        install_date=install_date, consumable_type=ctype,
        install_odometer=install_odo, odometer=install_odo,
        expected_lifespan_km=expected_km, amount=amount)
    db.session.add(c)
    db.session.commit()
    db.session.refresh(c)
    return c


def test_replaced_consumable_superseded_in_feed(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id, mileage=60000)
        # Old tyres: fitted 400 days ago at 50k, long past their 1k-km wear.
        _mk_dated_consumable(user.id, v.id, 'tire', 50000, 1000,
                             date.today() - timedelta(days=400))
        # New tyres: fitted today at 60k, fresh (40k-km lifespan).
        _mk_dated_consumable(user.id, v.id, 'tire', 60000, 40000, date.today())
        # A DIFFERENT worn type (battery) still surfaces — supersede is per-type.
        _mk_dated_consumable(user.id, v.id, 'battery', 50000, 1000,
                             date.today() - timedelta(days=300))
        db.session.commit()

    items = client.get('/api/due?days=30', headers=auth_headers(user.id)).get_json()['items']
    cons = [it for it in items if it['kind'] == 'consumable']
    titles = {it['title'] for it in cons}
    assert 'tire' not in titles          # old tyres retired by the fresh set
    assert 'battery' in titles           # unreplaced type still nags


def test_check_consumables_due_skips_superseded(app, monkeypatch):
    """The push job must not fire for an old consumable that was replaced."""
    from app.services import check_consumables_due
    import app.routes.push as push_mod

    calls = []
    monkeypatch.setattr(push_mod, 'send_push_to_user',
                        lambda *a, **k: calls.append(1) or 1)

    with app.app_context():
        u = User(email='sup@example.com', username='superseded', is_active=True)
        u.set_password('Str0ng!Passw0rd')
        db.session.add(u)
        db.session.commit()
        v = _mk_vehicle(u.id, 'Focus', mileage=60000)
        # Old worn brake pads (would push) + a fresh replacement of the same type.
        _mk_dated_consumable(u.id, v.id, 'brake_pads', 50000, 1000,
                             date.today() - timedelta(days=400))
        _mk_dated_consumable(u.id, v.id, 'brake_pads', 60000, 40000, date.today())

    check_consumables_due(app)
    assert calls == []                   # the superseded old pads never push


# ---------------------------------------------------------------------------
# R4-10 / R4-11 — write-path validation. `amount` and `currency` reached the
# Numeric / String(3) columns raw, the local `_parse_date` was an unguarded
# `fromisoformat`, and the local `_to_int` silently discarded anything it could
# not parse. Malformed input was a 500; a mistyped lifespan vanished.
# ---------------------------------------------------------------------------

def _valid_consumable_payload(vehicle_id, **overrides):
    payload = {
        'vehicle_id': vehicle_id,
        'consumable_type': 'tire',
        'date': '2026-03-01',
        'amount': 420.50,
        'brand': 'Michelin',
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize('field, bad_value, expected_key', [
    ('amount', 'abc', 'validation.invalidNumber'),
    # A European decimal comma is a realistic mistake, and truthy — unlike a
    # falsy value, which the `or 0` fallback still treats as "not provided".
    ('amount', '1,50', 'validation.invalidNumber'),
    ('date', 'bad', 'validation.invalidDate'),
    ('date', '2026-13-40', 'validation.invalidDate'),
    ('install_date', 'bad', 'validation.invalidDate'),
    ('odometer', 'abc', 'validation.invalidNumber'),
    ('install_odometer', 'abc', 'validation.invalidNumber'),
    ('quantity', 'abc', 'validation.invalidNumber'),
    ('expected_lifespan_km', 'abc', 'validation.invalidNumber'),
    ('expected_lifespan_months', 'abc', 'validation.invalidNumber'),
    ('warranty_months', 'abc', 'validation.invalidNumber'),
    ('currency', 'EURO', 'validation.invalidCurrency'),
])
def test_create_consumable_rejects_malformed_input(
        app, client, user, auth_headers, field, bad_value, expected_key):
    with app.app_context():
        vehicle_id = _mk_vehicle(user.id).id

    response = client.post('/api/consumables', headers=auth_headers(user.id),
                           json=_valid_consumable_payload(vehicle_id, **{field: bad_value}))

    assert response.status_code == 400, response.get_json()   # was: 500
    assert response.get_json()['message_key'] == expected_key
    with app.app_context():
        assert ConsumableEntry.query.count() == 0


def test_create_consumable_coerces_the_numeric_strings_a_form_submits(app, client, user, auth_headers):
    with app.app_context():
        vehicle_id = _mk_vehicle(user.id).id

    response = client.post('/api/consumables', headers=auth_headers(user.id),
                           json=_valid_consumable_payload(
                               vehicle_id, amount='420.50', odometer='45000',
                               quantity='4', expected_lifespan_km='60000',
                               warranty_months='24', currency='eur',
                               date='2026-03-01T09:30:00Z'))

    assert response.status_code == 201, response.get_json()
    with app.app_context():
        entry = ConsumableEntry.query.one()
        assert float(entry.amount) == 420.50
        assert entry.odometer == 45000
        assert entry.install_odometer == 45000     # defaults to the entry odometer
        assert entry.quantity == 4
        assert entry.expected_lifespan_km == 60000
        assert entry.warranty_months == 24
        assert entry.currency == 'EUR'             # upper-cased
        assert entry.date == date(2026, 3, 1)      # 'Z' suffix accepted
        assert entry.install_date == date(2026, 3, 1)


def _existing_consumable(app, user_id, vehicle_id):
    with app.app_context():
        entry = ConsumableEntry(
            user_id=user_id, vehicle_id=vehicle_id, date=date(2026, 3, 1),
            amount=420.50, currency='GBP', title='Original', consumable_type='tire',
            brand='Michelin', quantity=4, odometer=45000, install_odometer=45000,
            install_date=date(2026, 3, 1), expected_lifespan_km=60000,
            warranty_months=24,
        )
        db.session.add(entry)
        db.session.commit()
        return entry.id


@pytest.mark.parametrize('field, bad_value, expected_key', [
    ('amount', 'abc', 'validation.invalidNumber'),
    ('date', 'bad', 'validation.invalidDate'),
    ('install_date', 'bad', 'validation.invalidDate'),
    ('odometer', 'abc', 'validation.invalidNumber'),
    ('quantity', 'abc', 'validation.invalidNumber'),
    ('expected_lifespan_km', 'abc', 'validation.invalidNumber'),
    ('currency', 'EURO', 'validation.invalidCurrency'),
])
def test_update_consumable_rejects_malformed_input_without_partial_writes(
        app, client, user, auth_headers, field, bad_value, expected_key):
    with app.app_context():
        vehicle_id = _mk_vehicle(user.id).id
    entry_id = _existing_consumable(app, user.id, vehicle_id)

    response = client.put(f'/api/consumables/{entry_id}', headers=auth_headers(user.id),
                          json={'title': 'Renamed', field: bad_value})

    assert response.status_code == 400, response.get_json()   # was: 500
    assert response.get_json()['message_key'] == expected_key
    with app.app_context():
        entry = db.session.get(ConsumableEntry, entry_id)
        assert entry.title == 'Original'                      # the valid edit too
        assert float(entry.amount) == 420.50
        assert entry.date == date(2026, 3, 1)
        assert entry.odometer == 45000
        assert entry.quantity == 4
        assert entry.expected_lifespan_km == 60000
        assert entry.currency == 'GBP'


def test_update_consumable_stores_numeric_strings(app, client, user, auth_headers):
    with app.app_context():
        vehicle_id = _mk_vehicle(user.id).id
    entry_id = _existing_consumable(app, user.id, vehicle_id)

    response = client.put(f'/api/consumables/{entry_id}', headers=auth_headers(user.id),
                          json={'amount': '99.99', 'odometer': '50000',
                                'quantity': '2', 'date': '2026-04-02'})

    assert response.status_code == 200, response.get_json()
    with app.app_context():
        entry = db.session.get(ConsumableEntry, entry_id)
        assert float(entry.amount) == 99.99
        assert entry.odometer == 50000
        assert entry.quantity == 2
        assert entry.date == date(2026, 4, 2)


def test_update_consumable_clears_the_install_date(app, client, user, auth_headers):
    with app.app_context():
        vehicle_id = _mk_vehicle(user.id).id
    entry_id = _existing_consumable(app, user.id, vehicle_id)

    response = client.put(f'/api/consumables/{entry_id}', headers=auth_headers(user.id),
                          json={'install_date': ''})

    assert response.status_code == 200, response.get_json()
    with app.app_context():
        assert db.session.get(ConsumableEntry, entry_id).install_date is None

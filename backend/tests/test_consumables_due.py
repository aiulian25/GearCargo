"""Tests for F3 — consumable "due for replacement" endpoint + push job."""

from datetime import date

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

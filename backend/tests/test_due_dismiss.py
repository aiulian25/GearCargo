"""Tests for F40 — dismissing items from the "Coming up" feed."""

from datetime import date, timedelta

from app import db
from app.models import User, Vehicle, Reminder, TaxEntry, DueDismissal

TODAY = date.today()


def _mk_vehicle(user_id, name='Golf'):
    v = Vehicle(user_id=user_id, name=name, make='VW', model='Golf')
    db.session.add(v)
    db.session.commit()
    db.session.refresh(v)
    return v


def _mk_due_tax(user_id, vehicle_id, next_due):
    tx = TaxEntry(
        user_id=user_id, vehicle_id=vehicle_id, date=TODAY, amount=15,
        tax_type='road_tax', title='Road Tax', status='paid',
        recurring=True, recurrence_type='monthly', next_due_date=next_due,
    )
    db.session.add(tx)
    db.session.commit()
    db.session.refresh(tx)
    return tx


def _due_items(client, user, auth_headers):
    return client.get('/api/due', headers=auth_headers(user.id)).get_json()['items']


def test_requires_auth(client):
    assert client.post('/api/due/dismiss', json={'kind': 'tax', 'ref_id': 1}).status_code == 401


def test_dismiss_hides_item_and_undismiss_restores(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        tx = _mk_due_tax(user.id, v.id, next_due=TODAY + timedelta(days=5))
        tx_id = tx.id

    assert any(it['kind'] == 'tax' for it in _due_items(client, user, auth_headers))

    resp = client.post('/api/due/dismiss', json={'kind': 'tax', 'ref_id': tx_id},
                       headers=auth_headers(user.id))
    assert resp.status_code == 200
    assert not any(it['kind'] == 'tax' for it in _due_items(client, user, auth_headers))

    resp = client.post('/api/due/undismiss', json={'kind': 'tax', 'ref_id': tx_id},
                       headers=auth_headers(user.id))
    assert resp.status_code == 200
    assert any(it['kind'] == 'tax' for it in _due_items(client, user, auth_headers))


def test_dismissal_is_occurrence_scoped(app, client, user, auth_headers):
    """A NEW occurrence (advanced due date) resurfaces after a dismissal."""
    with app.app_context():
        v = _mk_vehicle(user.id)
        tx = _mk_due_tax(user.id, v.id, next_due=TODAY + timedelta(days=5))
        tx_id = tx.id

    client.post('/api/due/dismiss', json={'kind': 'tax', 'ref_id': tx_id},
                headers=auth_headers(user.id))
    assert not any(it['kind'] == 'tax' for it in _due_items(client, user, auth_headers))

    # The recurring series advances to its next occurrence…
    with app.app_context():
        tx = db.session.get(TaxEntry, tx_id)
        tx.next_due_date = TODAY + timedelta(days=12)
        db.session.commit()

    # …and reappears despite the earlier dismissal.
    assert any(it['kind'] == 'tax' for it in _due_items(client, user, auth_headers))


def test_dismiss_reminder_uses_native_flag(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        r = Reminder(user_id=user.id, vehicle_id=v.id, title='MOT',
                     due_date=TODAY + timedelta(days=3), reminder_type='inspection')
        db.session.add(r)
        db.session.commit()
        r_id = r.id

    resp = client.post('/api/due/dismiss', json={'kind': 'reminder', 'ref_id': r_id},
                       headers=auth_headers(user.id))
    assert resp.status_code == 200

    with app.app_context():
        assert db.session.get(Reminder, r_id).dismissed is True
        # No dismissal row — reminders use their own flag.
        assert DueDismissal.query.filter_by(kind='reminder', ref_id=r_id).count() == 0
    assert _due_items(client, user, auth_headers) == []

    # Undo flips the flag back.
    client.post('/api/due/undismiss', json={'kind': 'reminder', 'ref_id': r_id},
                headers=auth_headers(user.id))
    with app.app_context():
        assert db.session.get(Reminder, r_id).dismissed is False


def test_ownership_enforced(app, client, user, auth_headers):
    with app.app_context():
        other = User(email='other2@example.com', username='other2', is_active=True)
        other.set_password('Str0ng!Passw0rd')
        db.session.add(other)
        db.session.commit()
        ov = _mk_vehicle(other.id, 'Theirs')
        tx = _mk_due_tax(other.id, ov.id, next_due=TODAY + timedelta(days=5))
        tx_id = tx.id

    resp = client.post('/api/due/dismiss', json={'kind': 'tax', 'ref_id': tx_id},
                       headers=auth_headers(user.id))
    assert resp.status_code == 404
    with app.app_context():
        assert DueDismissal.query.count() == 0  # nothing stored


def test_invalid_kind_rejected(client, user, auth_headers):
    resp = client.post('/api/due/dismiss', json={'kind': 'user', 'ref_id': 1},
                       headers=auth_headers(user.id))
    assert resp.status_code == 400
    resp = client.post('/api/due/dismiss', json={'kind': 'tax', 'ref_id': 'abc'},
                       headers=auth_headers(user.id))
    assert resp.status_code == 400


def test_dismiss_is_idempotent(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        tx = _mk_due_tax(user.id, v.id, next_due=TODAY + timedelta(days=5))
        tx_id = tx.id

    for _ in range(2):
        assert client.post('/api/due/dismiss', json={'kind': 'tax', 'ref_id': tx_id},
                           headers=auth_headers(user.id)).status_code == 200
    with app.app_context():
        assert DueDismissal.query.filter_by(kind='tax', ref_id=tx_id).count() == 1

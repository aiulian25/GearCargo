"""Tests for F47 — pending taxes surface in the due feed until marked paid.

The create handler + due feed already supported unpaid taxes; F47 makes them
reachable from the UI (status select + one-tap "Mark paid"). These tests lock
the round-trip: a pending tax ranks in build_due_items as kind 'tax', and
marking it paid via PUT removes it.
"""

from datetime import date, timedelta

from app import db
from app.models import Vehicle, TaxEntry
from app.services.due import build_due_items

TODAY = date.today()


def _mk_vehicle(user_id, name='Focus'):
    v = Vehicle(user_id=user_id, name=name, make='Ford', model='Focus')
    db.session.add(v)
    db.session.commit()
    db.session.refresh(v)
    return v


def _create_tax(client, auth_headers, user_id, vehicle_id, status, due_in_days=10):
    return client.post('/api/taxes', headers=auth_headers(user_id), json={
        'vehicle_id': vehicle_id, 'tax_type': 'road_tax',
        'date': TODAY.isoformat(), 'amount': 120, 'status': status,
        'valid_until': (TODAY + timedelta(days=due_in_days)).isoformat(),
    })


def _tax_ids_in_feed(user_id):
    return {it['ref_id'] for it in build_due_items(user_id) if it['kind'] == 'tax'}


def test_pending_tax_appears_in_due_feed(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        vid = v.id

    resp = _create_tax(client, auth_headers, user.id, vid, 'pending')
    assert resp.status_code == 201, resp.get_data(as_text=True)
    tid = resp.get_json()['entry']['id']
    assert resp.get_json()['entry']['status'] == 'pending'
    assert resp.get_json()['entry']['paid_date'] is None

    with app.app_context():
        assert tid in _tax_ids_in_feed(user.id)


def test_mark_paid_removes_tax_from_feed(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        vid = v.id

    tid = _create_tax(client, auth_headers, user.id, vid, 'pending').get_json()['entry']['id']
    with app.app_context():
        assert tid in _tax_ids_in_feed(user.id)

    # One-tap "Mark paid" — exactly what the UI sends.
    resp = client.put(f'/api/taxes/{tid}', headers=auth_headers(user.id), json={
        'status': 'paid', 'paid_date': TODAY.isoformat(),
    })
    assert resp.status_code == 200
    got = resp.get_json()['entry']
    assert got['status'] == 'paid'
    assert got['paid_date'] == TODAY.isoformat()

    with app.app_context():
        assert tid not in _tax_ids_in_feed(user.id)


def test_paid_tax_never_enters_feed(app, client, user, auth_headers):
    """The unchanged default flow (status 'paid') stays out of Coming up."""
    with app.app_context():
        v = _mk_vehicle(user.id)
        vid = v.id

    tid = _create_tax(client, auth_headers, user.id, vid, 'paid').get_json()['entry']['id']
    with app.app_context():
        assert tid not in _tax_ids_in_feed(user.id)


def test_mark_paid_cross_user_forbidden(app, client, user, auth_headers):
    """A user cannot settle another user's tax."""
    from app.models import User
    with app.app_context():
        other = User(email='taxother@example.com', username='taxother', is_active=True)
        other.set_password('Str0ng!Passw0rd')
        db.session.add(other)
        db.session.commit()
        other_id = other.id
        ov = _mk_vehicle(other_id, 'Theirs')
        ovid = ov.id

    tid = _create_tax(client, auth_headers, other_id, ovid, 'pending').get_json()['entry']['id']

    resp = client.put(f'/api/taxes/{tid}', headers=auth_headers(user.id),
                      json={'status': 'paid', 'paid_date': TODAY.isoformat()})
    assert resp.status_code == 404
    with app.app_context():
        assert db.session.get(TaxEntry, tid).status == 'pending'

"""Tests for F42 — document-expiry pipeline (PUT expires_at → due feed + push).

The Attachment.expires_at / expiry_notified columns, the due-feed 'document'
kind and GET /api/attachments/expiring all existed already; nothing set the
date. F42 adds the UI PUT path, sentinel re-arm, and the daily push job.
"""

import io
from datetime import date, timedelta

from app import db
from app.models import Vehicle, Attachment
from app.services.due import build_due_items
from app.services import check_document_expiry

TODAY = date.today()


def _mk_vehicle(user_id, name='Focus'):
    v = Vehicle(user_id=user_id, name=name, make='Ford', model='Focus')
    db.session.add(v)
    db.session.commit()
    db.session.refresh(v)
    return v


def _upload(client, auth_headers, user_id, vehicle_id):
    """Upload a tiny JPEG so we have a real attachment id to PUT against."""
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (16, 16), (10, 20, 30)).save(buf, format='JPEG')
    resp = client.post(
        '/api/attachments',
        data={'file': (io.BytesIO(buf.getvalue()), 'mot.jpg'),
              'category': 'document', 'vehicle_id': str(vehicle_id)},
        headers=auth_headers(user_id),
        content_type='multipart/form-data',
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()['attachment']['id']


def test_put_expires_at_puts_document_in_due_feed(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        vid = v.id
    aid = _upload(client, auth_headers, user.id, vid)

    # No expiry yet → not in the feed.
    assert not any(it['kind'] == 'document' for it in
                   client.get('/api/due?days=30', headers=auth_headers(user.id)).get_json()['items'])

    exp = (TODAY + timedelta(days=10)).isoformat()
    resp = client.put(f'/api/attachments/{aid}', json={'expires_at': exp},
                      headers=auth_headers(user.id))
    assert resp.status_code == 200
    assert resp.get_json()['attachment']['expires_at'] == exp

    items = client.get('/api/due?days=30', headers=auth_headers(user.id)).get_json()['items']
    doc = next(it for it in items if it['kind'] == 'document')
    assert doc['days_left'] == 10

    # Clearing the expiry removes it again (and the PUT accepts null).
    client.put(f'/api/attachments/{aid}', json={'expires_at': None},
               headers=auth_headers(user.id))
    assert not any(it['kind'] == 'document' for it in
                   client.get('/api/due?days=30', headers=auth_headers(user.id)).get_json()['items'])


def test_check_document_expiry_pushes_once_then_rearms(app, client, user, auth_headers, monkeypatch):
    import app.routes.push as push_mod
    calls = []
    monkeypatch.setattr(push_mod, 'send_push_to_user',
                        lambda *a, **k: calls.append(k.get('tag')) or 1)

    with app.app_context():
        v = _mk_vehicle(user.id)
        vid = v.id
    aid = _upload(client, auth_headers, user.id, vid)

    # Expires in 5 days → within the 14-day horizon.
    client.put(f'/api/attachments/{aid}', json={'expires_at': (TODAY + timedelta(days=5)).isoformat()},
               headers=auth_headers(user.id))

    check_document_expiry(app)
    assert calls == [f'doc-expiry-{aid}']              # pushed once
    with app.app_context():
        assert db.session.get(Attachment, aid).expiry_notified is True

    check_document_expiry(app)
    assert len(calls) == 1                             # sentinel prevents a second push

    # Changing the expiry re-arms the sentinel → pushes again next run.
    client.put(f'/api/attachments/{aid}', json={'expires_at': (TODAY + timedelta(days=7)).isoformat()},
               headers=auth_headers(user.id))
    with app.app_context():
        assert db.session.get(Attachment, aid).expiry_notified is False
    check_document_expiry(app)
    assert len(calls) == 2


def test_far_off_document_not_pushed(app, client, user, auth_headers, monkeypatch):
    import app.routes.push as push_mod
    calls = []
    monkeypatch.setattr(push_mod, 'send_push_to_user', lambda *a, **k: calls.append(1) or 1)

    with app.app_context():
        v = _mk_vehicle(user.id)
        vid = v.id
    aid = _upload(client, auth_headers, user.id, vid)
    client.put(f'/api/attachments/{aid}', json={'expires_at': (TODAY + timedelta(days=60)).isoformat()},
               headers=auth_headers(user.id))

    check_document_expiry(app)
    assert calls == []                                 # 60 days out → outside 14-day horizon


def test_put_expires_at_ownership_enforced(app, client, user, auth_headers):
    """A user cannot set the expiry on someone else's attachment."""
    from app.models import User
    with app.app_context():
        other = User(email='docother@example.com', username='docother', is_active=True)
        other.set_password('Str0ng!Passw0rd')
        db.session.add(other)
        db.session.commit()
        ov = _mk_vehicle(other.id, 'Theirs')
        a = Attachment(user_id=other.id, vehicle_id=ov.id, filename='x.pdf',
                       filepath='/x/x.pdf', original_filename='x.pdf', category='document')
        db.session.add(a)
        db.session.commit()
        their_id = a.id

    resp = client.put(f'/api/attachments/{their_id}',
                      json={'expires_at': (TODAY + timedelta(days=5)).isoformat()},
                      headers=auth_headers(user.id))
    assert resp.status_code == 404
    with app.app_context():
        assert db.session.get(Attachment, their_id).expires_at is None

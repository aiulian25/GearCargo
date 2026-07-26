"""Tests for F58 — user-facing notification-delivery history.

GET /api/push/history returns the authenticated user's own NotificationLog
rows (push + email), newest first, and never another user's.
"""

from datetime import datetime, timedelta

from app import db
from app.models import User, NotificationLog


def _mk_user(email, username):
    u = User(email=email, username=username, is_active=True)
    u.set_password('Str0ng!Passw0rd')
    db.session.add(u)
    db.session.commit()
    return u


def _log(user_id, title, channel='push', status='sent', when=None, **kw):
    row = NotificationLog(
        user_id=user_id, notification_type=kw.get('notification_type', 'reminder'),
        title=title, body=kw.get('body', 'Body text'), channel=channel, status=status,
        error_message=kw.get('error_message'), created_at=when or datetime.utcnow())
    db.session.add(row)
    db.session.commit()
    return row


def test_history_returns_own_rows_newest_first(app, client, user, auth_headers):
    now = datetime.utcnow()
    with app.app_context():
        _log(user.id, 'Older push', when=now - timedelta(hours=2))
        _log(user.id, 'Newer email', channel='email', status='failed',
             when=now - timedelta(minutes=5), error_message='SMTP 550 mailbox unavailable')

    resp = client.get('/api/push/history', headers=auth_headers(user.id))
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['total'] == 2
    titles = [it['title'] for it in body['items']]
    assert titles == ['Newer email', 'Older push']  # newest first

    failed = body['items'][0]
    assert failed['channel'] == 'email'
    assert failed['status'] == 'failed'
    assert failed['error_message'] == 'SMTP 550 mailbox unavailable'

    # A successful row exposes no error_message.
    assert body['items'][1]['status'] == 'sent'
    assert body['items'][1]['error_message'] is None


def test_history_body_truncated_to_200_chars(app, client, user, auth_headers):
    with app.app_context():
        _log(user.id, 'Long', body='x' * 500)

    resp = client.get('/api/push/history', headers=auth_headers(user.id))
    assert len(resp.get_json()['items'][0]['body']) == 200


def test_history_never_leaks_other_users_rows(app, client, user, auth_headers):
    with app.app_context():
        other = _mk_user('nother@example.com', 'nother')
        _log(other.id, 'Their secret notification')
        _log(user.id, 'My notification')

    resp = client.get('/api/push/history', headers=auth_headers(user.id))
    body = resp.get_json()
    assert body['total'] == 1
    assert body['items'][0]['title'] == 'My notification'


def test_history_requires_auth(client):
    resp = client.get('/api/push/history')
    assert resp.status_code == 401


def test_history_pagination_caps_at_50(app, client, user, auth_headers):
    with app.app_context():
        for i in range(55):
            _log(user.id, f'N{i}')

    resp = client.get('/api/push/history', headers=auth_headers(user.id))
    body = resp.get_json()
    assert len(body['items']) == 50          # per-page hard cap
    assert body['total'] == 55
    assert body['has_more'] is True

    page2 = client.get('/api/push/history?page=2', headers=auth_headers(user.id)).get_json()
    assert len(page2['items']) == 5
    assert page2['has_more'] is False

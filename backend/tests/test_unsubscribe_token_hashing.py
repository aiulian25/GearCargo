"""Tests for R4-24 — the unsubscribe token is no longer stored in plaintext.

S08/R7 already hashed the password-reset and e-mail-verification tokens, but
`unsubscribe_token` was both stored and looked up verbatim, so a database or
backup leak yielded working one-click unsubscribe links for every user.

Unlike those two, this token is LONG-LIVED: `email_service` rebuilds the URL
into every digest e-mail. So the raw value has to stay reproducible, or the
link in last week's e-mail would stop working — which is why these tests pin
link stability as hard as they pin the hashing.
"""

import hashlib

import pytest

from app import db
from app.models import User


@pytest.fixture
def subscriber(app):
    with app.app_context():
        user = User(username='unsub', email='unsub@example.com', is_active=True,
                    notifications_enabled=True, notification_email_verified=True)
        user.set_password('StrongPass123!')
        db.session.add(user)
        db.session.commit()
        return user.id


def _stored_token(app, user_id):
    with app.app_context():
        return db.session.get(User, user_id).unsubscribe_token


def test_the_database_never_holds_the_raw_token(app, subscriber):
    with app.app_context():
        user = db.session.get(User, subscriber)
        raw = user.generate_unsubscribe_token()
        db.session.commit()

    stored = _stored_token(app, subscriber)

    assert raw
    assert stored != raw                                   # was: identical
    assert stored == hashlib.sha256(raw.encode('utf-8')).hexdigest()


def test_the_raw_token_from_the_email_unsubscribes(app, client, subscriber):
    with app.app_context():
        raw = db.session.get(User, subscriber).generate_unsubscribe_token()
        db.session.commit()

    response = client.get(f'/api/auth/unsubscribe?token={raw}')

    assert response.status_code == 200
    with app.app_context():
        user = db.session.get(User, subscriber)
        assert user.notifications_enabled is False
        assert user.notification_email_verified is False


def test_the_stored_hash_is_not_accepted_as_a_token(app, client, subscriber):
    """A leaked DB value must not be usable as a link."""
    with app.app_context():
        db.session.get(User, subscriber).generate_unsubscribe_token()
        db.session.commit()
    stored = _stored_token(app, subscriber)

    response = client.get(f'/api/auth/unsubscribe?token={stored}')

    assert response.status_code == 404
    with app.app_context():
        assert db.session.get(User, subscriber).notifications_enabled is True


def test_the_link_is_stable_across_emails(app, subscriber):
    """Every digest rebuilds the URL — last week's link must still work."""
    with app.app_context():
        user = db.session.get(User, subscriber)
        first = user.generate_unsubscribe_token()
        db.session.commit()
    with app.app_context():
        user = db.session.get(User, subscriber)
        second = user.generate_unsubscribe_token()
        db.session.commit()

    assert first == second


def test_an_existing_plaintext_row_still_works_and_is_upgraded(app, client, subscriber):
    """Transparent upgrade: links already in users' inboxes keep working."""
    legacy_raw = 'legacy-plaintext-token-value'
    with app.app_context():
        user = db.session.get(User, subscriber)
        user.unsubscribe_token = legacy_raw          # how rows look before this change
        db.session.commit()

    response = client.get(f'/api/auth/unsubscribe?token={legacy_raw}')

    assert response.status_code == 200
    with app.app_context():
        user = db.session.get(User, subscriber)
        assert user.notifications_enabled is False
        # …and the row is no longer plaintext afterwards.
        assert user.unsubscribe_token != legacy_raw
        assert user.unsubscribe_token == hashlib.sha256(
            legacy_raw.encode('utf-8')).hexdigest()


def test_an_unknown_token_is_rejected(app, client, subscriber):
    with app.app_context():
        db.session.get(User, subscriber).generate_unsubscribe_token()
        db.session.commit()

    response = client.get('/api/auth/unsubscribe?token=not-a-real-token')

    assert response.status_code == 404
    with app.app_context():
        assert db.session.get(User, subscriber).notifications_enabled is True


def test_a_missing_token_is_rejected(client):
    assert client.get('/api/auth/unsubscribe').status_code == 400


def test_one_users_token_never_unsubscribes_another(app, client, subscriber):
    with app.app_context():
        other = User(username='other-unsub', email='other-unsub@example.com',
                     is_active=True, notifications_enabled=True)
        other.set_password('StrongPass123!')
        db.session.add(other)
        db.session.commit()
        other_id = other.id
        other_raw = other.generate_unsubscribe_token()
        db.session.get(User, subscriber).generate_unsubscribe_token()
        db.session.commit()

    client.get(f'/api/auth/unsubscribe?token={other_raw}')

    with app.app_context():
        assert db.session.get(User, other_id).notifications_enabled is False
        assert db.session.get(User, subscriber).notifications_enabled is True


def test_the_email_body_carries_the_raw_token_not_the_hash(app, subscriber):
    """email_service builds the URL — it must not paste the stored hash in."""
    from app.services.email_service import build_unsubscribe_url

    with app.app_context():
        user = db.session.get(User, subscriber)
        raw = user.generate_unsubscribe_token()
        db.session.commit()
        url = build_unsubscribe_url(user)

    stored = _stored_token(app, subscriber)
    assert url and f'token={raw}' in url
    assert stored not in url

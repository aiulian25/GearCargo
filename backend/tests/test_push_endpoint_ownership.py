"""Regression tests for R4-13: POST /push/subscribe evicted another user's push
subscription whenever the endpoint matched.

A browser has ONE push endpoint per profile, so the endpoint is the device's
identity, not the user's. The old code deleted whatever row it found and created
one for the caller — its own comment said "Never silently transfer ownership
across users" while doing exactly that. Anyone who learned a victim's endpoint
URL could silence the victim's notifications and push arbitrary content to their
device.

The policy under test:
  * the caller proves possession of the device by presenting the SAME
    subscription keys the browser hands out -> handover allowed (this is the
    shared-device case, and it is what stops the previous owner's private
    notifications continuing to land on a device someone else now uses);
  * the record is stale (deactivated, never used, or not pushed to in
    _STALE_ENDPOINT_DAYS) -> takeover allowed;
  * otherwise -> 409, and the existing owner keeps the endpoint.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app import db
from app.models import PushSubscription, User
from app.routes.push import _STALE_ENDPOINT_DAYS


ENDPOINT = 'https://fcm.googleapis.com/fcm/send/shared-device-token'
DEVICE_KEYS = {'p256dh': 'device-p256dh-key', 'auth': 'device-auth-key'}
OTHER_KEYS = {'p256dh': 'attacker-p256dh-key', 'auth': 'attacker-auth-key'}


def _make_user(email):
    user = User(username=email.split('@')[0], email=email, is_active=True)
    user.set_password('StrongPass123!')
    db.session.add(user)
    db.session.commit()
    return user


def _subscribe(client, headers, keys=DEVICE_KEYS):
    return client.post('/api/push/subscribe', headers=headers, json={
        'subscription': {'endpoint': ENDPOINT, 'keys': keys},
        'device_type': 'mobile',
    })


def _owner_id():
    row = PushSubscription.query.filter_by(endpoint=ENDPOINT).one()
    return row.user_id


def _seed_owner(app, **row_overrides):
    """User A owns the endpoint; returns (owner_id, other_user_id)."""
    with app.app_context():
        owner = _make_user('owner@example.com')
        other = _make_user('other@example.com')
        subscription = PushSubscription(
            user_id=owner.id, endpoint=ENDPOINT,
            p256dh_key=DEVICE_KEYS['p256dh'], auth_key=DEVICE_KEYS['auth'],
            active=True, last_used_at=datetime.now(timezone.utc),
        )
        for field, value in row_overrides.items():
            setattr(subscription, field, value)
        db.session.add(subscription)
        db.session.commit()
        return owner.id, other.id


def test_a_live_endpoint_is_not_taken_over_by_another_account(app, client, auth_headers):
    """The attack: a caller who knows only the endpoint URL. Their subscription
    keys cannot match, so the claim is refused."""
    owner_id, other_id = _seed_owner(app)

    response = _subscribe(client, auth_headers(other_id), keys=OTHER_KEYS)

    assert response.status_code == 409
    assert response.get_json()['message_key'] == 'push.endpointOwnedByOther'
    with app.app_context():
        assert _owner_id() == owner_id          # the victim keeps their endpoint
        assert PushSubscription.query.filter_by(user_id=other_id).count() == 0


def test_the_same_browser_may_hand_the_device_over(app, client, auth_headers):
    """The shared-device case: the Push API returns the SAME endpoint AND keys to
    whoever is signed in on that browser profile, which proves possession."""
    owner_id, other_id = _seed_owner(app)

    response = _subscribe(client, auth_headers(other_id), keys=DEVICE_KEYS)

    assert response.status_code in (200, 201)
    with app.app_context():
        assert _owner_id() == other_id
        # The previous owner keeps no claim — so their private notifications stop
        # landing on a device they no longer use.
        assert PushSubscription.query.filter_by(user_id=owner_id).count() == 0


def test_a_deactivated_endpoint_may_be_taken_over(app, client, auth_headers):
    owner_id, other_id = _seed_owner(app, active=False)

    response = _subscribe(client, auth_headers(other_id), keys=OTHER_KEYS)

    assert response.status_code in (200, 201)
    with app.app_context():
        assert _owner_id() == other_id
        assert PushSubscription.query.filter_by(user_id=owner_id).count() == 0


def test_an_endpoint_not_pushed_to_for_a_long_time_may_be_taken_over(app, client, auth_headers):
    stale_since = datetime.now(timezone.utc) - timedelta(days=_STALE_ENDPOINT_DAYS + 1)
    owner_id, other_id = _seed_owner(app, last_used_at=stale_since)

    response = _subscribe(client, auth_headers(other_id), keys=OTHER_KEYS)

    assert response.status_code in (200, 201)
    with app.app_context():
        assert _owner_id() == other_id


def test_a_never_used_endpoint_may_be_taken_over(app, client, auth_headers):
    owner_id, other_id = _seed_owner(app, last_used_at=None)

    response = _subscribe(client, auth_headers(other_id), keys=OTHER_KEYS)

    assert response.status_code in (200, 201)
    with app.app_context():
        assert _owner_id() == other_id


def test_the_owner_can_still_re_register(app, client, auth_headers):
    """Re-registration by the current owner must keep working — the browser
    re-subscribes routinely (pushsubscriptionchange)."""
    owner_id, _other_id = _seed_owner(app)

    response = _subscribe(client, auth_headers(owner_id))

    assert response.status_code == 200
    with app.app_context():
        assert _owner_id() == owner_id
        assert PushSubscription.query.filter_by(endpoint=ENDPOINT).count() == 1

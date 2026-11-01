"""GC-007: a browser's captured write identity is checked at the mutation boundary."""
import jwt
import pytest
from uuid import uuid4

from app import db
from app.models import User, Vehicle
from app.routes.auth import generate_tokens


def sign_in(app, client, user):
    with app.test_request_context():
        access, refresh = generate_tokens(user)
    client.set_cookie('access_token', access)
    client.set_cookie('refresh_token', refresh, path='/api/auth/refresh')
    return access, refresh


def scope_headers(identity):
    return {'X-GearCargo-Offline-Owner': identity['owner_key'],
            'X-GearCargo-Offline-Generation': identity['generation'],
            'Idempotency-Key': str(uuid4()), 'X-GearCargo-Mutation-Version': '1'}


def test_offline_identity_is_noncredential_and_not_cached(app, client, user):
    access, refresh = sign_in(app, client, user)
    response = client.get('/api/auth/offline-identity')
    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'no-store'
    identity = response.json
    assert set(identity) == {'owner_id', 'owner_key', 'generation'}
    assert identity['owner_id'] == user.id
    assert len(identity['owner_key']) == len(identity['generation']) == 64
    assert access not in response.text and refresh not in response.text
    assert jwt.decode(access, app.config['JWT_SECRET_KEY'], algorithms=['HS256'])['jti'] not in response.text
    anonymous = app.test_client()
    assert anonymous.post('/api/vehicles', headers=scope_headers(identity), json={'name': 'No auth'}).status_code == 401


def test_same_session_can_write_but_cookie_switch_cannot_relabel_request(app, client, user):
    sign_in(app, client, user)
    identity_a = client.get('/api/auth/offline-identity').json
    assert client.post('/api/vehicles', headers=scope_headers(identity_a), json={'name': 'Account A'}).status_code == 201
    other = User(username='offline_b', email='offline-b@example.invalid', is_active=True)
    other.set_password('StrongPass123!')
    db.session.add(other); db.session.commit()
    sign_in(app, client, other)
    # The worker checked A, then another tab changed cookies before this POST.
    response = client.post('/api/vehicles', headers=scope_headers(identity_a), json={'name': 'Must not reach B'})
    assert response.status_code == 409
    assert response.json['code'] == 'OFFLINE_IDENTITY_MISMATCH'
    assert Vehicle.query.filter_by(user_id=other.id).count() == 0
    assert Vehicle.query.filter_by(user_id=user.id).count() == 1


def test_refresh_preserves_generation_new_login_rotates_it(app, client, user):
    sign_in(app, client, user)
    original = client.get('/api/auth/offline-identity').json
    assert client.post('/api/auth/refresh').status_code == 200
    assert client.get('/api/auth/offline-identity').json == original
    assert client.post('/api/vehicles', headers=scope_headers(original), json={'name': 'After refresh'}).status_code == 201
    sign_in(app, client, user)
    new = client.get('/api/auth/offline-identity').json
    assert new['owner_key'] == original['owner_key']
    assert new['generation'] != original['generation']
    assert client.post('/api/vehicles', headers=scope_headers(original), json={'name': 'Old session'}).status_code == 409
    assert Vehicle.query.filter_by(name='Old session').count() == 0


@pytest.mark.parametrize('invalid', [
    {'X-GearCargo-Offline-Owner': 'x'},
    {'X-GearCargo-Offline-Generation': 'x'},
    {'X-GearCargo-Offline-Owner': 'é', 'X-GearCargo-Offline-Generation': 'a' * 64},
])
def test_partial_or_malformed_identity_fails_closed(app, client, user, invalid):
    sign_in(app, client, user)
    assert client.post('/api/vehicles', headers=invalid, json={'name': 'Bad identity'}).status_code == 409
    assert Vehicle.query.count() == 0


def test_existing_online_client_contract_is_preserved(app, client, user):
    sign_in(app, client, user)
    assert client.post('/api/vehicles', json={'name': 'Online client'}).status_code == 201


def test_deleted_account_cannot_resolve_identity_or_replay(app, client, user):
    sign_in(app, client, user)
    identity = client.get('/api/auth/offline-identity').json
    db.session.delete(user); db.session.commit()
    assert client.get('/api/auth/offline-identity').status_code == 401
    assert client.post('/api/vehicles', headers=scope_headers(identity), json={'name': 'Deleted owner'}).status_code == 401
    assert Vehicle.query.count() == 0

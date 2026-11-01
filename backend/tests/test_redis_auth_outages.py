"""GC-026: live cache failures must not weaken durable authentication."""
import fnmatch
import importlib.util
from datetime import timedelta
from pathlib import Path

import jwt
import pytest
from flask import jsonify
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import event
from sqlalchemy.exc import OperationalError
from app import db
from app.models import UserSession
from app.routes import auth
from app.utils.timeutils import utc_naive_now


class Cache:
    def __init__(self):
        self.values = {}
        self.fail_reads = self.fail_writes = False
        self.after_get = None

    def get(self, key):
        if self.fail_reads:
            raise RedisConnectionError('Disconnected fixture')
        value = self.values.get(key)
        if self.after_get:
            self.after_get(); self.after_get = None
        return value

    def exists(self, key):
        return self.get(key) is not None

    def setex(self, key, ttl, value):
        if self.fail_writes:
            raise RedisConnectionError('Disconnected fixture')
        self.values[key] = value

    def delete(self, *keys):
        if self.fail_writes:
            raise RedisConnectionError('Disconnected fixture')
        count = sum(key in self.values for key in keys)
        for key in keys: self.values.pop(key, None)
        return count

    def scan(self, cursor=0, match='*', count=100):
        if self.fail_reads:
            raise RedisConnectionError('Disconnected fixture')
        return 0, [key for key in self.values if fnmatch.fnmatch(key, match)]


@pytest.fixture
def cache(monkeypatch):
    value = Cache()
    monkeypatch.setattr(auth, 'redis_client', value)
    return value


def issue(app, user):
    with app.test_request_context():
        return auth.generate_tokens(user)


def claims(app, token):
    return jwt.decode(token, app.config['JWT_SECRET_KEY'], algorithms=['HS256'])


def me(app, token, path='/api/auth/me'):
    return app.test_client().get(path, headers={'Authorization': 'Bearer '+token})


@pytest.mark.parametrize('media', [False, True])
@pytest.mark.parametrize('cookie', [False, True])
def test_live_blacklist_failure_uses_durable_session(app, user, cache, media, cookie):
    app.add_url_rule('/test-media', 'test_media', auth.token_required_query_param(lambda owner: jsonify(id=owner.id)))
    access, _ = issue(app, user)
    cache.fail_reads = True
    client = app.test_client()
    if cookie: client.set_cookie('access_token', access)
    response = client.get('/test-media' if media else '/api/auth/me',
                          headers={} if cookie else {'Authorization': 'Bearer '+access})
    assert response.status_code == 200


def test_cache_fails_before_issuance_then_recovers_without_losing_new_session(app, user, cache):
    cache.fail_reads = cache.fail_writes = True
    access, refresh = issue(app, user)
    assert me(app, access).status_code == 200
    cache.fail_reads = cache.fail_writes = False
    assert not cache.values
    assert me(app, access).status_code == 200
    response = app.test_client().post('/api/auth/refresh', json={'refresh_token': refresh})
    assert response.status_code == 200
    assert me(app, access).status_code == 401


@pytest.mark.parametrize('state', ['revoked', 'missing', 'expired'])
def test_healthy_stale_cache_never_authorizes_invalid_durable_session(app, user, cache, state):
    access, refresh = issue(app, user)
    row = UserSession.query.filter_by(jti=claims(app, access)['jti']).one()
    if state == 'revoked': row.revoked = True
    elif state == 'missing': db.session.delete(row)
    else: row.absolute_expires_at = utc_naive_now()-timedelta(seconds=1)
    db.session.commit()
    for down in (False, True, False):
        cache.fail_reads = down
        assert me(app, access).status_code == 401
        assert app.test_client().post('/api/auth/refresh', json={'refresh_token': refresh}).status_code == 401


@pytest.mark.parametrize('value', ['not json', '[]', 'null', '42', '{}', '{"absolute_expires_at":"2099-01-01"}'])
def test_cached_payload_cannot_extend_or_replace_durable_deadline(app, user, cache, value):
    access, refresh = issue(app, user)
    jti = claims(app, access)['jti']
    deadline = UserSession.query.filter_by(jti=jti).one().absolute_expires_at
    cache.values[f'session:{user.id}:{jti}'] = value
    client = app.test_client()
    assert client.post('/api/auth/refresh', json={'refresh_token': refresh}).status_code == 200
    new = claims(app, client.get_cookie('access_token').value)
    assert UserSession.query.filter_by(jti=new['jti']).one().absolute_expires_at == deadline


def test_disconnect_after_blacklist_read_does_not_bypass_revocation(app, user, cache):
    access, _ = issue(app, user)
    row = UserSession.query.filter_by(jti=claims(app, access)['jti']).one()
    def disconnect():
        row.revoked = True; db.session.commit(); cache.fail_reads = True
    cache.after_get = disconnect
    assert me(app, access).status_code == 401


def test_observed_denylist_revocation_survives_cache_loss(app, user, cache):
    access, refresh = issue(app, user)
    cache.values[f'blacklist:{access}'] = '1'
    assert me(app, access).status_code == 401
    cache.values.clear()
    cache.fail_reads = True
    assert me(app, access).status_code == 401
    assert app.test_client().post('/api/auth/refresh', json={'refresh_token': refresh}).status_code == 401


@pytest.mark.parametrize('state', ['revoked', 'expired', 'different_owner'])
def test_admission_cannot_reuse_invalid_session_identity(app, user, cache, state):
    access, _ = issue(app, user)
    jti = claims(app, access)['jti']
    row = UserSession.query.filter_by(jti=jti).one()
    owner = user.id
    if state == 'revoked':
        row.revoked = True
    elif state == 'expired':
        row.absolute_expires_at = utc_naive_now() - timedelta(seconds=1)
    else:
        owner += 1
    db.session.commit()
    with app.test_request_context(), pytest.raises(jwt.InvalidTokenError):
        auth.create_session(owner, jti)
    db.session.refresh(row)
    assert row.user_id == user.id
    assert row.revoked == (state == 'revoked')
    if state == 'expired':
        assert row.absolute_expires_at < utc_naive_now()


@pytest.mark.parametrize('operation', ['logout', 'refresh', 'all'])
def test_cache_cleanup_failure_never_restores_revoked_tokens(app, user, cache, operation):
    access, refresh = issue(app, user)
    cache.fail_writes = True
    if operation == 'logout':
        assert app.test_client().post('/api/auth/logout', headers={'Authorization':'Bearer '+access}).status_code == 200
    elif operation == 'refresh':
        assert app.test_client().post('/api/auth/refresh', json={'refresh_token':refresh}).status_code == 200
    else:
        auth.invalidate_user_sessions(user.id)
    for down in (False, True, False):
        cache.fail_reads = down
        assert me(app, access).status_code == 401
        assert app.test_client().post('/api/auth/refresh', json={'refresh_token':refresh}).status_code == 401


def test_single_device_eviction_survives_redis_outage_and_recovery(app, user, cache):
    user.max_sessions = 1; db.session.commit()
    old, old_refresh = issue(app, user)
    cache.fail_reads = cache.fail_writes = True
    new, _ = issue(app, user)
    for down in (True, False):
        cache.fail_reads = cache.fail_writes = down
        assert me(app, old).status_code == 401
        assert me(app, new).status_code == 200
        assert app.test_client().post('/api/auth/refresh', json={'refresh_token':old_refresh}).status_code == 401


@pytest.fixture
def fail_session_sql(app, user):
    engine = db.engine
    failures = set()
    def fail(conn, cursor, statement, parameters, context, executemany):
        if 'user_sessions' in statement.lower() and statement.split()[0].upper() in failures:
            raise OperationalError('injected session-store failure', {}, RuntimeError('fixture'))
    event.listen(engine, 'before_cursor_execute', fail)
    yield failures
    event.remove(engine, 'before_cursor_execute', fail)
    db.session.rollback()


def test_database_verification_failure_is_controlled_503(app, user, cache, fail_session_sql):
    access, refresh = issue(app, user)
    fail_session_sql.add('SELECT')
    for down in (False, True):
        cache.fail_reads = down
        response = me(app, access)
        assert response.status_code == 503 and response.json['code'] == 'AUTH_UNAVAILABLE'
        assert response.headers['Cache-Control'] == 'no-store'
        response = app.test_client().post('/api/auth/refresh', json={'refresh_token':refresh})
        assert response.status_code == 503


@pytest.mark.parametrize('operation,statement', [('logout', 'UPDATE'), ('refresh', 'UPDATE'), ('refresh', 'INSERT')])
def test_durable_write_failure_never_reports_success_or_rotates_cookies(app, user, cache, fail_session_sql, operation, statement):
    access, refresh = issue(app, user)
    original = dict(cache.values)
    fail_session_sql.add(statement)
    response = app.test_client().post('/api/auth/'+operation,
        headers={'Authorization':'Bearer '+access} if operation=='logout' else {},
        json={'refresh_token':refresh} if operation=='refresh' else {})
    assert response.status_code == 503 and response.json['code'] == 'AUTH_UNAVAILABLE'
    assert not response.headers.getlist('Set-Cookie')
    assert cache.values == original
    fail_session_sql.clear()
    assert me(app, access).status_code == 200
    assert UserSession.query.filter_by(revoked=False).count() == 1


def test_login_issuance_requires_durable_commit(app, user, cache, fail_session_sql):
    old_access, _ = issue(app, user)
    original = dict(cache.values)
    fail_session_sql.add('INSERT')
    response = app.test_client().post('/api/auth/login', json={'email':user.email,'password':'StrongPass123!'})
    assert response.status_code == 503
    assert not response.headers.getlist('Set-Cookie')
    assert cache.values == original
    fail_session_sql.clear()
    assert me(app, old_access).status_code == 200
    assert UserSession.query.filter_by(revoked=False).count() == 1


def test_legacy_revocation_migration_requires_fresh_signin(app, user, cache):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    access, refresh = issue(app, user)
    path = Path(__file__).parents[1]/'migrations/versions/gc026_durable_session_authority.py'
    spec=importlib.util.spec_from_file_location('session_migration',path)
    migration=importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    with db.engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        migration.upgrade(); migration.downgrade()
    db.session.expire_all()
    assert me(app, access).status_code == 401
    cache.fail_reads = True
    assert app.test_client().post('/api/auth/refresh', json={'refresh_token':refresh}).status_code == 401
    new, _ = issue(app, user)
    assert me(app, new).status_code == 200


def test_concurrent_refresh_can_replace_old_session_only_once(app, user, cache, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    _, refresh = issue(app, user)
    barrier = threading.Barrier(2)
    original = auth.get_session_data
    def both_validated(*args):
        result = original(*args)
        barrier.wait(timeout=10)
        return result
    monkeypatch.setattr(auth, 'get_session_data', both_validated)
    def rotate():
        client = app.test_client()
        response = client.post('/api/auth/refresh', json={'refresh_token':refresh})
        return response.status_code
    db.session.remove()
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: rotate(), range(2))) == [200,401]
    db.session.remove()
    assert UserSession.query.filter_by(revoked=False).count() == 1


@pytest.mark.parametrize('route', ['/api/auth/password-reset/verify','/api/auth/password/recover/reset'])
def test_password_reset_and_revocation_roll_back_together(app,user,cache,fail_session_sql,monkeypatch,route):
    access,_ = issue(app,user)
    reset = user.generate_reset_token(); db.session.commit()
    monkeypatch.setattr(auth,'validate_password_strength',lambda _: (True,[],100,'strong'))
    fail_session_sql.add('UPDATE')
    response = app.test_client().post(route,json={'token':reset,'reset_token':reset,'new_password':'NewStrongerPass123!'})
    assert response.status_code == 503
    fail_session_sql.clear(); db.session.refresh(user)
    assert user.check_password('StrongPass123!') and not user.check_password('NewStrongerPass123!')
    assert me(app,access).status_code == 200

"""GC-012: the browser mutation boundary is independent of CORS and proxies."""
import pytest
from flask import Flask, jsonify, g
from flask_wtf import CSRFProtect

from app import create_app, db
from app.models import Vehicle
from app.routes.auth import generate_tokens
from app.routes.widget import api_key_required, _hash_api_key
from app.services.cookie_csrf import init_cookie_csrf

TRUSTED = 'http://localhost:5000'


@pytest.fixture(autouse=True)
def enforce(app):
    app.config['WTF_CSRF_ENABLED'] = True


def proof(client):
    g.pop('csrf_token', None)  # The shared user fixture holds an app context across requests.
    response = client.get('/api/csrf-token', headers={'Origin': TRUSTED})
    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'no-store'
    return {'X-CSRF-Token': response.json['csrf_token'], 'Origin': TRUSTED}


@pytest.fixture()
def signed_in(app, client, user):
    with app.test_request_context():
        access, refresh = generate_tokens(user)
    client.set_cookie('access_token', access)
    client.set_cookie('refresh_token', refresh, path='/api/auth/refresh')
    return client, user, access, refresh


@pytest.mark.parametrize('headers', [
    {'Origin': 'http://evil.localhost:5000', 'Sec-Fetch-Site': 'same-site'},
    {'Origin': 'https://attacker.invalid', 'Sec-Fetch-Site': 'cross-site'},
    {'Origin': 'null'}, {'Origin': TRUSTED, 'Sec-Fetch-Site': 'cross-site'}, {'Origin': TRUSTED + '.evil.invalid'},
    {'Origin': 'http://localhost:5001'}, {'Origin': 'https://localhost:5000'},
    {'Origin': 'http://localhost:5000@evil.invalid'},
    {'Origin': TRUSTED + ', https://attacker.invalid'},
    {'Origin': TRUSTED + '/path'},
    {'Referer': 'http://evil.localhost:5000/form'},
    {'Sec-Fetch-Site': 'same-site'},
    {'Origin': 'http://evil.localhost:5000', 'Host': 'evil.localhost:5000',
     'X-Forwarded-Host': 'localhost:5000', 'X-Forwarded-Proto': 'http'},
])
def test_untrusted_browser_cannot_archive_even_with_valid_proof(signed_in, headers):
    client, user, _, _ = signed_in
    vehicle = Vehicle(user_id=user.id, name='CSRF target')
    db.session.add(vehicle); db.session.commit()
    token = proof(client)['X-CSRF-Token']
    response = client.post(f'/api/vehicles/{vehicle.id}/archive', headers={'X-CSRF-Token': token, **headers})
    assert response.status_code == 403
    assert response.json['code'] == 'CSRF_ORIGIN_REJECTED'
    db.session.refresh(vehicle)
    assert not vehicle.archived


@pytest.mark.parametrize('extra', [{}, {'Authorization': 'Bearer ignored'}, {'X-API-Key': 'ignored'}])
def test_cookie_requests_cannot_bypass_token_check(signed_in, extra):
    client, _, _, _ = signed_in
    response = client.post('/api/vehicles', json={'name': 'Blocked'}, headers={'Origin': TRUSTED, **extra})
    assert response.status_code == 403 and response.json['code'] == 'CSRF_INVALID'
    assert Vehicle.query.count() == 0


@pytest.mark.parametrize('source', [
    {'Origin': TRUSTED, 'Sec-Fetch-Site': 'same-origin'},
    {'Referer': TRUSTED + '/vehicles?view=all'},
    {}, {'Sec-Fetch-Site': 'same-origin'},
])
def test_trusted_and_headerless_clients_need_session_bound_proof(signed_in, app, source):
    client, _, _, _ = signed_in
    token = proof(client)['X-CSRF-Token']
    response = client.post('/api/vehicles', json={'name': 'Accepted'}, headers={'X-CSRF-Token': token, **source})
    assert response.status_code == 201
    other = app.test_client()
    other.set_cookie('access_token', signed_in[2])
    assert other.post('/api/vehicles', json={'name': 'Wrong session'}, headers={'X-CSRF-Token': token, **source}).status_code == 403
    assert Vehicle.query.count() == 1


def test_expired_invalid_and_rotated_proofs_fail_closed(signed_in, app):
    client, _, _, _ = signed_in
    headers = proof(client)
    app.config['WTF_CSRF_TIME_LIMIT'] = -1
    assert client.post('/api/vehicles', json={'name': 'Expired'}, headers=headers).status_code == 403
    app.config['WTF_CSRF_TIME_LIMIT'] = 3600
    assert client.post('/api/vehicles', json={'name': 'Tampered'}, headers={**headers, 'X-CSRF-Token': 'fake'}).status_code == 403
    assert client.post('/api/auth/refresh', headers=headers).status_code == 200
    assert client.post('/api/vehicles', json={'name': 'Stale'}, headers=headers).status_code == 403
    assert client.post('/api/vehicles', json={'name': 'Fresh'}, headers=proof(client)).status_code == 201


def test_login_and_logout_require_proof_and_rotate_it(client, user):
    credentials = {'email': user.email, 'password': 'StrongPass123!'}
    assert client.post('/api/auth/login', json=credentials, headers={'Origin': TRUSTED}).status_code == 403
    assert client.post('/api/auth/login', json=credentials, headers={'Authorization': 'Bearer fake'}).status_code == 403
    before = proof(client)
    response = client.post('/api/auth/login', json=credentials, headers=before)
    assert response.status_code == 200
    assert all('HttpOnly' in c and 'SameSite=Strict' in c for c in response.headers.getlist('Set-Cookie') if c.startswith(('access_token=', 'refresh_token=')))
    assert client.post('/api/auth/logout', headers=before).status_code == 403
    current = proof(client)
    assert client.post('/api/auth/logout', headers=current).status_code == 200
    assert client.post('/api/auth/login', json=credentials, headers=current).status_code == 403


def test_bearer_refresh_and_real_api_key_clients_need_no_browser_headers(app, client, user, auth_headers):
    @app.post('/api/test-key-only')
    @api_key_required
    def key_only(current_user):
        return jsonify(user=current_user.id)

    user.api_key_hash = _hash_api_key('explicit-api-key')
    db.session.commit()
    assert client.post('/api/test-key-only', headers={'X-API-Key': 'explicit-api-key'}).status_code == 200
    assert client.post('/api/test-key-only', headers={'X-API-Key': 'bad'}).status_code == 401
    assert client.post('/api/vehicles', json={'name': 'Bearer'}, headers=auth_headers(user.id)).status_code == 201
    with app.test_request_context():
        _, refresh = generate_tokens(user)
    assert client.post('/api/auth/refresh', json={'refresh_token': refresh}).status_code == 200


def test_preflight_is_safe_but_simple_form_and_malicious_token_reads_are_denied(signed_in):
    client, _, _, _ = signed_in
    assert client.options('/api/vehicles', headers={'Origin': 'http://evil.localhost:5000', 'Access-Control-Request-Method': 'POST'}).status_code == 200
    assert client.post('/api/vehicles', data={'name': 'Simple form'}, headers={'Origin': TRUSTED}).status_code == 403
    assert client.get('/api/csrf-token', headers={'Origin': 'http://evil.localhost:5000'}).status_code == 403
    assert client.get('/api/csrf-token', headers={'Sec-Fetch-Site': 'cross-site'}).status_code == 403
    assert Vehicle.query.count() == 0


@pytest.mark.parametrize('origin', ['*', 'null', 'https://*.example.com', 'https://example.com/path', 'https://user:pass@example.com', 'https://example.com:bad'])
def test_invalid_deployment_allowlist_fails_at_startup(origin):
    app = Flask(__name__)
    app.config.update(APP_URL=origin, SECRET_KEY='test')
    with pytest.raises(ValueError, match='exact HTTP'):
        init_cookie_csrf(app, CSRFProtect())


def test_explicit_origins_and_default_ports_do_not_depend_on_proxy_host():
    app = Flask(__name__)
    app.config.update(APP_URL='https://ignored.example', SECRET_KEY='test',
                      CSRF_TRUSTED_ORIGINS=['https://cars.example:443', 'http://192.168.1.10:8080'])
    init_cookie_csrf(app, CSRFProtect())
    client = app.test_client()
    for origin in ('https://cars.example', 'http://192.168.1.10:8080'):
        assert client.get('/api/csrf-token', headers={'Origin': origin, 'Host': 'internal:5000'}).status_code == 200
    assert client.get('/api/csrf-token', headers={'Origin': 'https://ignored.example', 'X-Forwarded-Host': 'cars.example'}).status_code == 403


def test_browser_generated_csp_reports_remain_anonymous_and_do_not_exempt_other_routes(app):
    # Exercise the real reporting route with its limiter enabled. The general
    # test config disables the limiter, whose decorator retains only a weakref.
    config = type('ReportingConfig', (), {**app.config, 'RATELIMIT_ENABLED': True,
                                         'RATELIMIT_STORAGE_URL': 'memory://'})
    reporting_app = create_app(config)
    client = reporting_app.test_client()
    client.set_cookie('access_token', 'ignored-by-anonymous-reporting')
    response = client.post('/api/csp-report', content_type='application/csp-report',
                           json={'csp-report': {'violated-directive': 'script-src', 'blocked-uri': 'inline'}})
    assert response.status_code == 204
    assert client.post('/api/vehicles', json={'name': 'Still protected'}).status_code == 403


@pytest.mark.parametrize('method', ['PUT', 'PATCH', 'DELETE'])
def test_other_unsafe_methods_also_require_browser_proof(signed_in, method):
    client, _, _, _ = signed_in
    response = client.open('/api/vehicles/999', method=method, headers={'Origin': TRUSTED})
    assert response.status_code == 403 and response.json['code'] == 'CSRF_INVALID'

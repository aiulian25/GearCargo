"""GC-013: JWT purpose is independent of signature, session and transport."""
from datetime import timedelta
from pathlib import Path

import jwt
import pytest

import app as app_module
from app import db
from app.models import Attachment, UserSession
from app.routes import auth
from app.utils import sign_attachment_url, sign_upload_url
from app.utils.timeutils import utc_naive_now


@pytest.fixture()
def credentials(app, user):
    user.is_admin = True
    db.session.commit()
    with app.test_request_context():
        access, refresh = auth.generate_tokens(user)
    return access, refresh


@pytest.fixture()
def media(app, user, tmp_path, monkeypatch):
    pdf = tmp_path / 'receipt.pdf'
    pdf.write_bytes(b'%PDF-1.4\n% private test receipt\n%%EOF\n')
    attachment = Attachment(user_id=user.id, filename='receipt.pdf', original_filename='receipt.pdf',
                            filepath=str(pdf), file_type='application/pdf', file_size=pdf.stat().st_size)
    db.session.add(attachment); db.session.commit()
    # The legacy image store resolves relative to the factory module. Redirect
    # only that fixture path so no test file is written into the checkout.
    monkeypatch.setattr(app_module, '__file__', str(tmp_path / 'app' / '__init__.py'))
    uploads = tmp_path / 'uploads'
    uploads.mkdir(exist_ok=True)
    (uploads / 'photo.png').write_bytes(b'private image fixture')
    return attachment


def decode(app, token):
    return jwt.decode(token, app.config['JWT_SECRET_KEY'], algorithms=['HS256'])


def reissue(app, token, **changes):
    payload = decode(app, token)
    payload.update(changes)
    return jwt.encode(payload, app.config['JWT_SECRET_KEY'], algorithm='HS256')


def get_with_token(app, path, token, transport):
    client = app.test_client()
    if transport == 'cookie':
        client.set_cookie('access_token', token)
        return client.get(path)
    return client.get(path, headers={'Authorization': f'Bearer {token}'})


def protected_paths(media):
    return ['/api/auth/me', '/api/admin/stats', f'/api/attachments/{media.id}/view',
            f'/api/attachments/{media.id}/download']


def test_issued_tokens_have_explicit_distinct_purposes(app, credentials):
    access, refresh = (decode(app, value) for value in credentials)
    assert access['type'] == 'access'
    assert refresh['type'] == 'refresh'
    assert access['jti'] == refresh['jti']
    assert access['offline_generation'] == refresh['offline_generation']


@pytest.mark.parametrize('transport', ['cookie', 'bearer'])
def test_access_succeeds_on_ordinary_admin_and_media_paths(app, credentials, media, transport):
    for path in protected_paths(media):
        response = get_with_token(app, path, credentials[0], transport)
        assert response.status_code == 200, (path, response.status_code)


@pytest.mark.parametrize('transport', ['cookie', 'bearer'])
@pytest.mark.parametrize('purpose', ['refresh', 'missing', 'unknown', 'calendar_feed', None, False, ['access']],
                         ids=['refresh', 'missing', 'unknown', 'calendar', 'null', 'boolean', 'array'])
def test_wrong_purpose_cannot_authenticate_any_protected_path(app, credentials, media, transport, purpose):
    if purpose == 'refresh':
        token = credentials[1]  # A real issued refresh token with a live session.
    else:
        payload = decode(app, credentials[0])
        if purpose == 'missing':
            payload.pop('type', None)
        else:
            payload['type'] = purpose
        token = jwt.encode(payload, app.config['JWT_SECRET_KEY'], algorithm='HS256')
    for path in protected_paths(media):
        response = get_with_token(app, path, token, transport)
        assert response.status_code == 401, (path, transport, purpose, response.status_code)
        assert response.json['error'] == 'Invalid token'


@pytest.mark.parametrize('purpose', ['access', 'missing', 'unknown', None, ['refresh']])
def test_refresh_endpoint_still_rejects_non_refresh_purposes(app, credentials, purpose):
    payload = decode(app, credentials[1])
    if purpose == 'missing':
        payload.pop('type')
    else:
        payload['type'] = purpose
    token = jwt.encode(payload, app.config['JWT_SECRET_KEY'], algorithm='HS256')
    response = app.test_client().post('/api/auth/refresh', json={'refresh_token': token})
    assert response.status_code == 401 and response.json['error'] == 'Invalid token type'


@pytest.mark.parametrize('state', ['revoked', 'absolute_expired', 'jwt_expired', 'bad_signature'])
def test_access_purpose_never_bypasses_existing_session_or_crypto_checks(app, credentials, media, state):
    token = credentials[0]
    if state in {'revoked', 'absolute_expired'}:
        row = UserSession.query.filter_by(jti=decode(app, token)['jti']).one()
        if state == 'revoked':
            row.revoked = True
        else:
            row.absolute_expires_at = utc_naive_now() - timedelta(seconds=1)
        db.session.commit()
    elif state == 'jwt_expired':
        token = reissue(app, token, exp=utc_naive_now() - timedelta(seconds=1))
    else:
        token = jwt.encode(decode(app, token), 'other-signing-key-0123456789abcdef', algorithm='HS256')
    for path in protected_paths(media):
        response = get_with_token(app, path, token, 'bearer')
        assert response.status_code == 401, (state, path)
        if state in {'revoked', 'absolute_expired'}:
            assert response.json['code'] == 'SESSION_EXPIRED'
    if state in {'revoked', 'absolute_expired'}:
        response = app.test_client().post('/api/auth/refresh', json={'refresh_token': credentials[1]})
        assert response.status_code == 401 and response.json['code'] == 'SESSION_EXPIRED'


def test_refresh_rotates_purposes_jti_and_preserves_absolute_deadline(app, credentials, media):
    old_access, old_refresh = credentials
    old_payload = decode(app, old_access)
    old_row = UserSession.query.filter_by(jti=old_payload['jti']).one()
    deadline = old_row.absolute_expires_at
    client = app.test_client()
    assert client.post('/api/auth/refresh', json={'refresh_token': old_refresh}).status_code == 200
    access = client.get_cookie('access_token').value
    refresh = client.get_cookie('refresh_token', path='/api/auth/refresh').value
    access_claims, refresh_claims = decode(app, access), decode(app, refresh)
    assert access_claims['type'] == 'access' and refresh_claims['type'] == 'refresh'
    assert access_claims['jti'] == refresh_claims['jti'] != old_payload['jti']
    assert access_claims['offline_generation'] == old_payload['offline_generation']
    assert UserSession.query.filter_by(jti=access_claims['jti']).one().absolute_expires_at == deadline
    db.session.refresh(old_row)
    assert old_row.revoked
    for path in protected_paths(media):
        assert client.get(path).status_code == 200
        assert get_with_token(app, path, old_access, 'bearer').status_code == 401
        assert get_with_token(app, path, refresh, 'bearer').status_code == 401
    assert app.test_client().post('/api/auth/refresh', json={'refresh_token': old_refresh}).status_code == 401


def test_legacy_access_is_rejected_but_explicit_refresh_can_renew_the_session(app, credentials):
    payload = decode(app, credentials[0])
    payload.pop('type', None)
    legacy = jwt.encode(payload, app.config['JWT_SECRET_KEY'], algorithm='HS256')
    client = app.test_client()
    client.set_cookie('access_token', legacy)
    client.set_cookie('refresh_token', credentials[1], path='/api/auth/refresh')
    assert client.get('/api/auth/me').status_code == 401
    assert client.post('/api/auth/refresh').status_code == 200
    assert decode(app, client.get_cookie('access_token').value)['type'] == 'access'
    assert client.get('/api/auth/me').status_code == 200


def test_signed_media_remains_separate_and_jwt_query_tokens_do_not_unlock_uploads(app, credentials, media):
    client = app.test_client()
    path = f'/api/attachments/{media.id}/view'
    for token in credentials:
        assert client.get(path, query_string={'token': token}).status_code == 401
        assert client.get('/uploads/photo.png', query_string={'token': token}).status_code == 403
        assert client.get('/uploads/photo.png', headers={'Authorization': f'Bearer {token}'}).status_code == 403
    signed_attachment = sign_attachment_url(media.id, media.user_id)
    response = client.get(signed_attachment)
    assert response.status_code == 200 and response.data == Path(media.filepath).read_bytes()
    assert client.get(signed_attachment.replace('sig=', 'sig=tampered')).status_code == 403
    signed_image = sign_upload_url('/uploads/photo.png')
    assert client.get(signed_image).data == b'private image fixture'
    assert client.get(signed_image.replace('sig=', 'sig=tampered')).status_code == 403
    # An explicitly presented wrong-purpose cookie is rejected even if the URL
    # also has a valid signature; credential precedence remains unchanged.
    client.set_cookie('access_token', credentials[1])
    assert client.get(signed_attachment).status_code == 401

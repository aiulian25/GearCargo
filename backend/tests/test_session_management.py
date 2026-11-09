"""GC-102: the Profile session list, per-device sign-out and self-service account deletion."""
from datetime import timedelta
import hashlib

import pyotp
import pytest

from app import ACCOUNT_DELETION_ATTEMPTS_PER_HOUR, db
from app.config import TestingConfig
from app.models import ActivityLog, Backup, User, UserSession
from app.routes import auth
from app.utils.timeutils import utc_naive_now
from tests.test_2fa_disable import PASSWORD, _enable_2fa

ANDROID_CHROME = ('Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36')
MAC_SAFARI = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 '
              '(KHTML, like Gecko) Version/17.5 Safari/605.1.15')
IPHONE_SAFARI = ('Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 '
                 '(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1')
SESSIONS_URL = '/api/auth/sessions'
REVOKE_OTHERS_URL = '/api/auth/sessions/revoke-others'
ACCOUNT_URL = '/api/auth/account'
ME_URL = '/api/auth/me'
REFRESH_URL = '/api/auth/refresh'


def _other_user(username='other'):
    other = User(username=username, email=f'{username}@example.com', is_active=True)
    other.set_password(PASSWORD)
    db.session.add(other)
    db.session.commit()
    return other.id


def _session_id(jti):
    return UserSession.query.filter_by(jti=jti).one().id


def _issue_tokens(app, user):
    with app.test_request_context():
        return auth.generate_tokens(user)


def _bearer(access_token):
    return {'Authorization': f'Bearer {access_token}'}


def _account_exists(user_id):
    db.session.expire_all()
    return db.session.get(User, user_id) is not None


def test_the_session_list_marks_this_device_and_hides_identifiers(app, client, user, auth_headers):
    user_id = user.id
    other_id = _other_user()
    auth_headers(other_id)
    this_device = auth_headers(user_id, jti='this-device')
    for jti, user_agent in (('phone-session', ANDROID_CHROME), ('laptop-session', MAC_SAFARI),
                            ('iphone-session', IPHONE_SAFARI)):
        with app.test_request_context(headers={'User-Agent': user_agent}):
            auth.create_session(user_id, jti)
    tomorrow = utc_naive_now() + timedelta(days=1)
    # Every create_session prunes the account's expired rows, so add this one last.
    db.session.add_all([
        UserSession(user_id=user_id, jti='revoked-session', absolute_expires_at=tomorrow, revoked=True),
        UserSession(user_id=user_id, jti='expired-session', absolute_expires_at=utc_naive_now() - timedelta(minutes=1)),
    ])
    db.session.commit()
    assert UserSession.query.filter_by(jti='expired-session').count() == 1

    response = client.get(SESSIONS_URL, headers=this_device)

    assert response.status_code == 200, response.json
    sessions = response.json['sessions']
    assert [session['id'] for session in sessions] == [_session_id('iphone-session'), _session_id('laptop-session'),
                                                       _session_id('phone-session'), _session_id('this-device')]
    assert [session['is_current'] for session in sessions] == [False, False, False, True]
    assert [(session['browser'], session['os']) for session in sessions[:3]] == [
        ('Safari', 'iOS'), ('Safari', 'macOS'), ('Chrome', 'Android')]
    for session in sessions:
        assert set(session) == {'id', 'browser', 'os', 'last_active_at', 'expires_at', 'is_current'}
        assert session['last_active_at'].endswith('Z') and session['expires_at'].endswith('Z')


def test_an_iphone_keeps_the_known_device_fingerprint_it_had_as_macos(app):
    """iPhones parsed as macOS before they were recognised as iOS. A changed
    signature would send every iPhone owner a false new-device alert."""
    language = {'Accept-Language': 'en-GB,en;q=0.9'}
    with app.test_request_context(headers={'User-Agent': IPHONE_SAFARI, **language}):
        iphone, _ = auth.get_device_fingerprint()
    with app.test_request_context(headers={'User-Agent': MAC_SAFARI, **language}):
        mac, _ = auth.get_device_fingerprint()

    assert iphone == hashlib.sha256(b'mobile|Safari|macOS|en-gb').hexdigest()[:16]
    assert mac != iphone


def test_signing_out_one_device_ends_only_that_session(app, client, user, auth_headers):
    keep = auth_headers(user.id, jti='keep')
    drop = auth_headers(user.id, jti='drop')

    response = client.delete(f"{SESSIONS_URL}/{_session_id('drop')}", headers=keep)

    assert response.status_code == 200, response.json
    ended = client.get(ME_URL, headers=drop)
    assert ended.status_code == 401 and ended.json['code'] == 'SESSION_EXPIRED'
    assert client.get(ME_URL, headers=keep).status_code == 200


@pytest.mark.parametrize('target', ['another account', 'revoked', 'unknown'])
def test_a_session_that_is_not_live_and_mine_is_not_found(app, client, user, auth_headers, target):
    other_headers = auth_headers(_other_user(), jti='another account')
    db.session.add(UserSession(user_id=user.id, jti='revoked', revoked=True,
                               absolute_expires_at=utc_naive_now() + timedelta(days=1)))
    db.session.commit()
    session_id = _session_id(target) if target != 'unknown' else 999999

    response = client.delete(f'{SESSIONS_URL}/{session_id}', headers=auth_headers(user.id))

    assert response.status_code == 404
    assert response.json['message_key'] == 'profile.sessionChanged'
    assert client.get(ME_URL, headers=other_headers).status_code == 200


def test_a_device_that_refreshed_keeps_its_new_session(app, client, user, auth_headers):
    this_device = auth_headers(user.id)
    _, refresh_token = _issue_tokens(app, user)
    listed_id = UserSession.query.filter_by(user_id=user.id).order_by(UserSession.id.desc()).first().id
    # A cookie-less client, so the rotated cookies never reach this device's requests.
    assert app.test_client().post(REFRESH_URL, json={'refresh_token': refresh_token}).status_code == 200

    response = client.delete(f'{SESSIONS_URL}/{listed_id}', headers=this_device)

    assert response.status_code == 404
    assert response.json['message_key'] == 'profile.sessionChanged'
    remaining = client.get(SESSIONS_URL, headers=this_device).json['sessions']
    assert len(remaining) == 2 and listed_id not in {session['id'] for session in remaining}


def test_signing_out_other_devices_keeps_this_one(app, client, user, auth_headers):
    this_device = auth_headers(user.id)
    tablet = auth_headers(user.id)
    phone_access, phone_refresh = _issue_tokens(app, user)
    other_device = auth_headers(_other_user())

    response = client.post(REVOKE_OTHERS_URL, headers=this_device)

    assert response.status_code == 200, response.json
    assert response.json['revoked'] == 2
    assert client.get(ME_URL, headers=this_device).status_code == 200
    assert client.get(ME_URL, headers=tablet).status_code == 401
    assert client.get(ME_URL, headers=_bearer(phone_access)).status_code == 401
    refreshed = app.test_client().post(REFRESH_URL, json={'refresh_token': phone_refresh})
    assert refreshed.status_code == 401 and refreshed.json['code'] == 'SESSION_EXPIRED'
    assert client.get(ME_URL, headers=other_device).status_code == 200


@pytest.mark.parametrize('body', [{}, {'password': ''}, {'password': 'NotMyPassword!'}, [PASSWORD], PASSWORD],
                         ids=['empty', 'blank', 'wrong', 'array body', 'string body'])
def test_account_deletion_refuses_a_wrong_or_missing_password(app, client, user, auth_headers, body):
    user_id = user.id
    headers = auth_headers(user_id)

    response = client.delete(ACCOUNT_URL, json=body, headers=headers)

    # 403, never 401: the web client signs out on any 401.
    assert response.status_code == 403
    assert response.json['message_key'] == 'profile.deleteAccountPasswordInvalid'
    assert _account_exists(user_id)
    assert client.get(ME_URL, headers=headers).status_code == 200
    assert ActivityLog.query.filter_by(event_type='account_deletion_denied', user_id=user_id,
                                       success=False).count() == 1


def _wrong_authenticator_code(secret):
    real = pyotp.TOTP(secret).now()
    return {'totp_code': str((int(real) + 1) % 1_000_000).zfill(6)}


@pytest.mark.parametrize('second_factor, deleted', [
    (lambda secret: {}, False),
    (_wrong_authenticator_code, False),
    (lambda secret: {'totp_code': pyotp.TOTP(secret).now()}, True),
    (lambda secret: {'backup_code': 'dead-beef'}, True),
], ids=['missing', 'wrong authenticator code', 'authenticator code', 'backup code'])
def test_account_deletion_needs_a_second_factor_when_enabled(app, client, user, auth_headers, second_factor, deleted):
    user_id = user.id
    secret = _enable_2fa(user_id)

    response = client.delete(ACCOUNT_URL, json={'password': PASSWORD, **second_factor(secret)},
                             headers=auth_headers(user_id))

    assert response.status_code == (200 if deleted else 403), response.json
    assert _account_exists(user_id) is not deleted
    if not deleted:
        assert response.json['message_key'] == 'profile.deleteAccountCodeInvalid'


@pytest.mark.parametrize('other_admin_active, deleted', [(None, False), (False, False), (True, True)],
                         ids=['no other admin', 'inactive other admin', 'active other admin'])
def test_the_last_active_administrator_cannot_delete_their_account(app, client, user, auth_headers,
                                                                    other_admin_active, deleted):
    user_id = user.id
    user.is_admin = True
    if other_admin_active is not None:
        db.session.add(User(username='second-admin', email='second-admin@example.com', password_hash='fixture',
                            is_admin=True, is_active=other_admin_active))
    db.session.commit()

    response = client.delete(ACCOUNT_URL, json={'password': PASSWORD}, headers=auth_headers(user_id, is_admin=True))

    assert response.status_code == (200 if deleted else 400), response.json
    assert _account_exists(user_id) is not deleted
    if not deleted:
        assert response.json['message_key'] == 'profile.deleteAccountLastAdmin'


def test_an_account_deletion_conflict_carries_a_message_key(app, client, user, auth_headers):
    user_id = user.id
    # Saved before the operator moved BACKUP_FOLDER, so its absolute path now leaves the storage folder.
    db.session.add(Backup(user_id=user_id, backup_type='full', format='zip', status='completed',
                          filename='old.zip', filepath='/old-install/volumes/backups/1/old.zip'))
    db.session.commit()

    response = client.delete(ACCOUNT_URL, json={'password': PASSWORD}, headers=auth_headers(user_id))

    assert response.status_code == 409, response.json
    assert response.json['message_key'] == 'profile.deleteAccountConflict'
    # The specific reason stays in the body for administrators.
    assert response.json['error']
    assert _account_exists(user_id)


def test_account_deletion_expires_cookies_and_every_session(app, client, user, auth_headers, monkeypatch):
    user_id, email = user.id, user.email
    audited = []
    monkeypatch.setattr(auth.security_audit, 'account_deleted', lambda *account: audited.append(account))
    this_device = auth_headers(user_id)
    other_device = auth_headers(user_id)

    response = client.delete(ACCOUNT_URL, json={'password': PASSWORD}, headers=this_device)

    assert response.status_code == 200, response.json
    assert response.json['message'] == 'Account deleted'
    assert response.json['cleanup']['state'] in {'completed', 'pending'}
    cookies = response.headers.getlist('Set-Cookie')
    for name in ('access_token', 'refresh_token'):
        assert any(cookie.startswith(f'{name}=;') and 'Max-Age=0' in cookie for cookie in cookies), cookies
    assert not _account_exists(user_id)
    assert UserSession.query.filter_by(user_id=user_id).count() == 0
    assert app.test_client().get(ME_URL, headers=other_device).status_code == 401
    assert audited == [(user_id, email)]


def test_account_deletion_attempts_are_limited_per_account(tmp_path):
    """Each attempt pauses the whole instance (exclusive restore lease), so a
    typo in the endpoint name silently dropping the limit must fail here."""
    from app import create_app

    class LimitedConfig(TestingConfig):
        SQLALCHEMY_DATABASE_URI = f'sqlite:///{tmp_path}/limited.sqlite'
        SESSION_TYPE = 'filesystem'
        SESSION_FILE_DIR = str(tmp_path / 'sessions')
        VOLUMES_PATH = UPLOAD_FOLDER = BACKUP_FOLDER = str(tmp_path)
        REDIS_URL = 'memory://'
        RATELIMIT_ENABLED = True
        RATELIMIT_STORAGE_URL = 'memory://'
        RATELIMIT_DEFAULT = '1000 per hour'

    limited_app = create_app(LimitedConfig)
    with limited_app.app_context():
        db.create_all()
        first_user = db.session.get(User, _other_user('first'))
        second_user = db.session.get(User, _other_user('second'))
        first_headers = _bearer(_issue_tokens(limited_app, first_user)[0])
        second_headers = _bearer(_issue_tokens(limited_app, second_user)[0])

    limited_client = limited_app.test_client()
    wrong_password = {'password': 'NotMyPassword!'}
    statuses = [limited_client.delete(ACCOUNT_URL, json=wrong_password, headers=first_headers).status_code
                for _ in range(ACCOUNT_DELETION_ATTEMPTS_PER_HOUR + 1)]
    second_status = limited_client.delete(ACCOUNT_URL, json=wrong_password, headers=second_headers).status_code

    with limited_app.app_context():
        db.session.remove()
        db.drop_all()

    assert statuses == [403] * ACCOUNT_DELETION_ATTEMPTS_PER_HOUR + [429]
    assert second_status == 403

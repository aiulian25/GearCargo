"""Passkeys (WebAuthn): the properties this app is responsible for.

The cryptography belongs to py_webauthn and is not re-tested here. What is
tested is everything around it: which deployments can offer a passkey at all,
that a challenge works once and only for what and whom it was opened for, that
user verification is actually demanded of the library, and that a passkey
sign-in issues a full session without asking for a second factor.
"""

import base64
import json

import pytest

from app import db
from app.models.passkey import Passkey
from app.services import passkey_service


HOSTED_URL = 'https://cars.example.org'
HOSTED_ORIGIN = 'https://cars.example.org'
HOSTED_RELYING_PARTY = 'cars.example.org'


def _b64(raw):
    return base64.urlsafe_b64encode(raw).decode().rstrip('=')


class _FakeRedis:
    """Enough Redis for the ceremony store: set/get/delete with a pipeline."""

    def __init__(self):
        self.store = {}

    def ping(self):
        return True

    def set(self, key, value, ex=None):
        self.store[key] = value

    def pipeline(self, transaction=True):
        return _FakePipeline(self)


class _FakePipeline:
    def __init__(self, redis):
        self.redis = redis
        self.calls = []

    def get(self, key):
        self.calls.append(('get', key))

    def delete(self, key):
        self.calls.append(('delete', key))

    def execute(self):
        results = []
        for kind, key in self.calls:
            if kind == 'get':
                results.append(self.redis.store.get(key))
            else:
                results.append(self.redis.store.pop(key, None) is not None)
        self.calls = []
        return results


@pytest.fixture()
def hosted(app, monkeypatch):
    """An app reachable by name, with a working ceremony store."""
    app.config['APP_URL'] = HOSTED_URL
    app.config['CSRF_TRUSTED_ORIGINS'] = []
    app.config['WTF_CSRF_ENABLED'] = False
    fake = _FakeRedis()
    monkeypatch.setattr(passkey_service, '_redis_client', lambda: fake)
    return fake


def _client_data(challenge_b64, ceremony_type):
    payload = {
        'type': ceremony_type,
        'challenge': challenge_b64,
        'origin': HOSTED_ORIGIN,
        'crossOrigin': False,
    }
    return _b64(json.dumps(payload).encode())


def _credential(challenge_b64, ceremony_type, credential_id='cred-1', user_handle=None):
    response = {'clientDataJSON': _client_data(challenge_b64, ceremony_type)}
    if user_handle is not None:
        response['userHandle'] = user_handle
    return {'id': credential_id, 'rawId': credential_id,
            'type': 'public-key', 'response': response}


def _stored_passkey(user_id, credential_id='cred-1',
                    relying_party_id=HOSTED_RELYING_PARTY, sign_count=4):
    passkey = Passkey(
        user_id=user_id,
        relying_party_id=relying_party_id,
        credential_id=credential_id,
        public_key=_b64(b'public-key-bytes'),
        sign_count=sign_count,
        backed_up=False,
        name='Phone',
    )
    db.session.add(passkey)
    db.session.commit()
    return passkey


# --- which deployments can offer a passkey ---------------------------------

@pytest.mark.parametrize('app_url', [
    'http://192.0.2.10:5000',
    'http://[2001:db8::1]:5000',
])
def test_a_deployment_reached_by_address_offers_no_passkey(app, app_url):
    """Browsers keep passkeys per hostname, so a bare address can hold none."""
    with app.app_context():
        app.config['APP_URL'] = app_url
        app.config['CSRF_TRUSTED_ORIGINS'] = []
        assert passkey_service.relying_party() is None
        assert passkey_service.passkeys_available() is False


def test_a_deployment_reached_by_name_offers_passkeys(app):
    with app.app_context():
        app.config['APP_URL'] = HOSTED_URL
        app.config['CSRF_TRUSTED_ORIGINS'] = []
        assert passkey_service.relying_party() == (
            HOSTED_RELYING_PARTY, [HOSTED_ORIGIN])


def test_sign_in_options_are_refused_where_passkeys_cannot_work(app, client):
    with app.app_context():
        app.config['APP_URL'] = 'http://192.0.2.10:5000'
        app.config['CSRF_TRUSTED_ORIGINS'] = []
        app.config['WTF_CSRF_ENABLED'] = False
    response = client.post('/api/auth/passkeys/login/options')
    assert response.status_code == 400
    assert response.get_json()['message_key'] == passkey_service.MESSAGE_UNAVAILABLE


# --- the ceremony store ----------------------------------------------------

def test_a_challenge_works_once(app, hosted):
    with app.app_context():
        options = passkey_service.authentication_options()
        challenge = options['challenge']
        assert passkey_service._take_ceremony(
            challenge, passkey_service.PURPOSE_SIGN_IN, None) is True
        # A replay of the same answer finds nothing left to consume.
        assert passkey_service._take_ceremony(
            challenge, passkey_service.PURPOSE_SIGN_IN, None) is False


def test_an_enrolment_challenge_cannot_be_used_to_sign_in(app, hosted, user):
    with app.app_context():
        options = passkey_service.registration_options(user)
        challenge = options['challenge']
        assert passkey_service._take_ceremony(
            challenge, passkey_service.PURPOSE_SIGN_IN, None) is False


def test_one_person_cannot_finish_another_persons_enrolment(app, hosted, user):
    with app.app_context():
        options = passkey_service.registration_options(user)
        challenge = options['challenge']
        someone_else = user.id + 1
        assert passkey_service._take_ceremony(
            challenge, passkey_service.PURPOSE_ENROL, someone_else) is False


def test_a_ceremony_is_refused_when_its_store_is_unreachable(app, monkeypatch, user):
    """Fail closed: no challenge store means no ceremony, not an unchecked one."""
    with app.app_context():
        app.config['APP_URL'] = HOSTED_URL
        app.config['CSRF_TRUSTED_ORIGINS'] = []
        monkeypatch.setattr(passkey_service, '_redis_client', lambda: None)
        with pytest.raises(passkey_service.PasskeyError) as refusal:
            passkey_service.authentication_options()
        assert refusal.value.message_key == passkey_service.MESSAGE_UNAVAILABLE


# --- what the library is asked to enforce ----------------------------------

def test_enrolment_demands_user_verification_and_a_discoverable_key(app, hosted, user):
    with app.app_context():
        options = passkey_service.registration_options(user)
    selection = options['authenticatorSelection']
    assert selection['userVerification'] == 'required'
    assert selection['residentKey'] == 'required'
    assert options['rp']['id'] == HOSTED_RELYING_PARTY


def test_sign_in_demands_user_verification(app, hosted):
    with app.app_context():
        options = passkey_service.authentication_options()
    assert options['userVerification'] == 'required'
    assert options['rpId'] == HOSTED_RELYING_PARTY


def test_verification_is_pinned_to_this_origin_and_demands_user_verification(
        app, hosted, user, monkeypatch):
    """A future edit cannot quietly accept an unverified or cross-origin answer."""
    import webauthn
    seen = {}

    class _Verified:
        credential_id = b'cred-1'
        new_sign_count = 9
        credential_backed_up = True
        user_verified = True

    def _capture(**kwargs):
        seen.update(kwargs)
        return _Verified()

    monkeypatch.setattr(webauthn, 'verify_authentication_response', _capture)
    with app.app_context():
        stored = _stored_passkey(user.id)
        options = passkey_service.authentication_options()
        credential = _credential(options['challenge'], 'webauthn.get',
                                 credential_id=stored.credential_id)
        passkey_service.verify_authentication(credential)

    assert seen['require_user_verification'] is True
    assert seen['expected_rp_id'] == HOSTED_RELYING_PARTY
    assert seen['expected_origin'] == [HOSTED_ORIGIN]


def test_a_passkey_answering_for_someone_else_is_refused(app, hosted, user, monkeypatch):
    import webauthn
    monkeypatch.setattr(webauthn, 'verify_authentication_response',
                        lambda **kwargs: pytest.fail('should refuse before verifying'))
    with app.app_context():
        stored = _stored_passkey(user.id)
        options = passkey_service.authentication_options()
        credential = _credential(options['challenge'], 'webauthn.get',
                                 credential_id=stored.credential_id,
                                 user_handle=_b64(str(user.id + 1).encode()))
        with pytest.raises(passkey_service.PasskeyError) as refusal:
            passkey_service.verify_authentication(credential)
        assert refusal.value.message_key == passkey_service.MESSAGE_REFUSED


def test_a_refused_signature_advances_nothing(app, hosted, user, monkeypatch):
    import webauthn

    def _refuse(**kwargs):
        raise ValueError('bad signature')

    monkeypatch.setattr(webauthn, 'verify_authentication_response', _refuse)
    with app.app_context():
        stored = _stored_passkey(user.id, sign_count=4)
        options = passkey_service.authentication_options()
        credential = _credential(options['challenge'], 'webauthn.get',
                                 credential_id=stored.credential_id)
        with pytest.raises(passkey_service.PasskeyError):
            passkey_service.verify_authentication(credential)
        assert db.session.get(Passkey, stored.id).sign_count == 4
        assert db.session.get(Passkey, stored.id).last_used_at is None


def test_a_successful_sign_in_advances_the_counter(app, hosted, user, monkeypatch):
    import webauthn

    class _Verified:
        credential_id = b'cred-1'
        new_sign_count = 11
        credential_backed_up = True
        user_verified = True

    monkeypatch.setattr(webauthn, 'verify_authentication_response',
                        lambda **kwargs: _Verified())
    with app.app_context():
        stored = _stored_passkey(user.id, sign_count=4)
        options = passkey_service.authentication_options()
        credential = _credential(options['challenge'], 'webauthn.get',
                                 credential_id=stored.credential_id)
        passkey = passkey_service.verify_authentication(credential)
        assert passkey.sign_count == 11
        assert passkey.last_used_at is not None


# --- ownership and listing -------------------------------------------------

def test_a_passkey_made_for_another_hostname_is_shown_as_elsewhere(app, hosted, user):
    with app.app_context():
        _stored_passkey(user.id, credential_id='old-host',
                        relying_party_id='old.example.net')
        listed = passkey_service.list_passkeys(user.id)
        assert listed[0]['other_relying_party'] == 'old.example.net'


def test_a_passkey_made_here_is_not_flagged_as_elsewhere(app, hosted, user):
    with app.app_context():
        _stored_passkey(user.id)
        listed = passkey_service.list_passkeys(user.id)
        assert listed[0]['other_relying_party'] is None


def test_one_person_cannot_remove_another_persons_passkey(app, hosted, user):
    with app.app_context():
        stored = _stored_passkey(user.id)
        with pytest.raises(passkey_service.PasskeyError) as refusal:
            passkey_service.delete_passkey(user.id + 1, stored.id)
        assert refusal.value.message_key == passkey_service.MESSAGE_NOT_FOUND
        assert db.session.get(Passkey, stored.id) is not None


def test_enrolment_stops_at_the_per_person_limit(app, hosted, user):
    with app.app_context():
        for index in range(passkey_service.PASSKEYS_PER_USER):
            _stored_passkey(user.id, credential_id=f'cred-{index}')
        with pytest.raises(passkey_service.PasskeyError) as refusal:
            passkey_service.registration_options(user)
        assert refusal.value.message_key == passkey_service.MESSAGE_LIMIT_REACHED


def test_a_stored_passkey_never_exposes_key_material(app, hosted, user):
    with app.app_context():
        _stored_passkey(user.id)
        listed = passkey_service.list_passkeys(user.id)
    serialised = json.dumps(listed)
    assert 'public_key' not in serialised
    assert 'credential_id' not in serialised


def test_deleting_an_account_takes_its_passkeys_with_it(app, hosted, user):
    """A passkey row holds a user_id, so leaving it behind would break the
    account deletion that GC-003's inventory guard checks for."""
    with app.app_context():
        stored = _stored_passkey(user.id)
        passkey_id = stored.id
        owner = db.session.get(type(user), user.id)
        db.session.delete(owner)
        db.session.commit()
        assert db.session.get(Passkey, passkey_id) is None

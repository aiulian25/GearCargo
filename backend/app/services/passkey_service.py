"""
GearCargo - Passkey (WebAuthn) service

Signing in with the device's own lock in place of a password and a code. A
passkey here must verify the person (user verification is required), so one
passkey alone satisfies both steps and no TOTP code is asked afterwards.

Two deployment facts shape this module:

* Browsers only keep passkeys for a site reached by name. A deployment reached
  at a bare address has none available, so the feature reports itself unusable
  rather than failing in the middle of a ceremony.
* The app serves from several gunicorn workers, so a challenge created by one
  worker has to be readable by another. Challenges live in Redis, not in
  process memory. When Redis cannot be reached the ceremony is refused rather
  than allowed through unchecked.
"""

import ipaddress
import json
import logging
from urllib.parse import urlparse

from flask import current_app

from app import db
from app.models.passkey import Passkey
from app.utils.timeutils import utc_naive_now

logger = logging.getLogger(__name__)

CEREMONY_TIMEOUT_MILLISECONDS = 300000
CEREMONY_TIMEOUT_SECONDS = CEREMONY_TIMEOUT_MILLISECONDS // 1000
CEREMONY_KEY_PREFIX = 'passkey_ceremony:'
PASSKEYS_PER_USER = 10
DEFAULT_PASSKEY_NAME = 'Passkey'

PURPOSE_ENROL = 'enrol'
PURPOSE_SIGN_IN = 'sign_in'

MESSAGE_UNAVAILABLE = 'passkeys.errorUnavailable'
MESSAGE_LIMIT_REACHED = 'passkeys.errorLimitReached'
MESSAGE_NOT_ADDED = 'passkeys.errorNotAdded'
MESSAGE_REFUSED = 'passkeys.errorRefused'
MESSAGE_NOT_FOUND = 'passkeys.errorNotFound'


class PasskeyError(Exception):
    """A refusal carrying the translation key the client should show."""

    def __init__(self, message_key):
        super().__init__(message_key)
        self.message_key = message_key


def _public_origins():
    """Every origin the browser may legitimately use, most specific first."""
    configured = current_app.config.get('CSRF_TRUSTED_ORIGINS') or []
    if configured:
        return list(configured)
    app_url = current_app.config.get('APP_URL') or ''
    parsed = urlparse(app_url)
    if not parsed.scheme or not parsed.hostname:
        return []
    return [f'{parsed.scheme}://{parsed.netloc}']


def _is_bare_address(hostname):
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return True


def relying_party():
    """``(relying_party_id, origins)`` for this deployment, or ``None``.

    ``None`` means no passkey can work here: the app is reached by a bare IP
    address, or no usable public origin is configured.
    """
    origins = _public_origins()
    if not origins:
        return None
    hostname = urlparse(origins[0]).hostname
    if not hostname or _is_bare_address(hostname):
        return None
    return hostname, origins


def passkeys_available():
    return relying_party() is not None


def _require_relying_party():
    resolved = relying_party()
    if resolved is None:
        raise PasskeyError(MESSAGE_UNAVAILABLE)
    return resolved


def _redis_client():
    """A Redis client, or ``None`` when one cannot be reached."""
    try:
        from redis import Redis
        redis_url = current_app.config.get('REDIS_URL')
        if not redis_url:
            return None
        client = Redis.from_url(redis_url)
        client.ping()
        return client
    except Exception as exc:
        logger.warning('Passkeys: Redis unavailable (%s)', type(exc).__name__)
        return None


def _remember_ceremony(challenge_b64, purpose, user_id):
    """Record an open ceremony. Refuses the ceremony if it cannot be stored."""
    client = _redis_client()
    if client is None:
        raise PasskeyError(MESSAGE_UNAVAILABLE)
    payload = json.dumps({'purpose': purpose, 'user_id': user_id})
    client.set(CEREMONY_KEY_PREFIX + challenge_b64, payload, ex=CEREMONY_TIMEOUT_SECONDS)


def _take_ceremony(challenge_b64, purpose, user_id):
    """Consume a ceremony once. True only for the purpose and person it was opened for.

    The record is removed before anything else about the response is checked,
    so a refused answer still ends its ceremony and cannot be replayed.
    """
    client = _redis_client()
    if client is None:
        return False
    key = CEREMONY_KEY_PREFIX + challenge_b64
    pipeline = client.pipeline(transaction=True)
    pipeline.get(key)
    pipeline.delete(key)
    stored = pipeline.execute()[0]
    if stored is None:
        return False
    try:
        ceremony = json.loads(stored)
    except (TypeError, ValueError):
        return False
    return ceremony.get('purpose') == purpose and ceremony.get('user_id') == user_id


def _challenge_of(credential):
    """The challenge the response was made for, or ``None`` when unreadable."""
    from webauthn.helpers import parse_client_data_json, bytes_to_base64url
    try:
        response = credential.get('response') or {}
        client_data = parse_client_data_json(
            _base64url_to_bytes(response['clientDataJSON']))
    except Exception:
        return None
    return bytes_to_base64url(client_data.challenge)


def _base64url_to_bytes(value):
    from webauthn.helpers import base64url_to_bytes
    return base64url_to_bytes(value)


def _user_passkeys(user_id):
    return Passkey.query.filter_by(user_id=user_id).order_by(Passkey.created_at.asc()).all()


def list_passkeys(user_id):
    resolved = relying_party()
    current_relying_party_id = resolved[0] if resolved else None
    return [row.to_dict(current_relying_party_id) for row in _user_passkeys(user_id)]


def registration_options(user):
    """Options for adding a passkey, and the challenge remembered for it."""
    from webauthn import generate_registration_options, options_to_json
    from webauthn.helpers import bytes_to_base64url
    from webauthn.helpers.structs import (
        AuthenticatorSelectionCriteria,
        PublicKeyCredentialDescriptor,
        ResidentKeyRequirement,
        UserVerificationRequirement,
    )

    relying_party_id, _origins = _require_relying_party()
    own = _user_passkeys(user.id)
    if len(own) >= PASSKEYS_PER_USER:
        raise PasskeyError(MESSAGE_LIMIT_REACHED)

    # Offering the same authenticator twice would store a second row for one
    # passkey; listing them lets the browser say it already has one.
    already_here = [
        PublicKeyCredentialDescriptor(id=_base64url_to_bytes(row.credential_id))
        for row in own
        if row.relying_party_id == relying_party_id
    ]

    options = generate_registration_options(
        rp_id=relying_party_id,
        rp_name=current_app.config.get('APP_NAME', 'GearCargo'),
        user_id=str(user.id).encode(),
        user_name=user.email,
        user_display_name=getattr(user, 'name', None) or user.email,
        timeout=CEREMONY_TIMEOUT_MILLISECONDS,
        exclude_credentials=already_here,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
    )
    _remember_ceremony(bytes_to_base64url(options.challenge), PURPOSE_ENROL, user.id)
    return json.loads(options_to_json(options))


def verify_registration(user, credential, suggested_name=None):
    """Store the passkey the browser created, or refuse it."""
    from webauthn import verify_registration_response
    from webauthn.helpers import bytes_to_base64url

    relying_party_id, origins = _require_relying_party()
    challenge_b64 = _challenge_of(credential)
    if challenge_b64 is None or not _take_ceremony(challenge_b64, PURPOSE_ENROL, user.id):
        raise PasskeyError(MESSAGE_NOT_ADDED)

    try:
        verified = verify_registration_response(
            credential=credential,
            expected_challenge=_base64url_to_bytes(challenge_b64),
            expected_rp_id=relying_party_id,
            expected_origin=origins,
            require_user_verification=True,
        )
    except Exception as exc:
        logger.info('Passkey enrolment refused (%s)', type(exc).__name__)
        raise PasskeyError(MESSAGE_NOT_ADDED)

    credential_id = bytes_to_base64url(verified.credential_id)
    if Passkey.query.filter_by(credential_id=credential_id).first() is not None:
        raise PasskeyError(MESSAGE_NOT_ADDED)

    passkey = Passkey(
        user_id=user.id,
        relying_party_id=relying_party_id,
        credential_id=credential_id,
        public_key=bytes_to_base64url(verified.credential_public_key),
        sign_count=verified.sign_count,
        backed_up=bool(verified.credential_backed_up),
        name=(suggested_name or '').strip() or DEFAULT_PASSKEY_NAME,
    )
    passkey.transport_list = (credential.get('response') or {}).get('transports') or []
    db.session.add(passkey)
    db.session.commit()
    return passkey


def authentication_options():
    """The challenge for signing in.

    No account is named: passkeys made here are discoverable, so the browser
    offers whichever ones it holds and the answer says who it belongs to.
    """
    from webauthn import generate_authentication_options, options_to_json
    from webauthn.helpers import bytes_to_base64url
    from webauthn.helpers.structs import UserVerificationRequirement

    relying_party_id, _origins = _require_relying_party()
    options = generate_authentication_options(
        rp_id=relying_party_id,
        timeout=CEREMONY_TIMEOUT_MILLISECONDS,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    _remember_ceremony(bytes_to_base64url(options.challenge), PURPOSE_SIGN_IN, None)
    return json.loads(options_to_json(options))


def verify_authentication(credential):
    """The passkey that answered, once its signature and counter check out."""
    from webauthn import verify_authentication_response

    relying_party_id, origins = _require_relying_party()
    challenge_b64 = _challenge_of(credential)
    if challenge_b64 is None or not _take_ceremony(challenge_b64, PURPOSE_SIGN_IN, None):
        raise PasskeyError(MESSAGE_REFUSED)

    credential_id = credential.get('id')
    passkey = Passkey.query.filter_by(
        credential_id=credential_id, relying_party_id=relying_party_id).first()
    if passkey is None:
        raise PasskeyError(MESSAGE_REFUSED)

    # The handle the authenticator returns says whose passkey answered; a
    # mismatch means this credential is not the one we hold for that person.
    user_handle = (credential.get('response') or {}).get('userHandle')
    if user_handle and _handle_mismatch(user_handle, passkey.user_id):
        raise PasskeyError(MESSAGE_REFUSED)

    try:
        verified = verify_authentication_response(
            credential=credential,
            expected_challenge=_base64url_to_bytes(challenge_b64),
            expected_rp_id=relying_party_id,
            expected_origin=origins,
            credential_public_key=_base64url_to_bytes(passkey.public_key),
            credential_current_sign_count=passkey.sign_count,
            require_user_verification=True,
        )
    except Exception as exc:
        logger.info('Passkey sign-in refused (%s)', type(exc).__name__)
        raise PasskeyError(MESSAGE_REFUSED)

    passkey.sign_count = verified.new_sign_count
    passkey.backed_up = bool(verified.credential_backed_up)
    passkey.last_used_at = utc_naive_now()
    return passkey


def _handle_mismatch(user_handle, user_id):
    try:
        return _base64url_to_bytes(user_handle).decode() != str(user_id)
    except Exception:
        return True


def delete_passkey(user_id, passkey_id):
    passkey = Passkey.query.filter_by(id=passkey_id, user_id=user_id).first()
    if passkey is None:
        raise PasskeyError(MESSAGE_NOT_FOUND)
    name = passkey.name
    db.session.delete(passkey)
    db.session.commit()
    return name

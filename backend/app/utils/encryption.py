"""
GearCargo - Field-Level Encryption Utility
AES-128-CBC + HMAC via Fernet (symmetric) for GDPR-compliant PII storage.

This module is the single source of truth for at-rest field encryption (2FA /
email-OTP secrets, notification email, CalDAV credentials).

S06 — key derivation, versioning and rotation
----------------------------------------------
* Keys are derived from ENCRYPTION_KEY with **HKDF-SHA256** (the correct KDF for
  high-entropy key material) rather than a single bare SHA-256.
* New ciphertext is tagged with a ``v2:`` prefix so the format is self-describing.
  Pre-S06 ciphertext (the unprefixed single-SHA-256 scheme) is still decryptable,
  so upgrading requires NO data migration — values are re-encrypted to v2 the next
  time they are written, or in bulk via ``scripts/reencrypt_pii.py``.
* Rotation is supported via ``MultiFernet``: set ENCRYPTION_KEY to the new key and
  list the previous key(s) in ENCRYPTION_KEYS_OLD. New data is encrypted with the
  new key; old data still decrypts with any listed key. Run the re-encryption
  script, then drop ENCRYPTION_KEYS_OLD. See README "Rotating the encryption key".
"""

import base64
import hashlib
import logging
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from flask import current_app

logger = logging.getLogger(__name__)

# Version tag for the HKDF-derived scheme (S06). A Fernet token is urlsafe-base64
# and always begins with 'gAAAAA', so it can never collide with this prefix.
_V2_PREFIX = 'v2:'

# Fixed, non-secret HKDF parameters. RFC 5869 permits a fixed/non-secret salt when
# the input keying material is already high-entropy (ENCRYPTION_KEY is meant to be
# 256 bits from secrets.token_hex(32)). Changing these would invalidate v2
# ciphertext, so they are constants.
_HKDF_SALT = b'gearcargo.field-encryption.v2'
_HKDF_INFO = b'fernet-256'


def _seed_value() -> str:
    """Return the primary key seed (ENCRYPTION_KEY, falling back to SECRET_KEY in
    dev). Raises in production-like setups where neither is set."""
    key_seed = current_app.config.get('ENCRYPTION_KEY') or current_app.config.get('SECRET_KEY')
    if not key_seed or key_seed in ('', 'dev-secret-key-change-in-production'):
        raise RuntimeError('ENCRYPTION_KEY must be set for field-level encryption')
    return str(key_seed)


def _old_seeds() -> tuple:
    """Decrypt-only previous key seeds, for zero-downtime rotation (S06).

    Read from ENCRYPTION_KEYS_OLD (comma-separated). Empty when not rotating.
    """
    raw = current_app.config.get('ENCRYPTION_KEYS_OLD', '') or ''
    return tuple(s.strip() for s in raw.split(',') if s.strip())


@lru_cache(maxsize=32)
def _hkdf_key(seed: str) -> bytes:
    """HKDF-SHA256 → urlsafe-base64 Fernet key (S06 scheme). Cached per seed."""
    raw = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_HKDF_SALT,
        info=_HKDF_INFO,
    ).derive(seed.encode('utf-8'))
    return base64.urlsafe_b64encode(raw)


@lru_cache(maxsize=32)
def _legacy_key(seed: str) -> bytes:
    """Pre-S06 derivation: single SHA-256 → urlsafe-base64. Kept ONLY so existing
    ciphertext written before S06 can still be decrypted."""
    return base64.urlsafe_b64encode(hashlib.sha256(seed.encode('utf-8')).digest())


def _v2_fernet() -> MultiFernet:
    """MultiFernet over the v2 (HKDF) keys: primary first, then any rotation keys.
    Encrypt uses the primary key; decrypt tries every key."""
    seeds = (_seed_value(),) + _old_seeds()
    return MultiFernet([Fernet(_hkdf_key(s)) for s in seeds])


def _legacy_fernet() -> MultiFernet:
    """MultiFernet over the legacy (SHA-256) keys, for decrypting pre-S06 data."""
    seeds = (_seed_value(),) + _old_seeds()
    return MultiFernet([Fernet(_legacy_key(s)) for s in seeds])


def is_versioned(ciphertext: str) -> bool:
    """True if *ciphertext* is stored in the current (v2) scheme."""
    return bool(ciphertext) and ciphertext.startswith(_V2_PREFIX)


def encrypt_field(plaintext: str) -> str:
    """Encrypt a string field for DB storage. Returns 'v2:'-prefixed ciphertext."""
    if not plaintext:
        return ''
    token = _v2_fernet().encrypt(plaintext.encode('utf-8')).decode('utf-8')
    return _V2_PREFIX + token


def decrypt_field(ciphertext: str) -> str:
    """Decrypt a stored field. Returns '' on failure or empty input.

    Handles both the current v2 (HKDF) scheme and legacy (unprefixed SHA-256)
    ciphertext transparently, and any rotation key listed in ENCRYPTION_KEYS_OLD.
    """
    if not ciphertext:
        return ''
    try:
        if ciphertext.startswith(_V2_PREFIX):
            token = ciphertext[len(_V2_PREFIX):].encode('utf-8')
            return _v2_fernet().decrypt(token).decode('utf-8')
        # Legacy pre-S06 ciphertext (no prefix): SHA-256-derived key.
        return _legacy_fernet().decrypt(ciphertext.encode('utf-8')).decode('utf-8')
    except (InvalidToken, Exception) as e:
        logger.error(f"Field decryption failed: {type(e).__name__}")
        return ''


def reencrypt_field(ciphertext: str) -> str:
    """Return *ciphertext* re-encrypted under the current primary v2 key.

    Used by the key-rotation script. Returns the input unchanged if it cannot be
    decrypted (so the caller can decide how to handle plaintext/garbage). A value
    that is already current-scheme is still re-encrypted (its token changes) — the
    caller may skip writes by comparing the decrypted value instead.
    """
    if not ciphertext:
        return ciphertext
    plaintext = decrypt_field(ciphertext)
    if plaintext == '':
        return ciphertext  # not decryptable with any known key — leave as-is
    return encrypt_field(plaintext)


def hash_email(email: str) -> str:
    """One-way SHA-256 hash of a normalised email. Used for lookups without decryption."""
    if not email:
        return ''
    normalised = email.strip().lower()
    return hashlib.sha256(normalised.encode('utf-8')).hexdigest()

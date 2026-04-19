"""
GearCargo - Field-Level Encryption Utility
AES-256 via Fernet (symmetric) for GDPR-compliant PII storage.
Uses ENCRYPTION_KEY from app config, derived through SHA-256 → Fernet key.
"""

import base64
import hashlib
import logging
from cryptography.fernet import Fernet, InvalidToken
from flask import current_app

logger = logging.getLogger(__name__)


def _get_key() -> bytes:
    """Derive a Fernet-compatible key from ENCRYPTION_KEY config."""
    key_seed = current_app.config.get('ENCRYPTION_KEY') or current_app.config.get('SECRET_KEY')
    if not key_seed or key_seed in ('', 'dev-secret-key-change-in-production'):
        raise RuntimeError('ENCRYPTION_KEY must be set for field-level encryption')
    return base64.urlsafe_b64encode(hashlib.sha256(str(key_seed).encode()).digest())


def encrypt_field(plaintext: str) -> str:
    """Encrypt a string field for database storage. Returns base64-encoded ciphertext."""
    if not plaintext:
        return ''
    fernet = Fernet(_get_key())
    return fernet.encrypt(plaintext.encode('utf-8')).decode('utf-8')


def decrypt_field(ciphertext: str) -> str:
    """Decrypt a stored field. Returns empty string on failure."""
    if not ciphertext:
        return ''
    try:
        fernet = Fernet(_get_key())
        return fernet.decrypt(ciphertext.encode('utf-8')).decode('utf-8')
    except (InvalidToken, Exception) as e:
        logger.error(f"Field decryption failed: {type(e).__name__}")
        return ''


def hash_email(email: str) -> str:
    """One-way SHA-256 hash of a normalised email. Used for lookups without decryption."""
    if not email:
        return ''
    normalised = email.strip().lower()
    return hashlib.sha256(normalised.encode('utf-8')).hexdigest()

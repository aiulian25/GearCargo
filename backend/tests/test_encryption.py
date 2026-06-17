"""Unit tests for field-level encryption (app/utils/encryption.py).

Covers the S06 HKDF/Fernet round-trip, the self-describing v2 prefix, safe
handling of empty/garbage input, and the deterministic email lookup hash.
"""

from app.utils.encryption import (
    encrypt_field,
    decrypt_field,
    reencrypt_field,
    hash_email,
    is_versioned,
)


def test_encrypt_decrypt_roundtrip(app):
    with app.app_context():
        ciphertext = encrypt_field("totp-secret-ABC123")
        assert ciphertext.startswith("v2:")
        assert is_versioned(ciphertext)
        assert ciphertext != "totp-secret-ABC123"
        assert decrypt_field(ciphertext) == "totp-secret-ABC123"


def test_empty_input_is_passthrough(app):
    with app.app_context():
        assert encrypt_field("") == ""
        assert decrypt_field("") == ""
        assert is_versioned("") is False


def test_ciphertext_is_non_deterministic(app):
    # Fernet uses a random IV, so the same plaintext yields different tokens,
    # but both must decrypt back to the original.
    with app.app_context():
        a = encrypt_field("same-value")
        b = encrypt_field("same-value")
        assert a != b
        assert decrypt_field(a) == "same-value"
        assert decrypt_field(b) == "same-value"


def test_decrypt_garbage_returns_empty_not_raise(app):
    with app.app_context():
        assert decrypt_field("v2:not-a-valid-fernet-token") == ""
        assert decrypt_field("totally-bogus-unprefixed") == ""


def test_reencrypt_preserves_plaintext(app):
    with app.app_context():
        original = encrypt_field("rotate-me")
        rotated = reencrypt_field(original)
        assert decrypt_field(rotated) == "rotate-me"


def test_hash_email_deterministic_and_normalised(app):
    with app.app_context():
        # Case and surrounding whitespace must not change the lookup hash.
        assert hash_email("Test@Example.com") == hash_email("  test@example.com  ")
        assert hash_email("a@b.com") != hash_email("c@d.com")
        assert len(hash_email("a@b.com")) == 64  # SHA-256 hex
        assert hash_email("") == ""

"""Unit tests for password hashing (app/models/user.py).

Covers the basic set/check round-trip, rejection of an empty hash, and the S02
property that passphrases longer than bcrypt's 72-byte limit are NOT silently
truncated (a SHA-256 pre-hash makes the full passphrase significant).
"""

from app.models import User


def test_set_and_check_password(app):
    with app.app_context():
        u = User(username="pwuser", email="pw@example.com")
        u.set_password("StrongPass123!")
        assert u.password_hash
        assert u.password_hash != "StrongPass123!"  # never stored in plaintext
        assert u.check_password("StrongPass123!") is True
        assert u.check_password("WrongPass123!") is False


def test_empty_hash_rejects_any_password(app):
    with app.app_context():
        u = User(username="nopw", email="nopw@example.com")
        assert u.password_hash is None
        assert u.check_password("anything") is False


def test_long_passphrase_not_truncated_at_72_bytes(app):
    # S02: without the SHA-256 pre-hash, bcrypt truncates at 72 bytes and these
    # two passphrases (identical for the first 72 bytes) would both verify.
    with app.app_context():
        prefix = "A" * 72
        u = User(username="longpw", email="long@example.com")
        u.set_password(prefix + "_correct_suffix")
        assert u.check_password(prefix + "_correct_suffix") is True
        assert u.check_password(prefix + "_WRONG_suffix") is False

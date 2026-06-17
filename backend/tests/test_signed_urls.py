"""Unit tests for HMAC-signed URLs (app/utils/__init__.py).

Covers the upload signature and the S20 attachment view signature: valid
round-trip, expiry, tamper rejection, and identity binding (a token for one
attachment/user must not verify for another).
"""

from urllib.parse import urlparse, parse_qs

from app.utils import (
    sign_upload_url,
    verify_upload_signature,
    sign_attachment_url,
    verify_attachment_signature,
)


def _qs(url):
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


# ── Upload signatures ────────────────────────────────────────────────────────

def test_upload_sign_then_verify(app):
    with app.app_context():
        q = _qs(sign_upload_url("/uploads/receipt.png"))
        assert verify_upload_signature("/uploads/receipt.png", q["exp"], q["sig"])


def test_upload_tampered_signature_rejected(app):
    with app.app_context():
        q = _qs(sign_upload_url("/uploads/receipt.png"))
        assert not verify_upload_signature("/uploads/receipt.png", q["exp"], "deadbeef")


def test_upload_signature_bound_to_path(app):
    with app.app_context():
        q = _qs(sign_upload_url("/uploads/receipt.png"))
        # Same signature, different path → must fail.
        assert not verify_upload_signature("/uploads/other.png", q["exp"], q["sig"])


def test_upload_expired_rejected(app):
    with app.app_context():
        q = _qs(sign_upload_url("/uploads/receipt.png", expiry=-1))
        assert not verify_upload_signature("/uploads/receipt.png", q["exp"], q["sig"])


def test_upload_malformed_exp_rejected(app):
    with app.app_context():
        assert not verify_upload_signature("/uploads/x.png", "not-an-int", "abc")


# ── Attachment view signatures (S20) ──────────────────────────────────────────

def test_attachment_sign_then_verify(app):
    with app.app_context():
        q = _qs(sign_attachment_url(42, 7))
        assert q["uid"] == "7"
        assert verify_attachment_signature(42, 7, q["exp"], q["sig"])


def test_attachment_signature_bound_to_attachment_id(app):
    with app.app_context():
        q = _qs(sign_attachment_url(42, 7))
        # Replaying the token for a different attachment must fail.
        assert not verify_attachment_signature(99, 7, q["exp"], q["sig"])


def test_attachment_signature_bound_to_user_id(app):
    with app.app_context():
        q = _qs(sign_attachment_url(42, 7))
        # Replaying the token for a different user must fail.
        assert not verify_attachment_signature(42, 8, q["exp"], q["sig"])


def test_attachment_expired_rejected(app):
    with app.app_context():
        q = _qs(sign_attachment_url(1, 1, expiry=-5))
        assert not verify_attachment_signature(1, 1, q["exp"], q["sig"])


def test_attachment_malformed_exp_rejected(app):
    with app.app_context():
        assert not verify_attachment_signature(1, 1, "bogus", "sig")

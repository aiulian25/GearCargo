"""Utility modules for the GearCargo application."""

import hashlib
import hmac
import time

from flask import current_app

from .security_audit import security_audit, SecurityAuditLogger

__all__ = ['security_audit', 'SecurityAuditLogger', 'sign_upload_url', 'verify_upload_signature',
           'sign_attachment_url', 'verify_attachment_signature']

# Signed URLs expire after 1 hour by default
SIGNED_URL_EXPIRY = 3600


def sign_upload_url(path, expiry=SIGNED_URL_EXPIRY):
    """Generate a signed URL for an upload path.

    Uses HMAC-SHA256 with the app SECRET_KEY to produce a short-lived
    signature that is tied to the specific file path.
    Returns the path with ?exp=<timestamp>&sig=<hex> appended.
    """
    if not path:
        return path
    exp = int(time.time()) + expiry
    secret = current_app.config['SECRET_KEY']
    message = f"{path}:{exp}".encode()
    sig = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return f"{path}?exp={exp}&sig={sig}"


def verify_upload_signature(path, exp_str, sig):
    """Verify the HMAC signature on an upload URL.

    Returns True if the signature is valid and not expired.
    """
    try:
        exp = int(exp_str)
    except (TypeError, ValueError):
        return False
    if time.time() > exp:
        return False
    secret = current_app.config['SECRET_KEY']
    message = f"{path}:{exp}".encode()
    expected = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


# ============================================================
# ATTACHMENT SIGNED URLs (S20 — replaces ?token=<JWT> in URLs)
# ============================================================

# Attachment media tokens are short-lived — 5 minutes is enough to open in a
# new tab or embed in an <img> tag.  The JWT itself is never put in the URL.
ATTACHMENT_URL_EXPIRY = 300  # seconds


def sign_attachment_url(attachment_id: int, user_id: int, expiry: int = ATTACHMENT_URL_EXPIRY) -> str:
    """Return a short-lived signed path for viewing attachment *attachment_id*.

    Produces: ``/api/attachments/<id>/view?exp=<ts>&uid=<uid>&sig=<hmac>``

    The HMAC message binds the attachment id, user id, and expiry timestamp so
    the token cannot be replayed for a different attachment or user.
    """
    exp = int(time.time()) + expiry
    secret = current_app.config['SECRET_KEY']
    message = f"attachment:{attachment_id}:{user_id}:{exp}".encode()
    sig = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return f"/api/attachments/{attachment_id}/view?exp={exp}&uid={user_id}&sig={sig}"


def verify_attachment_signature(attachment_id: int, user_id: int, exp_str, sig: str) -> bool:
    """Verify a signed attachment URL.

    Returns ``True`` iff the signature is valid, not expired, and bound to the
    claimed ``attachment_id`` / ``user_id`` pair.
    """
    try:
        exp = int(exp_str)
    except (TypeError, ValueError):
        return False
    if time.time() > exp:
        return False
    secret = current_app.config['SECRET_KEY']
    message = f"attachment:{attachment_id}:{user_id}:{exp}".encode()
    expected = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)

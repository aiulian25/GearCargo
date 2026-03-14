"""Utility modules for the GearCargo application."""

import hashlib
import hmac
import time
from urllib.parse import urlencode, urlparse, parse_qs

from flask import current_app

from .security_audit import security_audit, SecurityAuditLogger

__all__ = ['security_audit', 'SecurityAuditLogger', 'sign_upload_url', 'verify_upload_signature']

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

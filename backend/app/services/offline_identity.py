"""Non-credential identifiers used to constrain browser offline mutations.

These values cannot authenticate a request. The ordinary cookie/session checks
still run first; comparing them at the write boundary closes the cookie-change
race between the worker's identity check and its replay fetch.
"""
import hashlib
import hmac
import re

from flask import current_app


def offline_identity(user, claims):
    key = current_app.config['JWT_SECRET_KEY'].encode()
    created = user.created_at.isoformat() if user.created_at else ''
    owner = hmac.new(key, f'offline-owner-v1:{user.id}:{created}'.encode(), hashlib.sha256).hexdigest()
    # Existing sessions can participate without a migration or forced login.
    # Refresh carries this marker forward, while a fresh login mints a new one.
    generation = claims.get('offline_generation') or hmac.new(
        key, f'offline-session-v1:{claims["jti"]}'.encode(), hashlib.sha256,
    ).hexdigest()
    return {'owner_id': user.id, 'owner_key': owner, 'generation': generation}


def offline_headers_match(headers, identity):
    owner = headers.get('X-GearCargo-Offline-Owner')
    generation = headers.get('X-GearCargo-Offline-Generation')
    if owner is None and generation is None:
        return True  # Existing online/API clients keep their current contract.
    return bool(owner and generation and re.fullmatch(r'[a-f0-9]{64}', owner)
                and re.fullmatch(r'[a-f0-9]{64}', generation)
                and hmac.compare_digest(owner, identity['owner_key'])
                and hmac.compare_digest(generation, identity['generation']))

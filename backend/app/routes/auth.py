"""
GearCargo - Authentication Routes
"""

import io
import re
import json
import base64
import pyotp
import qrcode
import secrets
import hashlib
import requests
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Blueprint, request, jsonify, current_app
import jwt

from app import db, redis_client
from app.models import User, ActivityLog, BlockedIP, BlockedDevice
from app.utils.security_audit import security_audit

auth_bp = Blueprint('auth', __name__)

# Common passwords that should be rejected (top 100 most common)
COMMON_PASSWORDS = {
    'password', 'password1', 'password123', '123456', '12345678', '123456789',
    '1234567890', 'qwerty', 'qwerty123', 'abc123', 'monkey', 'master', 'dragon',
    'letmein', 'login', 'admin', 'welcome', 'welcome1', 'shadow', 'sunshine',
    'princess', 'football', 'baseball', 'iloveyou', 'trustno1', '111111',
    '123123', '654321', 'superman', 'qazwsx', 'michael', 'ashley', 'bailey',
    'passw0rd', 'password!', 'pass1234', 'test', 'test123', 'guest', 'master123',
    'changeme', 'hello', 'hello123', '000000', '666666', '888888', 'password12',
    'qwerty1', '1q2w3e4r', '1qaz2wsx', 'zaq12wsx', 'access', 'starwars',
    'charlie', 'donald', 'whatever', 'killer', 'jordan', 'jennifer', 'hunter',
    'buster', 'soccer', 'harley', 'batman', 'andrew', 'tigger', 'sunshine1',
    'secret', 'freedom', 'computer', 'pepper', 'ginger', 'joshua', 'maggie',
    'summer', 'nicole', 'chelsea', 'biteme', 'yankees', 'dallas', 'austin',
    'thunder', 'matrix', 'corvette', 'mercedes', 'lakers', 'cowboys', 'steelers',
    '1234', '12345', 'abcd1234', 'password2', 'password3', 'admin123', 'root',
    'toor', 'qwe123', 'zxcvbn', 'asdfgh', 'qwertyuiop', 'letmein123', 'gearcargo'
}

# S03: Minimum length for any NEW or changed password. Raised from 8 → 12 as a
# defence-in-depth floor (existing users are unaffected and can still log in with
# their current password; only setting/changing a password enforces this).
# Defined once here and reused by every server-side validator so the policy can
# never drift between endpoints. Keep in sync with the frontend (Register,
# ResetPassword, ForcePasswordChange, Profile) and the i18n strings.
MIN_PASSWORD_LENGTH = 12


def _normalize_host(hostname):
    """Normalize host/domain values for safe comparisons."""
    if not hostname:
        return ''

    # Keep the first value if a proxy provides a comma-separated list.
    value = hostname.split(',')[0].strip().lower()

    # Strip scheme/path if a full URL is provided by mistake.
    value = re.sub(r'^https?://', '', value)
    value = value.split('/')[0]
    return value


def _strip_port(hostname):
    """Return hostname without port when present."""
    if not hostname:
        return ''
    return hostname.split(':')[0]


def _request_host():
    """Resolve the external host from reverse-proxy aware headers."""
    forwarded_host = request.headers.get('X-Forwarded-Host')
    host = _normalize_host(forwarded_host or request.host or request.headers.get('Host', ''))
    return host


def _config_domain(key):
    """Read and normalize configured domain from app config."""
    value = current_app.config.get(key, '').strip()
    # Ignore comments and treat them as empty
    if not value or value.startswith('#'):
        return ''
    return _normalize_host(value)


def _is_host_match(request_host, configured_host):
    """Match host with or without explicit ports."""
    if not request_host or not configured_host:
        return False
    return request_host == configured_host or _strip_port(request_host) == _strip_port(configured_host)


def _is_request_on_domain(config_key):
    """Check whether current request is on a configured domain."""
    configured = _config_domain(config_key)
    if not configured:
        return False
    return _is_host_match(_request_host(), configured)


def _enforce_login_domain_policy(user):
    """Enforce admin/user login segregation by configured domains."""
    on_admin_domain = _is_request_on_domain('ADMIN_DOMAIN')
    on_user_domain = _is_request_on_domain('USER_DOMAIN')

    # If domains are not configured, skip policy enforcement.
    if not on_admin_domain and not on_user_domain:
        return None

    if on_admin_domain and not user.is_admin:
        return jsonify({'error': 'This domain is restricted to admin accounts'}), 403

    if on_user_domain and user.is_admin:
        return jsonify({'error': 'Admin accounts must login from the admin domain'}), 403

    return None


def validate_password_strength(password):
    """
    Validate password strength. Returns (is_valid, error_message, strength_score).
    Strength score: 0-100
    """
    errors = []
    score = 0
    breach_count = 0
    
    # Length checks
    if len(password) < MIN_PASSWORD_LENGTH:
        errors.append(f'Password must be at least {MIN_PASSWORD_LENGTH} characters')
    else:
        score += 20
    if len(password) >= 12:
        score += 10
    if len(password) >= 16:
        score += 10
    
    # Character type checks
    has_upper = bool(re.search(r'[A-Z]', password))
    has_lower = bool(re.search(r'[a-z]', password))
    has_digit = bool(re.search(r'\d', password))
    has_special = bool(re.search(r'[!@#$%^&*(),.?":{}|<>_\-+=\[\]\\;\'`~]', password))
    
    if has_upper:
        score += 15
    else:
        errors.append('Password should contain at least one uppercase letter')
    
    if has_lower:
        score += 15
    else:
        errors.append('Password should contain at least one lowercase letter')
    
    if has_digit:
        score += 15
    else:
        errors.append('Password should contain at least one number')
    
    if has_special:
        score += 15
    
    # Check for common passwords
    password_lower = password.lower()
    if password_lower in COMMON_PASSWORDS:
        errors.append('This password is too common. Please choose a more unique password')
        score = min(score, 20)  # Cap score for common passwords
    
    # Check for sequential characters
    sequential_patterns = ['123', '234', '345', '456', '567', '678', '789', 
                          'abc', 'bcd', 'cde', 'def', 'efg', 'qwe', 'wer', 'ert',
                          'asd', 'sdf', 'dfg', 'zxc', 'xcv', 'cvb']
    for pattern in sequential_patterns:
        if pattern in password_lower:
            score = max(0, score - 10)
            break
    
    # Check for repeated characters (e.g., 'aaa', '111')
    if re.search(r'(.)\1{2,}', password):
        score = max(0, score - 10)
    
    # Check Have I Been Pwned database for breached passwords
    breach_count = check_password_breach(password)
    if breach_count > 0:
        if breach_count > 100:
            errors.append(f'This password has been exposed in data breaches {breach_count:,} times. Choose a different password.')
            score = min(score, 10)  # Severely penalize breached passwords
        else:
            errors.append(f'This password has been found in {breach_count} data breach(es). Consider using a different password.')
            score = min(score, 30)
    
    # Determine strength level
    if score >= 70:
        strength = 'strong'
    elif score >= 50:
        strength = 'medium'
    else:
        strength = 'weak'
    
    # Only enforce critical requirements (length, not common, not breached >100 times)
    critical_errors = [e for e in errors if 'at least' in e or 'too common' in e or 'exposed in data breaches' in e]
    
    return len(critical_errors) == 0, errors, score, strength


def check_password_breach(password):
    """
    Check if password has been exposed in data breaches using Have I Been Pwned API.
    Uses k-anonymity model - only sends first 5 chars of SHA1 hash.
    Returns the number of times the password was found in breaches (0 if not found).
    """
    try:
        # SHA1 hash the password
        sha1_hash = hashlib.sha1(password.encode('utf-8')).hexdigest().upper()
        prefix = sha1_hash[:5]
        suffix = sha1_hash[5:]
        
        # Query HIBP API with only the prefix (k-anonymity)
        response = requests.get(
            f'https://api.pwnedpasswords.com/range/{prefix}',
            headers={'User-Agent': 'GearCargo-PasswordChecker/1.0'},
            timeout=3
        )
        
        if response.status_code != 200:
            # API error - fail open (don't block registration)
            current_app.logger.warning(f"HIBP API returned status {response.status_code}")
            return 0
        
        # Check if our hash suffix is in the response
        for line in response.text.splitlines():
            hash_suffix, count = line.split(':')
            if hash_suffix == suffix:
                return int(count)
        
        return 0  # Password not found in breaches
        
    except requests.exceptions.Timeout:
        current_app.logger.warning("HIBP API timeout - skipping breach check")
        return 0
    except Exception as e:
        current_app.logger.warning(f"HIBP API error: {e}")
        return 0  # Fail open on errors


def get_limiter():
    """Get rate limiter from app."""
    return current_app.extensions.get('limiter')


# ============================================================
# ACCOUNT LOCKOUT PROTECTION
# ============================================================

# Security settings
MAX_LOGIN_ATTEMPTS = 5  # Lock after 5 failed attempts
LOCKOUT_DURATION = 30 * 60  # 30 minutes lockout
FAILED_LOGIN_WINDOW = 15 * 60  # Track failures within 15 minutes


def get_failed_login_key(email):
    """Get Redis key for tracking failed logins."""
    return f'failed_login:{email.lower()}'


def get_lockout_key(email):
    """Get Redis key for account lockout."""
    return f'lockout:{email.lower()}'


def _db_is_account_locked(email):
    """DB-backed lockout check used when Redis is unavailable."""
    try:
        user = User.query.filter_by(email=email.lower()).first()
        if user and user.locked_until:
            # Naive UTC: locked_until is read back tz-naive from the DB, so
            # compare against naive now (mixing aware/naive raises TypeError).
            now = _utcnow_naive()
            if user.locked_until > now:
                remaining = int((user.locked_until - now).total_seconds())
                return True, remaining
            # Lock expired — clear it
            user.locked_until = None
            user.failed_login_attempts = 0
            db.session.commit()
    except Exception as e:
        current_app.logger.error(f"[Security] DB lockout check failed: {e}")
        db.session.rollback()
    return False, 0


def _db_record_failed_login(email):
    """DB-backed failed login recording used when Redis is unavailable."""
    try:
        user = User.query.filter_by(email=email.lower()).first()
        if not user:
            return False, 0, 0

        # Naive UTC throughout so the value we store matches what we read back
        # for comparison (the column is tz-naive).
        now = _utcnow_naive()
        # If a previous lock expired, reset the counter first
        if user.locked_until and user.locked_until <= now:
            user.locked_until = None
            user.failed_login_attempts = 0

        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        attempts = user.failed_login_attempts

        if attempts >= MAX_LOGIN_ATTEMPTS:
            user.locked_until = now + timedelta(seconds=LOCKOUT_DURATION)
            user.failed_login_attempts = 0
            db.session.commit()
            current_app.logger.warning(
                '[Security] DB-backed account lock triggered after %d failed attempts: %s '
                '(Redis unavailable — lockout is active but NOT cross-worker)',
                attempts, email
            )
            return True, LOCKOUT_DURATION, attempts

        db.session.commit()
        return False, 0, attempts
    except Exception as e:
        current_app.logger.error(f"[Security] DB failed-login recording failed: {e}")
        db.session.rollback()
        return False, 0, 0


def is_account_locked(email):
    """Check if account is locked due to too many failed attempts."""
    if redis_client:
        try:
            lockout_key = get_lockout_key(email)
            lockout_until = redis_client.get(lockout_key)
            if lockout_until:
                remaining = redis_client.ttl(lockout_key)
                return True, remaining
            return False, 0
        except Exception as e:
            current_app.logger.error(f"Failed to check account lockout via Redis: {e}")
            # Redis error — fall through to DB fallback

    # Redis unavailable or errored: use DB-backed fallback
    current_app.logger.warning('[Security] Redis unavailable for lockout check — using DB fallback')
    return _db_is_account_locked(email)


def record_failed_login(email):
    """Record a failed login attempt. Returns (is_locked, remaining_time, attempt_count)."""
    if redis_client:
        try:
            failed_key = get_failed_login_key(email)

            # Increment failed attempts
            attempts = redis_client.incr(failed_key)

            # Set expiry on first attempt
            if attempts == 1:
                redis_client.expire(failed_key, FAILED_LOGIN_WINDOW)

            # Check if should lock
            if attempts >= MAX_LOGIN_ATTEMPTS:
                lockout_key = get_lockout_key(email)
                redis_client.setex(lockout_key, LOCKOUT_DURATION, 'locked')
                redis_client.delete(failed_key)  # Reset counter

                # Log the lockout
                current_app.logger.warning(f"Account locked due to {attempts} failed attempts: {email}")

                return True, LOCKOUT_DURATION, attempts

            return False, 0, attempts
        except Exception as e:
            current_app.logger.error(f"Failed to record login attempt via Redis: {e}")
            # Redis error — fall through to DB fallback

    # Redis unavailable or errored: use DB-backed fallback
    current_app.logger.warning('[Security] Redis unavailable for failed-login recording — using DB fallback')
    return _db_record_failed_login(email)


def clear_failed_logins(email):
    """Clear failed login counter on successful login."""
    if redis_client:
        try:
            redis_client.delete(get_failed_login_key(email))
        except Exception as e:
            current_app.logger.error(f"Failed to clear login attempts from Redis: {e}")

    # Always clear DB counter on successful login (belt-and-suspenders)
    try:
        user = User.query.filter_by(email=email.lower()).first()
        if user and (user.failed_login_attempts or user.locked_until):
            user.failed_login_attempts = 0
            user.locked_until = None
            db.session.commit()
    except Exception as e:
        current_app.logger.error(f"Failed to clear login attempts from DB: {e}")
        db.session.rollback()


# ============================================================
# IP GEOLOCATION FOR SUSPICIOUS LOGIN DETECTION
# ============================================================

def get_real_client_ip():
    """
    Return the real client IP address as determined by werkzeug's ProxyFix.

    S11 fix: the previous implementation read X-Forwarded-For / X-Real-IP
    directly from the request, making it trivially spoofable — any client
    can inject arbitrary values into those headers. The correct approach is
    to configure ProxyFix in create_app() (done in __init__.py) with
    x_for=TRUSTED_PROXY_COUNT and then read request.remote_addr here.
    ProxyFix rewrites remote_addr to the nth-from-right hop in XFF, so only
    the trusted-proxy chain can influence the value; clients cannot.
    """
    # ProxyFix has already set request.remote_addr to the real client IP.
    # Calling .remote_addr directly is both safe and sufficient after S11 fix.
    return request.remote_addr or 'Unknown'


def get_ip_location(ip_address):
    """
    Get location info for an IP address using the local MaxMind GeoLite2 database.

    S10 fix: the previous implementation made a cleartext HTTP request to
    ip-api.com on every login, exposing the user's IP to a third party and to
    any MITM observer. This version performs an entirely local lookup against
    the MMDB file at GEOIP_DB_PATH — no external network call is made.

    Returns a dict with country/city/lat/lon, or None when the database is not
    configured (GEOIP_DB_PATH unset) or the IP is not found. When None is returned
    suspicious-location detection is silently disabled — login continues normally.
    """
    if not ip_address or ip_address in ('127.0.0.1', 'localhost', '::1'):
        return {'country': 'Local', 'country_code': 'LOCAL', 'city': 'Local',
                'lat': 0, 'lon': 0, 'isp': 'Local', 'ip': ip_address}

    # Reader is opened once at startup in create_app() and stored on the app object.
    reader = getattr(current_app._get_current_object(), 'geoip_reader', None)
    if reader is None:
        # GEOIP_DB_PATH not configured — feature gracefully disabled.
        return None

    try:
        import geoip2.errors
        response = reader.city(ip_address)
        return {
            'country': response.country.name or 'Unknown',
            'country_code': response.country.iso_code or 'XX',
            'city': response.city.name or 'Unknown',
            'lat': response.location.latitude or 0,
            'lon': response.location.longitude or 0,
            'isp': None,  # GeoLite2-City doesn't include ISP/org data
            'ip': ip_address,
        }
    except geoip2.errors.AddressNotFoundError:
        return None  # Private/reserved IPs not in the database — normal
    except Exception as e:
        current_app.logger.warning(f'GeoIP2 lookup failed for {ip_address}: {e}')
        return None


def get_known_locations_key(user_id):
    """Get Redis key for tracking known login locations."""
    return f'known_locations:{user_id}'


def get_user_known_locations(user_id):
    """Get list of countries/cities the user has logged in from before."""
    if not redis_client:
        return set()
    
    try:
        locations_key = get_known_locations_key(user_id)
        locations = redis_client.smembers(locations_key)
        if locations:
            return {loc.decode() if isinstance(loc, bytes) else loc for loc in locations}
        return set()
    except Exception as e:
        current_app.logger.error(f"Failed to get known locations: {e}")
        return set()


def register_user_location(user_id, country_code):
    """Register a country as a known login location for the user."""
    if not redis_client or not country_code:
        return
    
    try:
        locations_key = get_known_locations_key(user_id)
        redis_client.sadd(locations_key, country_code)
        # Keep location history for 1 year
        redis_client.expire(locations_key, 365 * 24 * 60 * 60)
    except Exception as e:
        current_app.logger.error(f"Failed to register user location: {e}")


def is_suspicious_location(user_id, current_location):
    """
    Check if login is from a suspicious (new) location.
    Returns (is_suspicious, location_info, known_locations).
    """
    if not current_location:
        return False, None, set()
    
    country_code = current_location.get('country_code', 'XX')
    known_locations = get_user_known_locations(user_id)
    
    # First login - not suspicious, just new
    if not known_locations:
        return False, current_location, known_locations
    
    # Check if this country is new
    is_new_location = country_code not in known_locations and country_code != 'LOCAL'
    
    return is_new_location, current_location, known_locations


def get_known_devices_key(user_id):
    """Get Redis key for tracking known devices."""
    return f'known_devices:{user_id}'


def get_device_fingerprint():
    """Generate a *stable* device fingerprint for new-device login alerts (S04).

    IMPORTANT: this is a heuristic for "have we seen this browser before?"
    notification signal only — it is NOT an authentication factor and must never
    gate access (it is trivially spoofable via headers).

    The previous implementation hashed the raw User-Agent, so every browser
    auto-update (which only bumps the version number) produced a brand-new
    fingerprint and a false "new device" alert. We instead hash a NORMALISED
    signature built from the browser family, OS family, device type and the
    primary Accept-Language — all of which are stable across version bumps —
    so genuine new-device alerts are not drowned out by update noise.

    Returns (fingerprint, user_agent). The full user_agent is still returned for
    display/audit purposes.
    """
    user_agent = request.headers.get('User-Agent', 'unknown')

    # Parse to families WITHOUT version numbers (parse_user_agent extracts them
    # but we deliberately ignore *_version fields here for stability).
    info = parse_user_agent(user_agent) if user_agent else {}

    accept_language = request.headers.get('Accept-Language', '')
    primary_lang = accept_language.split(',')[0].strip().lower() if accept_language else ''

    signature = '|'.join([
        info.get('device_type') or 'unknown',
        info.get('browser') or 'unknown',
        info.get('os') or 'unknown',
        primary_lang or 'unknown',
    ])
    fingerprint = hashlib.sha256(signature.encode('utf-8')).hexdigest()[:16]
    return fingerprint, user_agent


def is_new_device(user_id):
    """Check if this is a new device for the user."""
    if not redis_client:
        return False, None
    
    try:
        fingerprint, user_agent = get_device_fingerprint()
        devices_key = get_known_devices_key(user_id)
        
        # Get known devices
        known_devices = redis_client.smembers(devices_key)
        if known_devices:
            known_devices = {d.decode() if isinstance(d, bytes) else d for d in known_devices}
        else:
            known_devices = set()
        
        is_new = fingerprint not in known_devices
        
        # Get real client IP (not Docker/proxy IP)
        real_ip = get_real_client_ip()
        
        # Get location info for the email
        location_info = get_ip_location(real_ip)
        
        return is_new, {
            'fingerprint': fingerprint,
            'user_agent': user_agent[:200],
            'ip': real_ip,
            'location': location_info
        }
    except Exception as e:
        current_app.logger.error(f"Failed to check new device: {e}")
        return False, None


def register_device(user_id):
    """Register current device as known for the user."""
    if not redis_client:
        return
    
    try:
        fingerprint, _ = get_device_fingerprint()
        devices_key = get_known_devices_key(user_id)
        
        # Add device to known devices set
        redis_client.sadd(devices_key, fingerprint)
        
        # Keep device fingerprints for 90 days
        redis_client.expire(devices_key, 90 * 24 * 60 * 60)
    except Exception as e:
        current_app.logger.error(f"Failed to register device: {e}")


# ============================================================
# DB-BACKED SESSION FALLBACK (S01 — fail CLOSED when Redis is down)
# ============================================================
#
# Redis is the fast path for all session state. These helpers mirror every
# session into the `user_sessions` table so that when Redis is unavailable the
# auth layer validates against a durable store instead of failing OPEN. The
# previous behaviour accepted any well-signed token whenever Redis was down,
# silently disabling single-device enforcement, the 48h absolute-expiry wall,
# and logout/blacklist revocation. This mirrors the existing DB-backed
# account-lockout fallback pattern (_db_is_account_locked, above).

_REDIS_DEGRADED_LOG_INTERVAL = 300  # seconds — throttle "Redis down" warnings
_redis_degraded_last_logged = 0.0


def _utcnow_naive():
    """Naive UTC 'now' — matches the naive-UTC columns in user_sessions so
    comparisons never mix aware/naive datetimes."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _to_naive_utc(dt):
    """Coerce an (aware or naive) datetime to naive UTC for DB storage/compare."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _warn_redis_degraded(context):
    """Emit a throttled WARNING so a Redis outage is loudly visible in the logs
    (the 'loud degraded state' from IMPROVEMENTS.md §1.1) without flooding them
    on every request."""
    global _redis_degraded_last_logged
    import time
    now = time.time()
    if now - _redis_degraded_last_logged >= _REDIS_DEGRADED_LOG_INTERVAL:
        _redis_degraded_last_logged = now
        current_app.logger.warning(
            '[Security] Redis unavailable — using DB session fallback (%s). '
            'Single-device enforcement, the 48h session wall and logout '
            'revocation are now served from the user_sessions table.',
            context,
        )


def _db_create_session(user_id, jti, absolute_expires_at):
    """Upsert a durable session row. Best-effort — never raises (login must not
    fail because the mirror write failed)."""
    from app.models import UserSession
    try:
        abs_naive = _to_naive_utc(absolute_expires_at)
        existing = UserSession.query.filter_by(jti=jti).first()
        if existing:
            existing.user_id = user_id
            existing.absolute_expires_at = abs_naive
            existing.revoked = False
            existing.revoked_at = None
        else:
            db.session.add(UserSession(
                user_id=user_id,
                jti=jti,
                absolute_expires_at=abs_naive,
                user_agent=(request.headers.get('User-Agent', 'unknown') or 'unknown')[:255],
                ip=(request.remote_addr or 'unknown')[:45],
            ))
        db.session.commit()
        _db_prune_user_sessions(user_id)
    except Exception as e:
        current_app.logger.error(f'[Security] DB session create failed for user {user_id}: {e}')
        db.session.rollback()


def _db_validate_session(user_id, jti):
    """Return True only if a non-revoked, non-expired row exists. Fails CLOSED
    on a missing row or any DB error — we never accept a session we cannot
    positively verify."""
    from app.models import UserSession
    try:
        row = UserSession.query.filter_by(user_id=user_id, jti=jti).first()
        if not row or row.revoked:
            return False
        if row.absolute_expires_at and row.absolute_expires_at <= _utcnow_naive():
            return False
        return True
    except Exception as e:
        current_app.logger.error(f'[Security] DB session validation failed for user {user_id}: {e}')
        db.session.rollback()
        return False


def _db_get_session_data(user_id, jti):
    """Return a dict mirroring the Redis session payload (or None). Used by the
    refresh path to read absolute_expires_at when Redis is down."""
    from app.models import UserSession
    try:
        row = UserSession.query.filter_by(user_id=user_id, jti=jti).first()
        if not row or row.revoked:
            return None
        abs_dt = row.absolute_expires_at
        created = row.created_at
        return {
            'created_at': created.replace(tzinfo=timezone.utc).isoformat() if created else None,
            'absolute_expires_at': abs_dt.replace(tzinfo=timezone.utc).isoformat() if abs_dt else None,
            'user_agent': row.user_agent,
            'ip': row.ip,
        }
    except Exception as e:
        current_app.logger.error(f'[Security] DB session fetch failed for user {user_id}: {e}')
        db.session.rollback()
        return None


def _db_revoke_session(user_id, jti):
    """Mark a single session revoked (logout)."""
    from app.models import UserSession
    try:
        row = UserSession.query.filter_by(user_id=user_id, jti=jti).first()
        if row and not row.revoked:
            row.revoked = True
            row.revoked_at = _utcnow_naive()
            db.session.commit()
    except Exception as e:
        current_app.logger.error(f'[Security] DB session revoke failed for user {user_id}: {e}')
        db.session.rollback()


def _db_revoke_all_sessions(user_id):
    """Mark every active session for a user revoked (single-device enforcement /
    forced logout-everywhere)."""
    from app.models import UserSession
    try:
        UserSession.query.filter_by(user_id=user_id, revoked=False).update(
            {'revoked': True, 'revoked_at': _utcnow_naive()},
            synchronize_session=False,
        )
        db.session.commit()
    except Exception as e:
        current_app.logger.error(f'[Security] DB bulk session revoke failed for user {user_id}: {e}')
        db.session.rollback()


def _db_prune_user_sessions(user_id):
    """Opportunistically delete this user's expired or revoked rows so the table
    stays bounded even if the daily cleanup job is not running. Best-effort;
    absence of a row is treated as 'invalid' by _db_validate_session, so deleting
    revoked rows does not weaken logout revocation."""
    from app.models import UserSession
    try:
        UserSession.query.filter(
            UserSession.user_id == user_id,
            db.or_(
                UserSession.absolute_expires_at <= _utcnow_naive(),
                UserSession.revoked.is_(True),
            ),
        ).delete(synchronize_session=False)
        db.session.commit()
    except Exception:
        db.session.rollback()


def invalidate_user_sessions(user_id):
    """Invalidate all sessions for a user (Redis + durable DB mirror)."""
    if redis_client:
        try:
            # Get all session keys for this user
            session_keys = redis_client.keys(f'session:{user_id}:*')
            if session_keys:
                redis_client.delete(*session_keys)
            current_app.logger.info(f"Invalidated {len(session_keys)} sessions for user {user_id}")
        except Exception as e:
            current_app.logger.error(f"Failed to invalidate sessions: {e}")

    # S01: always revoke the durable DB mirror so single-device enforcement and
    # logout hold even if Redis is down now or goes down later.
    _db_revoke_all_sessions(user_id)


def create_session(user_id, token_jti, absolute_expires_at=None):
    """Create a new session in Redis and the durable DB mirror (S01).

    absolute_expires_at: timezone-aware UTC datetime for the hard session wall
    (48 h from initial login, non-sliding).  When None (initial login) it
    defaults to 48 hours from now.  The Redis TTL is set to the remaining
    seconds until that wall so the key self-destructs at the right moment.
    """
    now = datetime.now(timezone.utc)
    if absolute_expires_at is None:
        # Initial login — derive from config TTL (default 48 h)
        refresh_expires = current_app.config.get('JWT_REFRESH_TOKEN_EXPIRES')
        if isinstance(refresh_expires, timedelta):
            absolute_expires_at = now + refresh_expires
        else:
            absolute_expires_at = now + timedelta(hours=48)

    # Redis fast path.
    if redis_client:
        try:
            # TTL = remaining seconds until the absolute wall
            ttl = max(1, int((absolute_expires_at - now).total_seconds()))

            session_key = f'session:{user_id}:{token_jti}'
            session_data = {
                'created_at': now.isoformat(),
                'absolute_expires_at': absolute_expires_at.isoformat(),
                'user_agent': request.headers.get('User-Agent', 'unknown')[:200],
                'ip': request.remote_addr or 'unknown',
            }
            redis_client.setex(session_key, ttl, json.dumps(session_data))
            current_app.logger.info(
                f"Created session {token_jti} for user {user_id}, "
                f"absolute expiry: {absolute_expires_at.isoformat()}"
            )
        except Exception as e:
            current_app.logger.error(f"Failed to create session in Redis: {e}")

    # S01: durable DB mirror — written unconditionally so the fallback path can
    # validate this exact session (and enforce its 48h wall) if Redis is, or
    # later becomes, unavailable.
    _db_create_session(user_id, token_jti, absolute_expires_at)
    return True


def validate_session(user_id, token_jti):
    """Validate that a session exists and is active.

    S01: Redis is the fast path. When Redis is reachable its answer is
    authoritative — a missing key means the session expired or was revoked, so
    we reject. When Redis is unavailable or errors we no longer fail OPEN
    (the old behaviour returned True); instead we consult the durable
    user_sessions table and fail CLOSED if no valid, non-revoked, non-expired
    row exists.
    """
    if redis_client:
        try:
            session_key = f'session:{user_id}:{token_jti}'
            exists = bool(redis_client.exists(session_key))
            if not exists:
                # Redis is healthy and the key is gone → genuinely expired/revoked.
                current_app.logger.warning(f"Session {token_jti} not found for user {user_id}")
            return exists
        except Exception as e:
            current_app.logger.error(f"Redis session validation failed: {e}")
            _warn_redis_degraded('validate_session')
            return _db_validate_session(user_id, token_jti)

    # No Redis client at all → durable DB fallback (fail closed).
    _warn_redis_degraded('validate_session (no redis_client)')
    return _db_validate_session(user_id, token_jti)


def get_session_data(user_id, token_jti):
    """Retrieve and parse session data from Redis. Returns dict or None.

    Sessions are stored as JSON (see the ``json.dumps`` write path). Any value
    that is not valid JSON is treated as corrupt/untrusted and ignored — control
    falls through to the durable DB session mirror below, so a bad blob forces a
    safe re-login rather than being trusted.
    """
    if redis_client:
        try:
            session_key = f'session:{user_id}:{token_jti}'
            raw = redis_client.get(session_key)
            if raw:
                if isinstance(raw, bytes):
                    raw = raw.decode('utf-8', errors='replace')
                try:
                    return json.loads(raw)
                except (json.JSONDecodeError, ValueError):
                    # SEC-04: never eval Redis contents. Legacy Python-dict-string
                    # sessions (pre-JSON) are long expired (TTL + 48h absolute
                    # wall), so a non-JSON value is corrupt — ignore it and fall
                    # through to the DB mirror below (→ re-login if none found).
                    current_app.logger.warning(
                        "Ignoring non-JSON session blob for jti %s; using DB mirror.",
                        token_jti,
                    )
            # Key missing while Redis is healthy — fall through to the DB mirror.
            # In practice validate_session has already rejected this case before
            # we get here, so this only matters during a Redis outage.
        except Exception as e:
            current_app.logger.error(f"Failed to get session data for {token_jti}: {e}")
            _warn_redis_degraded('get_session_data')

    # S01: DB fallback so the 48h absolute-expiry wall is still enforced on
    # refresh when Redis is unavailable.
    return _db_get_session_data(user_id, token_jti)


# ============================================================
# HTTPONLY COOKIE HELPERS (S05 — JWT tokens moved out of localStorage)
# ============================================================

def _auth_cookie_settings():
    """Return shared kwargs for auth token cookies.

    SEC-03: ``httponly`` and ``samesite`` are hardcoded BY DESIGN and are NOT
    operator-configurable — do not wire them to an env var / config key. A
    private PWA has no legitimate cross-site auth-cookie use, so SameSite=Strict
    is the strongest CSRF posture and must never be weakened to Lax/None. Only
    ``secure`` is env-driven (JWT_COOKIE_SECURE) so HTTP-only local/dev setups can
    still log in while production stays HTTPS-only.
    """
    return dict(
        httponly=True,
        secure=bool(current_app.config.get('JWT_COOKIE_SECURE', False)),
        # SameSite=Strict: cookie never sent on cross-site requests — strongest
        # CSRF protection for a private PWA with no cross-site form submissions.
        samesite='Strict',
    )


def _set_auth_cookies(response, access_token, refresh_token):
    """Attach JWT tokens as httpOnly SameSite=Strict cookies (S05).

    access_token  — short-lived; scoped to all API paths.
    refresh_token — long-lived; scoped to /api/auth/refresh only, so it is
                    never accidentally sent on regular API calls.
    """
    settings = _auth_cookie_settings()

    access_expires = current_app.config.get('JWT_ACCESS_TOKEN_EXPIRES')
    access_max_age = int(access_expires.total_seconds()) if isinstance(access_expires, timedelta) else 3600

    refresh_expires = current_app.config.get('JWT_REFRESH_TOKEN_EXPIRES')
    refresh_max_age = int(refresh_expires.total_seconds()) if isinstance(refresh_expires, timedelta) else 30 * 24 * 3600

    response.set_cookie('access_token', access_token, max_age=access_max_age, path='/', **settings)
    response.set_cookie('refresh_token', refresh_token, max_age=refresh_max_age,
                        path='/api/auth/refresh', **settings)
    return response


def _clear_auth_cookies(response):
    """Expire both auth cookies (used on logout)."""
    settings = _auth_cookie_settings()
    response.set_cookie('access_token', '', max_age=0, path='/', **settings)
    response.set_cookie('refresh_token', '', max_age=0, path='/api/auth/refresh', **settings)
    return response


# ============================================================
# TOTP SECRET ENCRYPTION HELPERS (S06 — 2FA seed moved out of plaintext)
# ============================================================

def _get_totp_secret(user) -> str:
    """Return the plaintext TOTP base32 seed for *user*, decrypting from DB.

    Graceful plaintext fallback: rows written before S06 have a raw base32
    string.  Those rows cannot be decrypted (Fernet returns ''), so we log a
    warning and return the raw value.  The secret is automatically re-encrypted
    next time the user regenerates their 2FA or disables/re-enables it.
    """
    raw = user.two_factor_secret
    if not raw:
        return ''
    try:
        from app.utils.encryption import decrypt_field
        decrypted = decrypt_field(raw)
        if decrypted:
            return decrypted
        # decrypt_field returned '' — Fernet rejected the value: legacy plaintext row.
        current_app.logger.warning(
            '[Security] TOTP secret for user %s could not be decrypted (S06). '
            'Treating as legacy plaintext; will encrypt on next 2FA write.',
            user.id
        )
        return raw
    except Exception as exc:
        current_app.logger.warning(
            '[Security] TOTP secret decryption raised %s for user %s — using raw value.',
            type(exc).__name__, user.id
        )
        return raw


def _set_totp_secret(user, plaintext_secret: str) -> None:
    """Encrypt *plaintext_secret* and store in user.two_factor_secret (S06)."""
    if not plaintext_secret:
        user.two_factor_secret = None
        return
    from app.utils.encryption import encrypt_field
    user.two_factor_secret = encrypt_field(plaintext_secret)


# ============================================================
# EMAIL OTP SECRET ENCRYPTION HELPERS (S15 — email 2FA seed moved out of plaintext)
# ============================================================

def _get_email_otp_secret(user) -> str:
    """Return the plaintext email-OTP base32 seed for *user*, decrypting from DB.

    S15 fix: user.email_otp_secret was a raw String(32) column identical to
    the pre-S06 two_factor_secret column.  It is now encrypted with Fernet
    (AES-256-GCM) via encrypt_field().

    Graceful plaintext fallback: rows written before S15 have a raw base32
    string.  Those rows cannot be decrypted (decrypt_field returns ''), so we
    log a WARNING and return the raw value.  The secret is automatically
    re-encrypted the next time any email-OTP code path calls
    _set_email_otp_secret().
    """
    raw = user.email_otp_secret
    if not raw:
        return ''
    try:
        from app.utils.encryption import decrypt_field
        decrypted = decrypt_field(raw)
        if decrypted:
            return decrypted
        # decrypt_field returned '' — Fernet rejected the value: legacy plaintext row.
        current_app.logger.warning(
            '[Security] Email OTP secret for user %s could not be decrypted (S15). '
            'Treating as legacy plaintext; will encrypt on next email-OTP write.',
            user.id
        )
        return raw
    except Exception as exc:
        current_app.logger.warning(
            '[Security] Email OTP secret decryption raised %s for user %s — using raw value.',
            type(exc).__name__, user.id
        )
        return raw


def _set_email_otp_secret(user, plaintext_secret: str) -> None:
    """Encrypt *plaintext_secret* and store in user.email_otp_secret (S15)."""
    if not plaintext_secret:
        user.email_otp_secret = None
        return
    from app.utils.encryption import encrypt_field
    user.email_otp_secret = encrypt_field(plaintext_secret)


def token_required(f):
    """Decorator to require a valid JWT access token.

    Token lookup order (first match wins):
      1. httpOnly cookie ``access_token`` (browser clients — S05).
      2. ``Authorization: Bearer <token>`` header (API / non-browser clients).
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None

        # 1. httpOnly cookie (browser PWA clients)
        token = request.cookies.get('access_token')

        # 2. Authorization header fallback (API clients, widget integrations)
        if not token and 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                token = auth_header.split(' ')[1]
            except IndexError:
                return jsonify({'error': 'Invalid token format'}), 401

        if not token:
            return jsonify({'error': 'Token is missing'}), 401

        # Check if token is blacklisted
        if redis_client and redis_client.get(f'blacklist:{token}'):
            return jsonify({'error': 'Token has been revoked'}), 401
        
        try:
            data = jwt.decode(
                token,
                current_app.config['JWT_SECRET_KEY'],
                algorithms=['HS256']
            )
            current_user = User.query.get(data['user_id'])
            
            if not current_user:
                return jsonify({'error': 'User not found'}), 401
            
            if not current_user.is_active:
                return jsonify({'error': 'Account is disabled'}), 401
            
            # Validate session exists (single device enforcement)
            token_jti = data.get('jti')
            if not token_jti:
                # Old tokens without jti must re-login for security
                return jsonify({'error': 'Session invalid. Please login again.', 'code': 'SESSION_INVALID'}), 401
            
            if not validate_session(current_user.id, token_jti):
                return jsonify({'error': 'Session expired. You may have logged in from another device.', 'code': 'SESSION_EXPIRED'}), 401
            
            # Enforce domain policy on every request
            domain_policy_error = _enforce_login_domain_policy(current_user)
            if domain_policy_error:
                return domain_policy_error
                
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
        
        return f(current_user, *args, **kwargs)
    
    return decorated


def token_required_query_param(f):
    """
    Decorator for endpoints that need to accept tokens via query parameter.
    Only for GET requests (e.g., viewing attachments in <img> or <iframe>).

    Token lookup order:
      1. httpOnly cookie ``access_token`` (browser clients — S05).
      2. ``Authorization: Bearer <token>`` header.
      3. HMAC-signed media URL (``?exp=&uid=&sig=`` — S20, replaces JWT query param).
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None

        # 1. httpOnly cookie
        token = request.cookies.get('access_token')

        # 2. Authorization header
        if not token and 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                token = auth_header.split(' ')[1]
            except IndexError:
                pass

        # 3. HMAC-signed media URL (S20: replaces ?token=<JWT>; no credential in URL)
        if not token and request.method == 'GET':
            exp = request.args.get('exp', '')
            uid = request.args.get('uid', '')
            sig = request.args.get('sig', '')
            if exp and uid and sig:
                from app.utils import verify_attachment_signature
                # Derive attachment_id from the URL route kwargs
                attachment_id = kwargs.get('attachment_id')
                try:
                    uid_int = int(uid)
                except (TypeError, ValueError):
                    return jsonify({'error': 'Forbidden or link expired'}), 403
                if attachment_id and verify_attachment_signature(attachment_id, uid_int, exp, sig):
                    signed_user = User.query.get(uid_int)
                    if signed_user and signed_user.is_active:
                        return f(signed_user, *args, **kwargs)
                return jsonify({'error': 'Forbidden or link expired'}), 403
        
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
        
        # Check if token is blacklisted
        if redis_client and redis_client.get(f'blacklist:{token}'):
            return jsonify({'error': 'Token has been revoked'}), 401
        
        try:
            data = jwt.decode(
                token,
                current_app.config['JWT_SECRET_KEY'],
                algorithms=['HS256']
            )
            current_user = User.query.get(data['user_id'])
            
            if not current_user:
                return jsonify({'error': 'User not found'}), 401
            
            if not current_user.is_active:
                return jsonify({'error': 'Account is disabled'}), 401
            
            # Validate session exists (single device enforcement)
            token_jti = data.get('jti')
            if not token_jti:
                return jsonify({'error': 'Session invalid. Please login again.', 'code': 'SESSION_INVALID'}), 401
            
            if not validate_session(current_user.id, token_jti):
                return jsonify({'error': 'Session expired. You may have logged in from another device.', 'code': 'SESSION_EXPIRED'}), 401
            
            # Enforce domain policy on every request
            domain_policy_error = _enforce_login_domain_policy(current_user)
            if domain_policy_error:
                return domain_policy_error
                
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
        
        return f(current_user, *args, **kwargs)
    
    return decorated




def admin_required(f):
    """Decorator to require admin privileges."""
    @wraps(f)
    @token_required
    def decorated(current_user, *args, **kwargs):
        if not current_user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        
        # Additional domain check: admin routes should only be accessible on admin domain
        # This is redundant with token_required but adds defense in depth
        admin_domain = _config_domain('ADMIN_DOMAIN')
        if admin_domain and not _is_request_on_domain('ADMIN_DOMAIN'):
            return jsonify({'error': 'Admin routes are only accessible from the admin domain'}), 403
        
        return f(current_user, *args, **kwargs)
    return decorated


def generate_tokens(user, invalidate_existing=True, absolute_expires_at=None):
    """Generate access and refresh tokens with session tracking.

    absolute_expires_at: when provided (refresh path) the new session inherits
    the original login's absolute wall so it cannot be refreshed past 48 h.
    """
    # Generate unique session ID (JTI - JWT ID)
    token_jti = secrets.token_urlsafe(16)
    
    # Invalidate existing sessions if max_sessions is 1 (default)
    max_sessions = getattr(user, 'max_sessions', 1) or 1
    if invalidate_existing and max_sessions == 1:
        invalidate_user_sessions(user.id)
    
    # Get token expiry from config (already timedelta objects)
    access_expires = current_app.config.get('JWT_ACCESS_TOKEN_EXPIRES')
    if isinstance(access_expires, timedelta):
        access_exp = datetime.now(timezone.utc) + access_expires
    else:
        access_exp = datetime.now(timezone.utc) + timedelta(hours=1)
    
    refresh_expires = current_app.config.get('JWT_REFRESH_TOKEN_EXPIRES')
    if isinstance(refresh_expires, timedelta):
        refresh_exp = datetime.now(timezone.utc) + refresh_expires
    else:
        refresh_exp = datetime.now(timezone.utc) + timedelta(days=30)
    
    access_token = jwt.encode(
        {
            'user_id': user.id,
            'email': user.email,
            'is_admin': user.is_admin,
            'jti': token_jti,  # Session identifier
            'exp': access_exp
        },
        current_app.config['JWT_SECRET_KEY'],
        algorithm='HS256'
    )
    
    refresh_token = jwt.encode(
        {
            'user_id': user.id,
            'type': 'refresh',
            'jti': token_jti,  # Same session identifier
            'exp': refresh_exp
        },
        current_app.config['JWT_SECRET_KEY'],
        algorithm='HS256'
    )
    
    # Create session in Redis, propagating the absolute expiry from the
    # original login (non-sliding 48 h enforcement).
    create_session(user.id, token_jti, absolute_expires_at=absolute_expires_at)
    
    return access_token, refresh_token


@auth_bp.route('/register', methods=['POST'])
def register():
    """Register a new user."""
    # Note: rate limiting is applied in create_app() via limiter.limit() on this
    # view function ('5 per hour; 20 per day' per IP). Flask-Limiter's before_request
    # hook enforces it before this function runs — no manual check needed here.

    data = request.get_json()
    
    # Validate required fields
    required = ['email', 'password']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400
    
    # Public signup is closed once an admin exists.
    if User.query.filter_by(is_admin=True).first():
        return jsonify({'error': 'Public signup is disabled. Ask an admin to create your account.'}), 403

    # Initial bootstrap signup can only happen from admin domain when configured.
    if _config_domain('ADMIN_DOMAIN') and not _is_request_on_domain('ADMIN_DOMAIN'):
        return jsonify({'error': 'Initial registration is only allowed on the admin domain'}), 403

    # Explicitly block registration from user domain when configured.
    if _is_request_on_domain('USER_DOMAIN'):
        return jsonify({'error': 'Registration is not allowed on the user domain'}), 403

    email = data['email'].strip().lower()
    password = data['password']

    # S03: Enforce the FULL server-side password policy (length / common /
    # breached) — not just a length check. This runs BEFORE any account-existence
    # lookup so password feedback never depends on whether the email exists.
    is_valid, pw_errors, pw_score, pw_strength = validate_password_strength(password)
    if not is_valid:
        return jsonify({
            'error': pw_errors[0] if pw_errors else 'Password is too weak',
            'password_errors': pw_errors,
            'strength_score': pw_score,
            'strength': pw_strength,
        }), 400

    # S03: Account-enumeration hardening.
    # In production this branch is effectively unreachable: public signup is
    # closed once an admin exists (the 403 above), so registration is only open
    # during first-run bootstrap, when there are no accounts to enumerate. As
    # defence-in-depth we still equalise response timing between the
    # "already exists" and "created" paths by burning an equivalent bcrypt cost,
    # so an attacker cannot distinguish the two by latency.
    if User.query.filter_by(email=email).first():
        try:
            from app import bcrypt as _bcrypt
            from app.models.user import _prehash_password
            _bcrypt.generate_password_hash(_prehash_password(password))
        except Exception:
            pass
        return jsonify({'error': 'Email already registered'}), 409

    # Parse name if provided
    first_name = data.get('first_name', '')
    last_name = data.get('last_name', '')
    if data.get('name') and not first_name:
        # Split full name into first/last
        name_parts = data['name'].split(' ', 1)
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else ''
    
    # Check if this is the first user (make them admin)
    # SECURITY: Only the first user in the system can become admin through self-registration
    # After first admin exists, new admins can ONLY be created by existing admins
    is_first_user = User.query.count() == 0
    
    # Create user - SECURITY: is_admin is NEVER taken from request data
    # It's only True for the very first user, or when created by an admin via /admin/users
    user = User(
        email=email,
        username=data.get('username', email.split('@')[0]),
        first_name=first_name,
        last_name=last_name,
        language=data.get('language', 'en'),
        timezone=data.get('timezone', 'UTC'),
        is_admin=is_first_user,  # ONLY first user becomes admin - this is NOT from request data
    )
    user.set_password(password)
    
    db.session.add(user)
    db.session.commit()
    
    # Log registration
    ActivityLog.log(
        event_type='registration',
        event_category='auth',
        user_id=user.id,
        description=f'New user registered: {user.email}',
        success=True
    )
    security_audit.account_created(user.id, user.email)
    
    # Send verification email (if email is enabled)
    if current_app.config.get('MAIL_ENABLED'):
        try:
            from app.services.email_service import email_verification_service
            token = user.generate_verification_token()
            email_verification_service.send_verification_email(user, token)
        except Exception as e:
            current_app.logger.warning(f"Failed to send verification email: {e}")
    
    # Generate tokens
    access_token, refresh_token = generate_tokens(user)
    
    # Tokens delivered via httpOnly cookies only (S05).
    resp = jsonify({
        'message': 'Registration successful',
        'user': user.to_dict(),
    })
    resp.status_code = 201
    _set_auth_cookies(resp, access_token, refresh_token)
    return resp


def parse_user_agent(ua_string):
    """Parse user agent string for device info."""
    if not ua_string:
        return {}
    
    result = {
        'device_type': 'desktop',
        'browser': None,
        'browser_version': None,
        'os': None,
        'os_version': None,
    }
    
    ua_lower = ua_string.lower()
    
    # Device type
    if 'mobile' in ua_lower or ('android' in ua_lower and 'mobile' in ua_lower):
        result['device_type'] = 'mobile'
    elif 'tablet' in ua_lower or 'ipad' in ua_lower:
        result['device_type'] = 'tablet'
    
    # Browser detection
    if 'firefox' in ua_lower:
        result['browser'] = 'Firefox'
        match = re.search(r'firefox[/\s]?([\d.]+)', ua_lower)
        if match:
            result['browser_version'] = match.group(1)
    elif 'edg/' in ua_lower or 'edge/' in ua_lower:
        result['browser'] = 'Edge'
        match = re.search(r'edg[e]?[/\s]?([\d.]+)', ua_lower)
        if match:
            result['browser_version'] = match.group(1)
    elif 'chrome' in ua_lower and 'chromium' not in ua_lower:
        result['browser'] = 'Chrome'
        match = re.search(r'chrome[/\s]?([\d.]+)', ua_lower)
        if match:
            result['browser_version'] = match.group(1)
    elif 'safari' in ua_lower and 'chrome' not in ua_lower:
        result['browser'] = 'Safari'
        match = re.search(r'version[/\s]?([\d.]+)', ua_lower)
        if match:
            result['browser_version'] = match.group(1)
    elif 'opera' in ua_lower or 'opr/' in ua_lower:
        result['browser'] = 'Opera'
    
    # OS detection
    if 'windows' in ua_lower:
        result['os'] = 'Windows'
        if 'windows nt 10' in ua_lower:
            result['os_version'] = '10/11'
        elif 'windows nt 6.3' in ua_lower:
            result['os_version'] = '8.1'
        elif 'windows nt 6.1' in ua_lower:
            result['os_version'] = '7'
    elif 'mac os x' in ua_lower or 'macintosh' in ua_lower:
        result['os'] = 'macOS'
        match = re.search(r'mac os x[/\s]?([\d_]+)', ua_lower)
        if match:
            result['os_version'] = match.group(1).replace('_', '.')
    elif 'android' in ua_lower:
        result['os'] = 'Android'
        match = re.search(r'android[/\s]?([\d.]+)', ua_lower)
        if match:
            result['os_version'] = match.group(1)
    elif 'iphone' in ua_lower or 'ipad' in ua_lower:
        result['os'] = 'iOS'
        match = re.search(r'os[/\s]?([\d_]+)', ua_lower)
        if match:
            result['os_version'] = match.group(1).replace('_', '.')
    elif 'linux' in ua_lower:
        result['os'] = 'Linux'
        if 'ubuntu' in ua_lower:
            result['os'] = 'Ubuntu'
        elif 'fedora' in ua_lower:
            result['os'] = 'Fedora'
    
    return result


@auth_bp.route('/login', methods=['POST'])
def login():
    """Login user with account lockout protection and IP/device blocking."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Invalid request body'}), 400
    except Exception:
        return jsonify({'error': 'Invalid JSON'}), 400
    
    email = data.get('email', '').lower()
    password = data.get('password', '')
    totp_code = data.get('totp_code')
    backup_code = data.get('backup_code', '').upper().replace('-', '').replace(' ', '') if data.get('backup_code') else None
    
    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400
    
    # Get IP address and user agent for blocking checks
    # S11: request.remote_addr is set by ProxyFix to the real client IP.
    ip_address = request.remote_addr or 'Unknown'
    user_agent = request.headers.get('User-Agent', '')
    
    # Check if IP is blocked
    try:
        ip_blocked, blocked_ip_record = BlockedIP.is_blocked(ip_address)
    except Exception as e:
        current_app.logger.error(f'Database error checking blocked IP: {e}')
        ip_blocked = False
        blocked_ip_record = None
    if ip_blocked:
        ActivityLog.log(
            event_type='login_blocked_ip',
            event_category='auth',
            description=f'Login blocked - IP address blocked: {ip_address}',
            success=False,
            error_message='IP address is blocked',
            extra_data={'email': email, 'ip': ip_address, 'block_id': blocked_ip_record.id}
        )
        return jsonify({
            'error': 'Access denied. Your IP address has been blocked due to suspicious activity. Contact support if you believe this is an error.',
            'blocked': True,
            'block_type': 'ip'
        }), 403
    
    # Check if device is blocked  
    try:
        device_blocked, blocked_device_record = BlockedDevice.is_blocked(user_agent, ip_address)
    except Exception as e:
        current_app.logger.error(f'Database error checking blocked device: {e}')
        db.session.rollback()
        device_blocked = False
        blocked_device_record = None
    if device_blocked:
        ActivityLog.log(
            event_type='login_blocked_device',
            event_category='auth',
            description=f'Login blocked - device blocked: {blocked_device_record.device_fingerprint[:8]}...',
            success=False,
            error_message='Device is blocked',
            extra_data={'email': email, 'device_id': blocked_device_record.id}
        )
        return jsonify({
            'error': 'Access denied. This device has been blocked due to suspicious activity. Contact support if you believe this is an error.',
            'blocked': True,
            'block_type': 'device'
        }), 403
    
    # Check if account is locked
    locked, remaining_seconds = is_account_locked(email)
    if locked:
        remaining_minutes = remaining_seconds // 60
        ActivityLog.log(
            event_type='login_blocked_lockout',
            event_category='auth',
            description=f'Login blocked - account locked: {email}',
            success=False,
            error_message='Account temporarily locked',
            extra_data={'email': email, 'remaining_seconds': remaining_seconds}
        )
        security_audit.login_locked(email, remaining_seconds // 60)
        return jsonify({
            'error': f'Account temporarily locked. Try again in {remaining_minutes} minutes.',
            'locked': True,
            'retry_after': remaining_seconds
        }), 429
    
    try:
        user = User.query.filter_by(email=email).first()
    except Exception as e:
        current_app.logger.error(f'Database error during login query: {e}')
        db.session.rollback()
        return jsonify({'error': 'Database error. Please try again or contact support.'}), 500
    
    if not user or not user.check_password(password):
        # Record failed attempt and check for lockout (by email)
        is_locked, lockout_time, attempts = record_failed_login(email)
        
        # Get location info for IP tracking
        location_info = get_ip_location(ip_address)
        
        # Record failed attempt for IP (auto-blocks after 3 attempts)
        try:
            ip_now_blocked, _, ip_attempts = BlockedIP.record_failed_attempt(
                ip_address=ip_address,
                email=email,
                user_id=user.id if user else None,
                location_info=location_info,
                max_attempts=3
            )
        except Exception as e:
            current_app.logger.error(f'Failed to record IP attempt: {e}')
            db.session.rollback()
            ip_now_blocked, _, ip_attempts = False, None, 0
        
        # Parse device info for device tracking
        device_info = parse_user_agent(user_agent) if user_agent else None
        
        # Record failed attempt for device (auto-blocks after 3 attempts)
        try:
            device_now_blocked, _, device_attempts = BlockedDevice.record_failed_attempt(
                user_agent=user_agent,
                ip_address=ip_address,
                email=email,
                user_id=user.id if user else None,
                device_info=device_info,
                max_attempts=3
            )
        except Exception as e:
            current_app.logger.error(f'Failed to record device attempt: {e}')
            db.session.rollback()
            device_now_blocked, _, device_attempts = False, None, 0
        
        # Log failed login attempt
        ActivityLog.log(
            event_type='login_failed',
            event_category='auth',
            user_id=user.id if user else None,
            description=f'Failed login attempt for email: {email} (attempt {attempts}/{MAX_LOGIN_ATTEMPTS})',
            success=False,
            error_message='Invalid credentials',
            extra_data={
                'email': email, 
                'attempt_number': attempts,
                'ip_attempts': ip_attempts,
                'device_attempts': device_attempts,
                'ip_blocked': ip_now_blocked,
                'device_blocked': device_now_blocked
            }
        )
        security_audit.login_failed(email, 'Invalid credentials', attempts)
        
        # Check if IP or device just got blocked
        if ip_now_blocked:
            return jsonify({
                'error': 'Too many failed attempts from this IP address. Access has been blocked.',
                'blocked': True,
                'block_type': 'ip'
            }), 403
        
        if device_now_blocked:
            return jsonify({
                'error': 'Too many failed attempts from this device. Access has been blocked.',
                'blocked': True,
                'block_type': 'device'
            }), 403
        
        if is_locked:
            return jsonify({
                'error': f'Too many failed attempts. Account locked for {LOCKOUT_DURATION // 60} minutes.',
                'locked': True,
                'retry_after': lockout_time
            }), 429
        
        # Show remaining attempts warning after 3 failures
        remaining = MAX_LOGIN_ATTEMPTS - attempts
        if remaining <= 2:
            return jsonify({
                'error': f'Invalid email or password. {remaining} attempts remaining before lockout.'
            }), 401
        
        return jsonify({'error': 'Invalid email or password'}), 401
    
    if not user.is_active:
        # Log blocked login attempt
        ActivityLog.log(
            event_type='login_blocked',
            event_category='auth',
            user_id=user.id,
            description=f'Login blocked - account disabled: {email}',
            success=False,
            error_message='Account disabled'
        )
        return jsonify({'error': 'Account is disabled'}), 401

    domain_policy_error = _enforce_login_domain_policy(user)
    if domain_policy_error:
        ActivityLog.log(
            event_type='login_blocked_domain',
            event_category='auth',
            user_id=user.id,
            description=f'Login blocked by domain policy for: {email}',
            success=False,
            error_message='Domain policy violation',
            extra_data={'host': _request_host(), 'is_admin': user.is_admin}
        )
        return domain_policy_error
    
    # Check 2FA if enabled
    if user.two_factor_enabled:
        if not totp_code and not backup_code:
            return jsonify({
                'requires_2fa': True,
                'message': '2FA code required'
            }), 200
        
        code_valid = False
        used_backup_code = False
        
        # Try TOTP code first
        if totp_code:
            totp = pyotp.TOTP(_get_totp_secret(user))
            code_valid = totp.verify(totp_code)
        
        # Try backup code if TOTP failed or wasn't provided
        if not code_valid and backup_code and user.two_factor_backup_codes:
            from werkzeug.security import check_password_hash
            remaining_codes = []
            
            for hashed_code in user.two_factor_backup_codes:
                if not code_valid and check_password_hash(hashed_code, backup_code):
                    code_valid = True
                    used_backup_code = True
                    # Don't add this code to remaining (it's used up)
                else:
                    remaining_codes.append(hashed_code)
            
            if code_valid:
                # Update remaining backup codes
                user.two_factor_backup_codes = remaining_codes if remaining_codes else None
        
        if not code_valid:
            # Log failed 2FA attempt
            ActivityLog.log(
                event_type='2fa_failed',
                event_category='auth',
                user_id=user.id,
                description=f'Failed 2FA verification for: {email}',
                success=False,
                error_message='Invalid 2FA code'
            )
            security_audit.two_factor_failed(user.id, user.email)
            return jsonify({'error': 'Invalid 2FA code'}), 401
    
    # Clear failed login attempts on successful login
    clear_failed_logins(email)
    
    # Clear IP and device failed attempts (if not blocked)
    BlockedIP.clear_attempts(ip_address)
    BlockedDevice.clear_attempts(user_agent, ip_address)
    
    # Check for new device / suspicious location only when user has not opted out (S18)
    if user.login_alerts_enabled:
        # Check for new device login
        new_device, device_info = is_new_device(user.id)

        # Check for suspicious location (new country)
        ip_address = get_real_client_ip()
        current_location = get_ip_location(ip_address)
        suspicious_location, location_info, known_locations = is_suspicious_location(user.id, current_location)
    else:
        new_device, device_info = False, {}
        ip_address = get_real_client_ip()
        current_location = None
        suspicious_location, location_info, known_locations = False, None, set()
    
    # Update last login
    user.last_login = datetime.now(timezone.utc)
    db.session.commit()
    
    # Generate tokens
    access_token, refresh_token = generate_tokens(user)
    
    # Register device and location as known (only when alerts are enabled)
    if user.login_alerts_enabled:
        register_device(user.id)
        if location_info and location_info.get('country_code'):
            register_user_location(user.id, location_info['country_code'])
    
    # Send new device login alert email
    if new_device and current_app.config.get('MAIL_ENABLED'):
        try:
            from app.services.email_service import send_new_login_alert
            send_new_login_alert(user, device_info)
        except Exception as e:
            current_app.logger.warning(f"Failed to send new device login alert: {e}")
    
    # Send suspicious location alert (even if same device, new country is suspicious)
    if suspicious_location and current_app.config.get('MAIL_ENABLED'):
        try:
            from app.services.email_service import send_suspicious_location_alert
            send_suspicious_location_alert(user, location_info, list(known_locations))
        except Exception as e:
            current_app.logger.warning(f"Failed to send suspicious location alert: {e}")
    
    # Log successful login
    ActivityLog.log(
        event_type='login_success',
        event_category='auth',
        user_id=user.id,
        description=f'Successful login for: {email}',
        success=True,
        extra_data={
            'used_2fa': user.two_factor_enabled,
            'used_backup_code': used_backup_code if user.two_factor_enabled else False,
            'new_device': new_device,
            'suspicious_location': suspicious_location,
            'ip_address': ip_address,
            'location': location_info
        }
    )
    
    # Security audit log
    location_str = location_info.get('city', '') + ', ' + location_info.get('country', '') if location_info else None
    security_audit.login_success(user.id, user.email, new_device, location_str)
    
    if suspicious_location and location_info:
        previous_countries = ', '.join(known_locations) if known_locations else 'Unknown'
        security_audit.suspicious_location(
            user.id, user.email,
            previous_countries,
            location_info.get('country', 'Unknown')
        )
    
    # Set tokens in httpOnly SameSite=Strict cookies (S05 — removed from JSON body).
    # The JSON response intentionally omits the token strings so they are
    # never accessible to JavaScript on the page origin.
    resp = jsonify({
        'message': 'Login successful',
        'user': user.to_dict(),
        'new_device': new_device,
        'suspicious_location': suspicious_location,
    })
    _set_auth_cookies(resp, access_token, refresh_token)
    return resp


@auth_bp.route('/refresh', methods=['POST'])
def refresh_token():
    """Refresh access token.

    The refresh token is read from the httpOnly ``refresh_token`` cookie
    (S05).  A body ``refresh_token`` field is accepted as a fallback for
    non-browser API clients that cannot use cookies.
    """
    # 1. httpOnly cookie (browser PWA)
    refresh = request.cookies.get('refresh_token')

    # 2. JSON body fallback (non-browser API clients)
    if not refresh:
        data = request.get_json(silent=True) or {}
        refresh = data.get('refresh_token')

    if not refresh:
        return jsonify({'error': 'Refresh token required'}), 400
    
    try:
        payload = jwt.decode(
            refresh,
            current_app.config['JWT_SECRET_KEY'],
            algorithms=['HS256']
        )
        
        if payload.get('type') != 'refresh':
            return jsonify({'error': 'Invalid token type'}), 401
        
        user = User.query.get(payload['user_id'])
        if not user or not user.is_active:
            return jsonify({'error': 'User not found or disabled'}), 401
        
        # Validate session still exists
        token_jti = payload.get('jti')
        if not token_jti:
            return jsonify({'error': 'Session invalid. Please login again.', 'code': 'SESSION_INVALID'}), 401
        
        if not validate_session(user.id, token_jti):
            return jsonify({'error': 'Session expired. Please login again.', 'code': 'SESSION_EXPIRED'}), 401

        # Enforce the absolute 48-hour session wall.
        # Read the original session's absolute_expires_at so it is propagated
        # into the new session (the window does NOT slide on each refresh).
        absolute_expires_at = None
        session_data = get_session_data(user.id, token_jti)
        if session_data and session_data.get('absolute_expires_at'):
            try:
                absolute_expires_at = datetime.fromisoformat(session_data['absolute_expires_at'])
                if absolute_expires_at <= datetime.now(timezone.utc):
                    return jsonify({
                        'error': 'Session expired after 48 hours. Please login again.',
                        'code': 'SESSION_EXPIRED'
                    }), 401
            except (ValueError, TypeError):
                # Old session without absolute_expires_at — allow it this once;
                # the new session will set the wall going forward.
                absolute_expires_at = None

        # Generate new tokens but don't invalidate existing session (same session continues)
        access_token, new_refresh = generate_tokens(user, invalidate_existing=False, absolute_expires_at=absolute_expires_at)

        # Deliver via cookies (S05) — also echo in JSON body for non-browser clients.
        resp = jsonify({'message': 'Token refreshed'})
        _set_auth_cookies(resp, access_token, new_refresh)
        return resp
        
    except jwt.ExpiredSignatureError:
        return jsonify({'error': 'Refresh token expired'}), 401
    except jwt.InvalidTokenError:
        return jsonify({'error': 'Invalid refresh token'}), 401


@auth_bp.route('/logout', methods=['POST'])
@token_required
def logout(current_user):
    """Logout user, blacklist the access token, and clear auth cookies."""
    # Resolve the token that was used for this request (cookie or header).
    token = request.cookies.get('access_token')
    if not token:
        token = request.headers.get('Authorization', '').split(' ')[-1]

    # Decode once to recover the jti/exp. verify_exp=False so we can still revoke
    # the session even if the access token has already expired.
    token_jti = None
    token_exp = 0
    try:
        payload = jwt.decode(
            token,
            current_app.config['JWT_SECRET_KEY'],
            algorithms=['HS256'],
            options={'verify_exp': False},
        )
        token_jti = payload.get('jti')
        token_exp = payload.get('exp', 0)
    except Exception:
        pass

    if redis_client:
        try:
            # Blacklist token for its remaining lifetime (skip if already expired).
            ttl = max(0, token_exp - int(datetime.now(timezone.utc).timestamp()))
            if ttl > 0:
                redis_client.setex(f'blacklist:{token}', ttl, '1')

            # Also delete the Redis session key.
            if token_jti:
                redis_client.delete(f'session:{current_user.id}:{token_jti}')
        except Exception:
            pass

    # S01: revoke the durable DB session so logout holds even if Redis is down
    # now or goes down later — the DB-fallback validation path rejects revoked
    # (or pruned/absent) rows.
    if token_jti:
        _db_revoke_session(current_user.id, token_jti)
    
    # Log logout
    ActivityLog.log(
        event_type='logout',
        event_category='auth',
        user_id=current_user.id,
        description=f'User logged out: {current_user.email}',
        success=True
    )
    security_audit.logout(current_user.id, current_user.email)

    resp = jsonify({'message': 'Logged out successfully'})
    _clear_auth_cookies(resp)
    return resp


@auth_bp.route('/me', methods=['GET'])
@token_required
def get_current_user(current_user):
    """Get current user profile."""
    return jsonify(current_user.to_dict())


@auth_bp.route('/me', methods=['PUT'])
@token_required
def update_profile(current_user):
    """Update current user profile and preferences."""
    data = request.get_json()
    
    # Sensitive fields that require password verification
    sensitive_fields = ['email', 'username', 'name', 'first_name', 'last_name']
    
    # Check if any sensitive field is being changed
    is_sensitive_change = any(
        field in data and data[field] != getattr(current_user, field if field != 'name' else 'display_name', None)
        for field in sensitive_fields
    )
    
    # If sensitive change, require password (and 2FA if enabled)
    if is_sensitive_change:
        password = data.get('current_password')
        if not password:
            return jsonify({
                'error': 'Password required for account changes',
                'requires_verification': True
            }), 401
        
        if not current_user.check_password(password):
            return jsonify({'error': 'Incorrect password'}), 401
        
        # Check 2FA if enabled
        if current_user.two_factor_enabled:
            totp_code = data.get('totp_code')
            if not totp_code:
                return jsonify({
                    'error': '2FA code required',
                    'requires_2fa': True
                }), 401
            
            totp = pyotp.TOTP(_get_totp_secret(current_user))
            if not totp.verify(totp_code, valid_window=1):
                return jsonify({'error': 'Invalid 2FA code'}), 401
    
    # Updateable profile fields
    profile_fields = ['first_name', 'last_name', 'username']
    
    # Updateable preference fields - these persist user settings
    preference_fields = [
        'language', 'timezone', 'theme', 'currency',
        'distance_unit', 'volume_unit', 'date_format',
        'country_preference',
        # notification_email removed — must use POST /notification-email (GDPR: encryption, consent, double opt-in)
        # Location settings
        'location_lat', 'location_lon', 'location_name', 'location_auto_detect'
    ]
    
    # Email notification preference fields
    email_notification_fields = [
        'notifications_enabled',
        'email_insurance_alerts',
        'email_tax_alerts',
        'email_service_alerts',
        'email_reminder_alerts',
        'email_smart_alerts',
        'daily_alerts_enabled',
        'weekly_report_enabled',
        'monthly_report_enabled',
        'alert_days_before',
        'login_alerts_enabled',  # S18: suspicious login/device detection opt-out
    ]
    
    # Handle 'name' field (split into first/last)
    if 'name' in data:
        name_parts = data['name'].split(' ', 1)
        current_user.first_name = name_parts[0]
        current_user.last_name = name_parts[1] if len(name_parts) > 1 else ''
    
    # Handle email update with validation
    if 'email' in data and data['email']:
        new_email = data['email'].lower().strip()
        if new_email != current_user.email:
            # Check if email is already taken by another user
            existing = User.query.filter(
                User.email == new_email,
                User.id != current_user.id
            ).first()
            if existing:
                return jsonify({'error': 'Email is already in use'}), 400
            current_user.email = new_email
    
    # Handle username update with validation
    if 'username' in data and data['username']:
        new_username = data['username'].strip()
        if new_username != current_user.username:
            # Check if username is already taken by another user
            existing = User.query.filter(
                User.username == new_username,
                User.id != current_user.id
            ).first()
            if existing:
                return jsonify({'error': 'Username is already in use'}), 400
            current_user.username = new_username
    
    # Update profile fields
    for field in profile_fields:
        if field in data:
            setattr(current_user, field, data[field])
    
    # Update preference fields (with special handling for location coordinates)
    for field in preference_fields:
        if field in data:
            value = data[field]
            # Explicit float conversion for coordinates
            if field in ('location_lat', 'location_lon') and value is not None:
                try:
                    # Handle string values that might have comma as decimal separator
                    if isinstance(value, str):
                        value = value.replace(',', '.').strip()
                    value = float(value) if value != '' else None
                    # Validate coordinate ranges
                    if value is not None:
                        if field == 'location_lat' and not (-90 <= value <= 90):
                            continue  # Invalid latitude, skip
                        if field == 'location_lon' and not (-180 <= value <= 180):
                            continue  # Invalid longitude, skip
                except (ValueError, TypeError):
                    continue  # Skip invalid values
            setattr(current_user, field, value)
    
    # Update email notification fields
    for field in email_notification_fields:
        if field in data:
            setattr(current_user, field, data[field])
    
    db.session.commit()
    
    return jsonify({
        'message': 'Profile updated',
        'user': current_user.to_dict(include_private=True)
    })


@auth_bp.route('/password', methods=['PUT'])
@token_required
def change_password(current_user):
    """Change user password with enhanced security validation."""
    data = request.get_json()
    
    current_password = data.get('current_password')
    new_password = data.get('new_password')
    confirm_password = data.get('confirm_password')
    
    if not current_password or not new_password:
        return jsonify({'error': 'Current and new password required'}), 400
    
    # Verify password confirmation
    if confirm_password and new_password != confirm_password:
        return jsonify({'error': 'New passwords do not match'}), 400
    
    if not current_user.check_password(current_password):
        return jsonify({'error': 'Current password is incorrect'}), 401
    
    # Check 2FA if enabled
    if current_user.two_factor_enabled:
        totp_code = data.get('totp_code')
        if not totp_code:
            return jsonify({
                'error': '2FA code required',
                'requires_2fa': True
            }), 401
        
        totp = pyotp.TOTP(_get_totp_secret(current_user))
        if not totp.verify(totp_code, valid_window=1):
            return jsonify({'error': 'Invalid 2FA code'}), 401
    
    # Validate password strength
    is_valid, errors, score, strength = validate_password_strength(new_password)
    
    if not is_valid:
        return jsonify({
            'error': errors[0] if errors else 'Password is too weak',
            'password_errors': errors,
            'strength_score': score,
            'strength': strength
        }), 400
    
    # Check that new password is different from current
    if current_user.check_password(new_password):
        return jsonify({'error': 'New password must be different from current password'}), 400
    
    current_user.set_password(new_password)
    current_user.must_change_password = False  # Clear the forced password change flag
    db.session.commit()
    
    # Log password change
    ActivityLog.log(
        event_type='password_change',
        event_category='auth',
        user_id=current_user.id,
        description=f'Password changed for: {current_user.email}',
        success=True
    )
    security_audit.password_change(current_user.id, current_user.email, success=True)
    
    return jsonify({
        'message': 'Password changed successfully',
        'strength': strength,
        'strength_score': score
    })


@auth_bp.route('/password/validate', methods=['POST'])
@token_required
def validate_password(current_user):
    """Validate password strength without changing it. Includes breach check."""
    data = request.get_json()
    password = data.get('password', '')
    
    is_valid, errors, score, strength = validate_password_strength(password)
    
    # Check for breach count separately for detailed feedback
    breach_count = check_password_breach(password)
    
    return jsonify({
        'is_valid': is_valid,
        'errors': errors,
        'strength_score': score,
        'strength': strength,
        'breach_count': breach_count,
        'is_breached': breach_count > 0
    })


@auth_bp.route('/password/check', methods=['POST'])
def check_password_public():
    """Public endpoint to check password strength during registration.
    Rate limited to prevent abuse.
    """
    data = request.get_json()
    password = data.get('password', '')
    
    if not password:
        return jsonify({'error': 'Password required'}), 400
    
    is_valid, errors, score, strength = validate_password_strength(password)
    breach_count = check_password_breach(password)
    
    return jsonify({
        'is_valid': is_valid,
        'errors': errors,
        'strength_score': score,
        'strength': strength,
        'breach_count': breach_count,
        'is_breached': breach_count > 0
    })


@auth_bp.route('/2fa/setup', methods=['POST'])
@token_required
def setup_2fa(current_user):
    """Generate TOTP secret and QR code for 2FA setup.

    S24 fix — two changes:
    1. The secret is staged in Redis (TTL 10 min) rather than committed to the
       database immediately.  If the user abandons the setup flow the secret
       expires automatically and is never persisted.  On Redis unavailability we
       fall back to the old behaviour (store in DB) so the feature degrades
       gracefully rather than failing hard.
    2. The raw provisioning_uri is omitted from the response — it encodes the
       secret verbatim in a URL-parseable form and is redundant with the QR
       code image.  The frontend only reads `qr_code` and `secret`.
    """
    if current_user.two_factor_enabled:
        return jsonify({'error': '2FA is already enabled'}), 400

    # Generate a fresh base32 TOTP secret.
    secret = pyotp.random_base32()

    # S24: Stage the plaintext secret in Redis for 10 minutes rather than
    # writing it to the database before the user has confirmed setup.
    # Key: '2fa_pending:<user_id>'  Value: plaintext base32 secret
    _pending_key = f'2fa_pending:{current_user.id}'
    _stored_in_redis = False
    if redis_client:
        try:
            redis_client.setex(_pending_key, 600, secret)  # 10-minute TTL
            _stored_in_redis = True
        except Exception as exc:
            current_app.logger.warning(
                f'[2FA setup] Redis write failed for user {current_user.id}: {exc}. '
                'Falling back to DB staging.'
            )

    if not _stored_in_redis:
        # Fallback: store encrypted in DB so verify_2fa() can still succeed.
        _set_totp_secret(current_user, secret)
        db.session.commit()

    # Build provisioning URI for the QR code image only.
    totp = pyotp.TOTP(secret)
    app_name = current_app.config.get('APP_NAME', 'GearCargo')
    uri = totp.provisioning_uri(
        name=current_user.email,
        issuer_name=app_name
    )

    # Render QR code as a PNG data URI.
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    qr_base64 = base64.b64encode(buffer.getvalue()).decode()

    # S24: provisioning_uri is intentionally NOT returned — it contains the
    # raw secret in a URL-parseable form and the frontend does not use it.
    return jsonify({
        'secret': secret,
        'qr_code': f'data:image/png;base64,{qr_base64}',
    })


@auth_bp.route('/2fa/verify', methods=['POST'])
@token_required
def verify_2fa(current_user):
    """Verify and enable 2FA.

    S24 fix: reads the pending secret from Redis (staged by setup_2fa) rather
    than from the database.  Only on successful TOTP verification is the secret
    encrypted and persisted to the DB, eliminating the window where an
    unconfirmed secret exists in the database.

    Fallback: if the Redis key is absent (Redis unavailable, or the 10-minute
    TTL expired, or setup fell back to DB storage) we fall through to reading
    the encrypted secret from user.two_factor_secret — identical to the
    previous behaviour.
    """
    data = request.get_json()
    code = data.get('code')

    if not code:
        return jsonify({'error': 'Verification code required'}), 400

    # S24: Try to consume the pending secret from Redis first.
    _pending_key = f'2fa_pending:{current_user.id}'
    pending_secret = None
    if redis_client:
        try:
            raw = redis_client.get(_pending_key)
            if raw:
                pending_secret = raw.decode()
        except Exception as exc:
            current_app.logger.warning(
                f'[2FA verify] Redis read failed for user {current_user.id}: {exc}. '
                'Falling back to DB-stored secret.'
            )

    if pending_secret:
        # Happy path: secret was staged in Redis.
        totp = pyotp.TOTP(pending_secret)
        if not totp.verify(code):
            return jsonify({'error': 'Invalid verification code'}), 401
        # TOTP verified — now encrypt and persist the secret.
        _set_totp_secret(current_user, pending_secret)
        try:
            redis_client.delete(_pending_key)
        except Exception:
            pass  # Non-critical — key will expire via TTL anyway.
    else:
        # Fallback: Redis unavailable, TTL expired, or setup stored directly
        # in DB (Redis was down at setup time).
        if not current_user.two_factor_secret:
            return jsonify({'error': 'Please setup 2FA first'}), 400
        totp = pyotp.TOTP(_get_totp_secret(current_user))
        if not totp.verify(code):
            return jsonify({'error': 'Invalid verification code'}), 401
    
    # Generate backup codes
    import secrets
    backup_codes = [secrets.token_hex(4).upper() for _ in range(10)]
    
    # Store hashed backup codes for security
    from werkzeug.security import generate_password_hash
    hashed_codes = [generate_password_hash(code, method='pbkdf2:sha256') for code in backup_codes]
    
    current_user.two_factor_backup_codes = hashed_codes
    current_user.two_factor_enabled = True
    db.session.commit()
    
    # Log 2FA enabled
    ActivityLog.log(
        event_type='2fa_enabled',
        event_category='auth',
        user_id=current_user.id,
        description=f'2FA enabled for: {current_user.email}',
        success=True
    )
    security_audit.two_factor_change(current_user.id, current_user.email, enabled=True)
    
    return jsonify({
        'message': '2FA enabled successfully',
        'backup_codes': backup_codes,  # Return plain codes only once
    })


@auth_bp.route('/2fa/disable', methods=['POST'])
@token_required
def disable_2fa(current_user):
    """Disable 2FA."""
    data = request.get_json()
    password = data.get('password')
    
    if not password or not current_user.check_password(password):
        return jsonify({'error': 'Password verification failed'}), 401
    
    current_user.two_factor_enabled = False
    current_user.two_factor_secret = None
    current_user.two_factor_backup_codes = None
    db.session.commit()
    
    # Log 2FA disabled
    ActivityLog.log(
        event_type='2fa_disabled',
        event_category='auth',
        user_id=current_user.id,
        description=f'2FA disabled for: {current_user.email}',
        success=True
    )
    security_audit.two_factor_change(current_user.id, current_user.email, enabled=False)
    
    return jsonify({'message': '2FA disabled successfully'})


@auth_bp.route('/2fa/verify-backup', methods=['POST'])
@token_required
def verify_backup_code(current_user):
    """Verify a backup code during login."""
    data = request.get_json()
    backup_code = data.get('backup_code', '').upper().replace('-', '').replace(' ', '')
    
    if not backup_code:
        return jsonify({'error': 'Backup code required'}), 400
    
    if not current_user.two_factor_backup_codes:
        return jsonify({'error': 'No backup codes available'}), 400
    
    # Check each hashed backup code
    from werkzeug.security import check_password_hash
    
    remaining_codes = []
    code_valid = False
    
    for hashed_code in current_user.two_factor_backup_codes:
        if not code_valid and check_password_hash(hashed_code, backup_code):
            code_valid = True
            # Don't add this code to remaining (it's used up)
        else:
            remaining_codes.append(hashed_code)
    
    if not code_valid:
        return jsonify({'error': 'Invalid backup code'}), 401
    
    # Update remaining backup codes
    current_user.two_factor_backup_codes = remaining_codes if remaining_codes else None
    db.session.commit()
    
    return jsonify({
        'message': 'Backup code verified',
        'remaining_codes': len(remaining_codes)
    })


@auth_bp.route('/2fa/regenerate-backup', methods=['POST'])
@token_required
def regenerate_backup_codes(current_user):
    """Regenerate backup codes (requires password)."""
    data = request.get_json()
    password = data.get('password')
    
    if not password or not current_user.check_password(password):
        return jsonify({'error': 'Password verification failed'}), 401
    
    if not current_user.two_factor_enabled:
        return jsonify({'error': '2FA is not enabled'}), 400
    
    # Generate new backup codes
    import secrets
    backup_codes = [secrets.token_hex(4).upper() for _ in range(10)]
    
    # Store hashed backup codes
    from werkzeug.security import generate_password_hash
    hashed_codes = [generate_password_hash(code, method='pbkdf2:sha256') for code in backup_codes]
    
    current_user.two_factor_backup_codes = hashed_codes
    db.session.commit()
    
    return jsonify({
        'message': 'Backup codes regenerated',
        'backup_codes': backup_codes,
    })


@auth_bp.route('/2fa/status', methods=['GET'])
@token_required
def get_2fa_status(current_user):
    """Get 2FA status for current user."""
    return jsonify({
        'enabled': current_user.two_factor_enabled,
        'has_backup_codes': bool(current_user.two_factor_backup_codes),
        'backup_codes_count': len(current_user.two_factor_backup_codes) if current_user.two_factor_backup_codes else 0
    })


@auth_bp.route('/password-reset/request', methods=['POST'])
def request_password_reset():
    """Request password reset email."""
    from app.services.email_service import PasswordResetEmailService
    
    data = request.get_json()
    email = data.get('email', '').lower()
    
    if not email:
        return jsonify({'error': 'Email is required'}), 400
    
    user = User.query.filter_by(email=email).first()
    
    # Always return success to prevent email enumeration
    if user:
        token = user.generate_reset_token()
        db.session.commit()
        # Send password reset email
        PasswordResetEmailService.send_password_reset_email(user, token)
    
    return jsonify({
        'message': 'If that email exists, a reset link has been sent'
    })


@auth_bp.route('/password-reset/verify', methods=['POST'])
def verify_reset_token():
    """Verify password reset token."""
    data = request.get_json()
    token = data.get('token')
    new_password = data.get('new_password')
    
    if not token or not new_password:
        return jsonify({'error': 'Token and new password required'}), 400
    
    user = User.verify_reset_token(token)
    
    if not user:
        return jsonify({'error': 'Invalid or expired reset token'}), 401

    # S03: enforce the full password policy (length / common / breached),
    # consistent with /change-password and the security-question reset path.
    is_valid, pw_errors, pw_score, pw_strength = validate_password_strength(new_password)
    if not is_valid:
        return jsonify({
            'error': pw_errors[0] if pw_errors else 'Password is too weak',
            'password_errors': pw_errors,
            'strength_score': pw_score,
            'strength': pw_strength,
        }), 400

    user.set_password(new_password)
    user.password_reset_token = None
    user.password_reset_expires = None
    db.session.commit()

    # Invalidate all existing sessions after a password reset (defence in depth).
    invalidate_user_sessions(user.id)

    return jsonify({'message': 'Password reset successfully'})


# ============================================================
# EMAIL VERIFICATION ENDPOINTS
# ============================================================

@auth_bp.route('/email/send-verification', methods=['POST'])
@token_required
def send_verification_email(current_user):
    """Send email verification email to current user."""
    from app.services.email_service import email_verification_service
    
    if current_user.email_verified:
        return jsonify({'message': 'Email already verified'}), 200
    
    if not current_app.config.get('MAIL_ENABLED'):
        return jsonify({'error': 'Email service is not enabled'}), 503
    
    # Generate verification token
    token = current_user.generate_verification_token()
    
    # Send verification email
    success = email_verification_service.send_verification_email(current_user, token)
    
    if success:
        return jsonify({'message': 'Verification email sent'})
    else:
        return jsonify({'error': 'Failed to send verification email'}), 500


@auth_bp.route('/email/verify', methods=['POST'])
def verify_email():
    """Verify email with token."""
    data = request.get_json()
    token = data.get('token')
    
    if not token:
        return jsonify({'error': 'Token is required'}), 400
    
    user = User.verify_email_token(token)
    
    if not user:
        return jsonify({'error': 'Invalid or expired verification token'}), 401
    
    user.mark_email_verified()

    # Cross-sync: if notification email matches account email, verify notification email too
    if user.notification_email and user.notification_email_hash:
        from app.utils.encryption import hash_email
        if hash_email(user.email) == user.notification_email_hash:
            user.notification_email_verified = True
    
    # Log the verification
    ActivityLog.log(
        event_type='email_verified',
        event_category='auth',
        user_id=user.id,
        description=f'Email verified for: {user.email}',
        success=True
    )
    
    return jsonify({
        'message': 'Email verified successfully',
        'user': user.to_dict()
    })


@auth_bp.route('/email/resend-verification', methods=['POST'])
def resend_verification_email():
    """Resend verification email (public endpoint - for login page)."""
    from app.services.email_service import email_verification_service
    
    data = request.get_json()
    email = data.get('email', '').lower()
    
    if not email:
        return jsonify({'error': 'Email is required'}), 400
    
    # Always return success to prevent email enumeration
    user = User.query.filter_by(email=email).first()
    
    if user and not user.email_verified:
        if current_app.config.get('MAIL_ENABLED'):
            token = user.generate_verification_token()
            email_verification_service.send_verification_email(user, token)
    
    return jsonify({
        'message': 'If that email exists and is unverified, a verification link has been sent'
    })


@auth_bp.route('/email/test', methods=['POST'])
@token_required
def send_test_email(current_user):
    """Send a test email to verify email notification settings."""
    if not current_app.config.get('MAIL_ENABLED'):
        return jsonify({'error': 'Email notifications are not enabled on this server'}), 503
    
    from app.services.email_service import EmailService
    
    success = EmailService.send_test_email(current_user)
    
    if success:
        return jsonify({'message': 'Test email sent successfully'})
    else:
        return jsonify({'error': 'Failed to send test email'}), 500


@auth_bp.route('/email/settings', methods=['GET'])
@token_required
def get_email_settings(current_user):
    """Get current user's email notification settings."""
    return jsonify({
        'email_enabled_on_server': current_app.config.get('MAIL_ENABLED', False),
        'notifications_enabled': current_user.notifications_enabled if current_user.notifications_enabled is not None else True,
        'email_insurance_alerts': current_user.email_insurance_alerts if current_user.email_insurance_alerts is not None else True,
        'email_tax_alerts': current_user.email_tax_alerts if current_user.email_tax_alerts is not None else True,
        'email_service_alerts': current_user.email_service_alerts if current_user.email_service_alerts is not None else True,
        'email_reminder_alerts': current_user.email_reminder_alerts if current_user.email_reminder_alerts is not None else True,
        'email_smart_alerts': current_user.email_smart_alerts if current_user.email_smart_alerts is not None else True,
        'login_alerts_enabled': current_user.login_alerts_enabled if current_user.login_alerts_enabled is not None else True,  # S18
        'daily_alerts_enabled': current_user.daily_alerts_enabled if current_user.daily_alerts_enabled is not None else True,
        'weekly_report_enabled': current_user.weekly_report_enabled if current_user.weekly_report_enabled is not None else False,
        'monthly_report_enabled': current_user.monthly_report_enabled if current_user.monthly_report_enabled is not None else True,
        'alert_days_before': current_user.alert_days_before or 14,
        # GDPR notification email fields
        'notification_email': current_user.get_decrypted_notification_email(),
        'notification_email_verified': current_user.notification_email_verified or False,
        'has_notification_email': bool(current_user.notification_email),
    })


# ============================================================
# GDPR Notification Email Endpoints
# ============================================================

NOTIFICATION_EMAIL_CONSENT_TEXT_V1 = (
    "I consent to receiving vehicle alerts, reports, and notifications "
    "from GearCargo at this email address. I understand I can withdraw "
    "consent at any time via the app settings or the unsubscribe link "
    "in any email."
)

@auth_bp.route('/notification-email', methods=['POST'])
@token_required
def set_notification_email(current_user):
    """Set or update the notification email with GDPR consent.
    Requires explicit consent. Sends verification email (double opt-in)."""
    import re as _re
    from app.utils.encryption import hash_email
    from app.models.email_consent_log import EmailConsentLog

    if not current_app.config.get('MAIL_ENABLED'):
        return jsonify({'error': 'Email service is not enabled on this server'}), 503

    data = request.get_json() or {}
    email_addr = (data.get('email') or '').strip().lower()
    consent = data.get('consent', False)

    # Validate consent
    if not consent:
        return jsonify({'error': 'Explicit consent is required to add a notification email'}), 400

    # Validate email format
    if not email_addr or not _re.match(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$', email_addr):
        return jsonify({'error': 'Invalid email address'}), 400

    # Rate limiting: max 3 verification sends per hour (check consent log)
    from datetime import datetime, timedelta
    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    recent_grants = EmailConsentLog.query.filter(
        EmailConsentLog.user_id == current_user.id,
        EmailConsentLog.action == 'grant',
        EmailConsentLog.created_at >= one_hour_ago
    ).count()
    if recent_grants >= 3:
        return jsonify({'error': 'Too many verification requests. Try again later.'}), 429

    # Get request context for GDPR record
    # S11: request.remote_addr is set by ProxyFix to the real client IP.
    ip_address = request.remote_addr or 'Unknown'
    user_agent = request.headers.get('User-Agent', '')[:500]

    # Encrypt and store
    current_user.set_notification_email_encrypted(email_addr)
    current_user.notification_email_verified = False
    current_user.notification_email_bounce_count = 0

    # Generate verification token
    token = current_user.generate_notification_email_token(expires_hours=72)

    # Record consent timestamp + IP
    current_user.notification_email_consented_at = datetime.now(timezone.utc)
    current_user.notification_email_consent_ip = ip_address

    # Generate unsubscribe token if needed
    current_user.generate_unsubscribe_token()

    # Immutable consent ledger entry
    EmailConsentLog.record(
        user_id=current_user.id,
        action='grant',
        email_hash=hash_email(email_addr),
        ip_address=ip_address,
        user_agent=user_agent,
        consent_text_version='1.0'
    )

    db.session.commit()

    # Send verification email
    from app.services.email_service import EmailService
    # Use USER_DOMAIN for user-facing email links
    user_domain = current_app.config.get('USER_DOMAIN', '').strip()
    if not user_domain:
        user_domain = current_app.config.get('APP_URL', 'http://localhost:5000')
    if not user_domain.startswith('http'):
        user_domain = f"https://{user_domain}"
    verify_url = f"{user_domain}/settings?verify_notification={token}"

    verify_html = f"""
    <div class="header">
        <img src="{user_domain}/icons/logo.png" alt="GearCargo" class="header-logo">
        <h1>✉️ Verify Notification Email</h1>
        <p class="header-subtitle">Confirm your email address</p>
    </div>
    <div class="content">
        <p>Hi {current_user.display_name},</p>
        <p>You requested to receive GearCargo notifications at this email address.</p>
        <p style="color: #94a3b8; font-size: 13px;">
            By clicking the button below, you confirm that:<br>
            <em>"{NOTIFICATION_EMAIL_CONSENT_TEXT_V1}"</em>
        </p>
        <a href="{verify_url}" class="btn">Verify Email Address</a>
        <p style="margin-top: 20px; color: #64748b; font-size: 12px;">
            This link expires in 72 hours. If you did not request this, ignore this email.
        </p>
    </div>
    """
    EmailService.send_email(
        to=email_addr,
        subject='Verify Your Notification Email',
        content_html=verify_html
    )

    # Activity log
    ActivityLog.log(
        event_type='notification_email_set',
        event_category='auth',
        user_id=current_user.id,
        description='Notification email set (verification pending)',
        ip_address=ip_address,
        success=True,
        extra_data={'email_hash': hash_email(email_addr)}
    )

    return jsonify({
        'message': 'Verification email sent. Check your inbox.',
        'notification_email': email_addr,
        'notification_email_verified': False,
    })


@auth_bp.route('/notification-email/verify', methods=['POST'])
@token_required
def verify_notification_email(current_user):
    """Verify notification email with token (double opt-in step 2)."""
    from app.models.email_consent_log import EmailConsentLog

    data = request.get_json() or {}
    token = data.get('token', '').strip()

    if not token:
        return jsonify({'error': 'Verification token is required'}), 400

    # Validate token
    if current_user.notification_email_token != token:
        return jsonify({'error': 'Invalid verification token'}), 401

    if not current_user.notification_email_token_exp or \
       current_user.notification_email_token_exp < datetime.now(timezone.utc):
        return jsonify({'error': 'Verification token has expired. Please request a new one.'}), 401

    # Mark as verified
    current_user.notification_email_verified = True
    current_user.notification_email_token = None
    current_user.notification_email_token_exp = None

    # Cross-sync: if notification email matches account email, verify account email too
    decrypted_notif = current_user.get_decrypted_notification_email()
    if decrypted_notif and decrypted_notif.lower() == current_user.email.lower():
        current_user.email_verified = True

    # Record consent context
    # S11: request.remote_addr is set by ProxyFix to the real client IP.
    ip_address = request.remote_addr or 'Unknown'
    user_agent = request.headers.get('User-Agent', '')[:500]
    email_hash = current_user.notification_email_hash or ''

    # Immutable consent ledger — verification record
    EmailConsentLog.record(
        user_id=current_user.id,
        action='verify',
        email_hash=email_hash,
        ip_address=ip_address,
        user_agent=user_agent,
        consent_text_version='1.0'
    )

    db.session.commit()

    # Activity log
    ActivityLog.log(
        event_type='notification_email_verified',
        event_category='auth',
        user_id=current_user.id,
        description='Notification email verified (double opt-in complete)',
        ip_address=ip_address,
        success=True
    )

    return jsonify({
        'message': 'Notification email verified successfully',
        'notification_email': current_user.get_decrypted_notification_email(),
        'notification_email_verified': True,
    })


@auth_bp.route('/notification-email', methods=['DELETE'])
@token_required
def remove_notification_email(current_user):
    """Remove the notification email and revoke consent."""
    from app.models.email_consent_log import EmailConsentLog

    email_hash = current_user.notification_email_hash or ''
    # S11: request.remote_addr is set by ProxyFix to the real client IP.
    ip_address = request.remote_addr or 'Unknown'
    user_agent = request.headers.get('User-Agent', '')[:500]

    # Clear all notification email data
    current_user.notification_email = None
    current_user.notification_email_hash = None
    current_user.notification_email_verified = False
    current_user.notification_email_token = None
    current_user.notification_email_token_exp = None
    current_user.notification_email_consented_at = None
    current_user.notification_email_consent_ip = None
    current_user.notification_email_bounce_count = 0

    # Immutable consent ledger — revocation
    if email_hash:
        EmailConsentLog.record(
            user_id=current_user.id,
            action='revoke',
            email_hash=email_hash,
            ip_address=ip_address,
            user_agent=user_agent,
            consent_text_version='1.0'
        )

    db.session.commit()

    ActivityLog.log(
        event_type='notification_email_removed',
        event_category='auth',
        user_id=current_user.id,
        description='Notification email removed, consent revoked',
        ip_address=ip_address,
        success=True
    )

    return jsonify({'message': 'Notification email removed', 'notification_email': '', 'notification_email_verified': False})


@auth_bp.route('/notification-email/resend', methods=['POST'])
@token_required
def resend_notification_verification(current_user):
    """Resend verification email for pending notification email."""
    from app.models.email_consent_log import EmailConsentLog

    if not current_app.config.get('MAIL_ENABLED'):
        return jsonify({'error': 'Email service is not enabled'}), 503

    if not current_user.notification_email:
        return jsonify({'error': 'No notification email set'}), 400

    if current_user.notification_email_verified:
        return jsonify({'message': 'Already verified'}), 200

    # Rate limit: max 3/hour
    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    recent = EmailConsentLog.query.filter(
        EmailConsentLog.user_id == current_user.id,
        EmailConsentLog.action.in_(['grant', 'verify']),
        EmailConsentLog.created_at >= one_hour_ago
    ).count()
    if recent >= 3:
        return jsonify({'error': 'Too many requests. Try again later.'}), 429

    # Regenerate token
    token = current_user.generate_notification_email_token(expires_hours=72)
    db.session.commit()

    email_addr = current_user.get_decrypted_notification_email()
    if not email_addr:
        return jsonify({'error': 'Could not decrypt notification email'}), 500

    from app.services.email_service import EmailService
    # Use USER_DOMAIN for user-facing email links
    user_domain = current_app.config.get('USER_DOMAIN', '').strip()
    if not user_domain:
        user_domain = current_app.config.get('APP_URL', 'http://localhost:5000')
    if not user_domain.startswith('http'):
        user_domain = f"https://{user_domain}"
    verify_url = f"{user_domain}/settings?verify_notification={token}"

    verify_html = f"""
    <div class="header">
        <img src="{user_domain}/icons/logo.png" alt="GearCargo" class="header-logo">
        <h1>✉️ Verify Notification Email</h1>
        <p class="header-subtitle">Confirm your email address</p>
    </div>
    <div class="content">
        <p>Hi {current_user.display_name},</p>
        <p>Please verify this email address to receive GearCargo notifications.</p>
        <a href="{verify_url}" class="btn">Verify Email Address</a>
        <p style="margin-top: 20px; color: #64748b; font-size: 12px;">
            This link expires in 72 hours.
        </p>
    </div>
    """
    EmailService.send_email(to=email_addr, subject='Verify Your Notification Email', content_html=verify_html)

    return jsonify({'message': 'Verification email resent'})


@auth_bp.route('/unsubscribe', methods=['GET'])
def unsubscribe_email():
    """One-click unsubscribe via signed token. Public endpoint (no auth)."""
    from app.models.email_consent_log import EmailConsentLog

    token = request.args.get('token', '').strip()
    if not token:
        return '<html><body style="background:#0f172a;color:#e2e8f0;font-family:sans-serif;text-align:center;padding:60px"><h1>Missing Token</h1><p>Invalid unsubscribe link.</p></body></html>', 400

    user = User.query.filter_by(unsubscribe_token=token).first()
    if not user:
        return '<html><body style="background:#0f172a;color:#e2e8f0;font-family:sans-serif;text-align:center;padding:60px"><h1>Invalid Link</h1><p>This unsubscribe link is no longer valid.</p></body></html>', 404

    # S11: request.remote_addr is set by ProxyFix to the real client IP.
    ip_address = request.remote_addr or 'Unknown'
    user_agent = request.headers.get('User-Agent', '')[:500]
    email_hash = user.notification_email_hash or ''

    # Disable notifications
    user.notifications_enabled = False
    user.notification_email_verified = False

    # Consent ledger
    EmailConsentLog.record(
        user_id=user.id,
        action='unsubscribe',
        email_hash=email_hash,
        ip_address=ip_address,
        user_agent=user_agent,
        consent_text_version='1.0'
    )

    db.session.commit()

    ActivityLog.log(
        event_type='email_unsubscribed',
        event_category='auth',
        user_id=user.id,
        description='User unsubscribed via email link',
        ip_address=ip_address,
        success=True
    )

    # Use USER_DOMAIN for user-facing links
    user_domain = current_app.config.get('USER_DOMAIN', '').strip()
    if not user_domain:
        user_domain = current_app.config.get('APP_URL', 'http://localhost:5000')
    if not user_domain.startswith('http'):
        user_domain = f"https://{user_domain}"
    return f'''<html><body style="background:#0f172a;color:#e2e8f0;font-family:sans-serif;text-align:center;padding:60px">
    <h1 style="color:#3b82f6">Unsubscribed</h1>
    <p>You have been successfully unsubscribed from GearCargo email notifications.</p>
    <p style="color:#94a3b8;margin-top:20px">You can re-enable notifications at any time in your
    <a href="{user_domain}/settings" style="color:#3b82f6">app settings</a>.</p>
    </body></html>''', 200


@auth_bp.route('/consent-history', methods=['GET'])
@token_required
def get_consent_history(current_user):
    """Return the user's own consent history (GDPR transparency)."""
    from app.models.email_consent_log import EmailConsentLog

    logs = EmailConsentLog.query.filter_by(user_id=current_user.id)\
        .order_by(EmailConsentLog.created_at.desc())\
        .limit(50)\
        .all()

    return jsonify({
        'consent_history': [log.to_dict() for log in logs]
    })

@auth_bp.route('/avatar', methods=['POST'])
@token_required
def upload_avatar(current_user):
    """Upload a new avatar image. Keeps history of previous avatars."""
    import os
    import uuid
    from werkzeug.utils import secure_filename
    
    # Security constants
    MAX_FILE_SIZE = 2 * 1024 * 1024  # 2MB max for avatars
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    ALLOWED_MIME_TYPES = {'image/png', 'image/jpeg', 'image/gif', 'image/webp'}
    IMAGE_SIGNATURES = {
        b'\xff\xd8\xff': 'jpg',
        b'\x89PNG\r\n\x1a\n': 'png',
        b'GIF87a': 'gif',
        b'GIF89a': 'gif',
    }
    MAX_AVATAR_HISTORY = 10  # Keep last 10 avatars
    
    if 'avatar' not in request.files:
        return jsonify({'error': 'No avatar file provided'}), 400
    
    avatar = request.files['avatar']
    
    if avatar.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    # Check file size
    avatar.seek(0, 2)
    size = avatar.tell()
    avatar.seek(0)
    
    if size > MAX_FILE_SIZE:
        return jsonify({'error': 'File too large. Maximum size is 2MB'}), 400
    
    # Validate file extension
    filename = secure_filename(avatar.filename)
    extension = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    
    if extension not in ALLOWED_EXTENSIONS:
        return jsonify({'error': f'Invalid file type. Allowed: {", ".join(ALLOWED_EXTENSIONS)}'}), 400
    
    # Validate MIME type
    if avatar.content_type not in ALLOWED_MIME_TYPES:
        return jsonify({'error': 'Invalid file type'}), 400
    
    # Validate actual file content (magic bytes)
    header = avatar.read(12)
    avatar.seek(0)
    detected_type = None
    for sig, img_type in IMAGE_SIGNATURES.items():
        if header.startswith(sig):
            detected_type = img_type
            break
    if header[:4] == b'RIFF' and header[8:12] == b'WEBP':
        detected_type = 'webp'
    
    if detected_type is None:
        return jsonify({'error': 'Invalid image file'}), 400
    
    # Create avatars directory
    avatar_dir = os.path.join(current_app.root_path, '..', 'uploads', 'avatars', str(current_user.id))
    os.makedirs(avatar_dir, mode=0o750, exist_ok=True)
    
    # Generate unique filename
    unique_filename = f"{uuid.uuid4().hex}.{detected_type}"
    file_path = os.path.join(avatar_dir, unique_filename)
    
    # Ensure file_path is within avatar_dir
    if not os.path.abspath(file_path).startswith(os.path.abspath(avatar_dir)):
        return jsonify({'error': 'Invalid file path'}), 400
    
    # Write new avatar to a temp path first — activated atomically after DB commit
    temp_path = file_path + '.tmp'
    try:
        avatar.save(temp_path)
        os.chmod(temp_path, 0o640)
    except OSError as e:
        current_app.logger.error(f"Failed to write avatar temp file for user {current_user.id}: {e}")
        return jsonify({'error': 'Failed to save avatar'}), 500

    # Compute URL and prepare updated history (in memory — no disk changes yet)
    avatar_url = f"/uploads/avatars/{current_user.id}/{unique_filename}"
    avatar_history = current_user.preferences.get('avatar_history', []) if current_user.preferences else []

    # Add current avatar to history if it exists and is not already recorded
    if current_user.avatar and current_user.avatar not in avatar_history:
        avatar_history.insert(0, current_user.avatar)

    # Identify old history files to prune — deletion deferred until after commit
    files_to_prune = []
    if len(avatar_history) > MAX_AVATAR_HISTORY:
        for old_url in avatar_history[MAX_AVATAR_HISTORY:]:
            old_filename = os.path.basename(old_url)
            old_path = os.path.join(avatar_dir, old_filename)
            if os.path.exists(old_path) and os.path.abspath(old_path).startswith(os.path.abspath(avatar_dir)):
                files_to_prune.append(old_path)
        avatar_history = avatar_history[:MAX_AVATAR_HISTORY]

    # Update user record in memory
    if not current_user.preferences:
        current_user.preferences = {}
    current_user.preferences = {**current_user.preferences, 'avatar_history': avatar_history}
    current_user.avatar = avatar_url

    # Commit DB — only activate the new file if this succeeds
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        try:
            os.remove(temp_path)
        except OSError:
            pass
        current_app.logger.error(f"DB commit failed during avatar upload for user {current_user.id}: {e}")
        return jsonify({'error': 'Failed to update avatar'}), 500

    # DB committed — atomically move temp file to its permanent name
    try:
        os.rename(temp_path, file_path)
    except OSError:
        import shutil
        try:
            shutil.move(temp_path, file_path)
        except OSError as e2:
            current_app.logger.error(
                f"Avatar file activation failed after successful DB commit for user {current_user.id}: {e2}. "
                f"Temp file left at {temp_path}"
            )

    # Prune old history files from disk only after the DB commit succeeded
    for old_path in files_to_prune:
        try:
            os.remove(old_path)
        except OSError:
            pass

    from app.utils import sign_upload_url
    return jsonify({
        'message': 'Avatar uploaded successfully',
        'avatar_url': sign_upload_url(avatar_url),
        'avatar_history': [sign_upload_url(u) for u in avatar_history]
    })


@auth_bp.route('/avatars', methods=['GET'])
@token_required
def get_avatars(current_user):
    """Get current avatar and avatar history."""
    from app.utils import sign_upload_url
    avatar_history = current_user.preferences.get('avatar_history', []) if current_user.preferences else []
    
    return jsonify({
        'current_avatar': sign_upload_url(current_user.avatar),
        'avatar_history': [sign_upload_url(u) for u in avatar_history]
    })


@auth_bp.route('/avatar/select', methods=['PUT'])
@token_required
def select_avatar(current_user):
    """Select an avatar from history as the current avatar."""
    import os
    from urllib.parse import urlparse
    
    data = request.get_json()
    avatar_url = data.get('avatar_url', '')
    
    # Strip any signed-URL query parameters so we store the raw path
    avatar_url = urlparse(avatar_url).path
    
    if not avatar_url:
        return jsonify({'error': 'Avatar URL is required'}), 400
    
    # Validate the URL belongs to this user
    expected_prefix = f"/uploads/avatars/{current_user.id}/"
    if not avatar_url.startswith(expected_prefix):
        return jsonify({'error': 'Invalid avatar URL'}), 400
    
    # Check if the file exists
    avatar_dir = os.path.join(current_app.root_path, '..', 'uploads', 'avatars', str(current_user.id))
    filename = os.path.basename(avatar_url)
    file_path = os.path.join(avatar_dir, filename)
    
    if not os.path.exists(file_path):
        return jsonify({'error': 'Avatar not found'}), 404
    
    # Update avatar history
    avatar_history = current_user.preferences.get('avatar_history', []) if current_user.preferences else []
    
    # Remove selected from history (it will become current)
    if avatar_url in avatar_history:
        avatar_history.remove(avatar_url)
    
    # Add current avatar to history
    if current_user.avatar and current_user.avatar not in avatar_history:
        avatar_history.insert(0, current_user.avatar)
    
    # Update preferences and current avatar
    if not current_user.preferences:
        current_user.preferences = {}
    current_user.preferences = {**current_user.preferences, 'avatar_history': avatar_history}
    current_user.avatar = avatar_url
    db.session.commit()
    
    from app.utils import sign_upload_url
    return jsonify({
        'message': 'Avatar selected successfully',
        'avatar_url': sign_upload_url(avatar_url),
        'avatar_history': [sign_upload_url(u) for u in avatar_history]
    })


@auth_bp.route('/avatar/<filename>', methods=['DELETE'])
@token_required
def delete_avatar(current_user, filename):
    """Delete an avatar from history."""
    import os
    from werkzeug.utils import secure_filename
    
    # Secure the filename
    safe_filename = secure_filename(filename)
    if safe_filename != filename:
        return jsonify({'error': 'Invalid filename'}), 400
    
    avatar_dir = os.path.join(current_app.root_path, '..', 'uploads', 'avatars', str(current_user.id))
    file_path = os.path.join(avatar_dir, safe_filename)
    
    # Ensure file_path is within avatar_dir
    if not os.path.abspath(file_path).startswith(os.path.abspath(avatar_dir)):
        return jsonify({'error': 'Invalid file path'}), 400
    
    avatar_url = f"/uploads/avatars/{current_user.id}/{safe_filename}"
    
    # Cannot delete current avatar
    if current_user.avatar == avatar_url:
        return jsonify({'error': 'Cannot delete current avatar. Select another avatar first.'}), 400
    
    # Remove from history
    avatar_history = current_user.preferences.get('avatar_history', []) if current_user.preferences else []
    if avatar_url in avatar_history:
        avatar_history.remove(avatar_url)
        if not current_user.preferences:
            current_user.preferences = {}
        current_user.preferences = {**current_user.preferences, 'avatar_history': avatar_history}
        db.session.commit()
    
    # Delete file
    if os.path.exists(file_path):
        os.remove(file_path)
    
    from app.utils import sign_upload_url
    return jsonify({
        'message': 'Avatar deleted successfully',
        'avatar_history': [sign_upload_url(u) for u in avatar_history]
    })


@auth_bp.route('/avatar', methods=['DELETE'])
@token_required
def remove_current_avatar(current_user):
    """Remove current avatar (set to no avatar)."""
    if not current_user.avatar:
        return jsonify({'error': 'No avatar to remove'}), 404
    
    # Move current avatar to history
    avatar_history = current_user.preferences.get('avatar_history', []) if current_user.preferences else []
    if current_user.avatar not in avatar_history:
        avatar_history.insert(0, current_user.avatar)
    
    # Update preferences
    if not current_user.preferences:
        current_user.preferences = {}
    current_user.preferences = {**current_user.preferences, 'avatar_history': avatar_history}
    
    # Clear current avatar
    current_user.avatar = None
    db.session.commit()
    
    from app.utils import sign_upload_url
    return jsonify({
        'message': 'Avatar removed successfully',
        'avatar_history': [sign_upload_url(u) for u in avatar_history]
    })


# ============================================================
# SECURITY QUESTIONS FOR ACCOUNT RECOVERY
# ============================================================

# Predefined security questions for consistency
SECURITY_QUESTIONS = [
    "What was the name of your first pet?",
    "What is your mother's maiden name?",
    "What was the name of your first school?",
    "In what city were you born?",
    "What is the name of your favorite childhood friend?",
    "What was your childhood nickname?",
    "What is your oldest sibling's middle name?",
    "What is the name of the first street you lived on?",
    "What was the make of your first car?",
    "What was your dream job as a child?",
    "What is your favorite movie?",
    "What was the first concert you attended?",
    "What is your favorite book?",
    "What is your favorite sports team?",
    "What was the name of your first employer?",
]


@auth_bp.route('/security-questions/available', methods=['GET'])
def get_available_security_questions():
    """Get list of available predefined security questions."""
    return jsonify({
        'questions': SECURITY_QUESTIONS
    })


@auth_bp.route('/security-questions', methods=['GET'])
@token_required
def get_user_security_questions(current_user):
    """Get user's configured security questions (without answers)."""
    if not current_user.has_security_questions():
        return jsonify({
            'configured': False,
            'questions': []
        })
    
    return jsonify({
        'configured': True,
        'questions': current_user.get_security_questions(),
        'set_at': current_user.security_questions_set_at.isoformat() if current_user.security_questions_set_at else None
    })


@auth_bp.route('/security-questions', methods=['POST'])
@token_required
def set_security_questions(current_user):
    """
    Set or update security questions for account recovery.
    Requires password verification.
    """
    data = request.get_json()
    
    password = data.get('password')
    questions = data.get('questions', [])  # [{question: str, answer: str}, ...]
    
    if not password or not current_user.check_password(password):
        return jsonify({'error': 'Password verification failed'}), 401
    
    # Require at least 2 questions
    if len(questions) < 2:
        return jsonify({'error': 'At least 2 security questions are required'}), 400
    
    # Validate each question has both fields
    for q in questions:
        if not q.get('question') or not q.get('answer'):
            return jsonify({'error': 'Each security question must have both question and answer'}), 400
        
        # Validate answer is meaningful (at least 2 characters)
        if len(q['answer'].strip()) < 2:
            return jsonify({'error': 'Answer must be at least 2 characters'}), 400
    
    # Check 2FA if enabled
    if current_user.two_factor_enabled:
        totp_code = data.get('totp_code')
        if not totp_code:
            return jsonify({
                'error': '2FA code required',
                'requires_2fa': True
            }), 401
        
        totp = pyotp.TOTP(_get_totp_secret(current_user))
        if not totp.verify(totp_code, valid_window=1):
            return jsonify({'error': 'Invalid 2FA code'}), 401
    
    # Set the security questions
    current_user.set_security_questions(questions)
    
    # Security audit log
    security_audit.log(
        security_audit.EVENT_PROFILE_UPDATED,
        user_id=current_user.id,
        user_email=current_user.email,
        details={'action': 'security_questions_set', 'question_count': len(questions)}
    )
    
    # Log activity
    ActivityLog.log(
        event_type='security_questions_set',
        event_category='auth',
        user_id=current_user.id,
        description=f'Security questions set for: {current_user.email}',
        success=True,
        extra_data={'question_count': len(questions)}
    )
    
    return jsonify({
        'message': 'Security questions set successfully',
        'question_count': len(questions)
    })


@auth_bp.route('/security-questions/first-time', methods=['POST'])
@token_required
def set_security_questions_first_time(current_user):
    """
    Set security questions for first-time setup (after forced password change).
    Does NOT require password re-entry since the user just authenticated.
    This endpoint should only be used right after password change flow.
    """
    data = request.get_json()
    
    questions = data.get('questions', [])  # [{question: str, answer: str}, ...]
    
    # Only allow if user doesn't already have security questions
    # This prevents abuse of the simpler endpoint
    if current_user.has_security_questions():
        return jsonify({'error': 'Security questions already configured. Use the regular endpoint to update.'}), 400
    
    # Require at least 2 questions
    if len(questions) < 2:
        return jsonify({'error': 'At least 2 security questions are required'}), 400
    
    # Validate each question has both fields
    for q in questions:
        if not q.get('question') or not q.get('answer'):
            return jsonify({'error': 'Each security question must have both question and answer'}), 400
        
        # Validate answer is meaningful (at least 2 characters)
        if len(q['answer'].strip()) < 2:
            return jsonify({'error': 'Answer must be at least 2 characters'}), 400
    
    # Set the security questions
    current_user.set_security_questions(questions)
    
    # Security audit log
    security_audit.log(
        security_audit.EVENT_PROFILE_UPDATED,
        user_id=current_user.id,
        user_email=current_user.email,
        details={'action': 'security_questions_first_time', 'question_count': len(questions)}
    )
    
    # Log activity
    ActivityLog.log(
        event_type='security_questions_set',
        event_category='auth',
        user_id=current_user.id,
        description=f'Security questions set (first time) for: {current_user.email}',
        success=True,
        extra_data={'question_count': len(questions), 'first_time': True}
    )
    
    return jsonify({
        'message': 'Security questions set successfully',
        'question_count': len(questions)
    })


@auth_bp.route('/password/recover/questions', methods=['POST'])
def get_recovery_questions():
    """
    Get security questions for an email address (for password recovery).
    Rate limited to prevent enumeration.
    """
    data = request.get_json()
    email = data.get('email', '').lower().strip()
    
    if not email:
        return jsonify({'error': 'Email is required'}), 400
    
    user = User.query.filter_by(email=email).first()
    
    # Always return same structure to prevent user enumeration
    if not user or not user.has_security_questions():
        # Add small delay to make timing attacks harder
        import time
        time.sleep(0.3)
        return jsonify({
            'available': False,
            'message': 'Security questions not available for this account'
        })
    
    return jsonify({
        'available': True,
        'questions': user.get_security_questions()
    })


@auth_bp.route('/password/recover/verify-answers', methods=['POST'])
def verify_recovery_answers():
    """
    Verify security question answers and issue a password reset token.
    Rate limited to prevent brute force attacks.

    S21: Two independent Redis counters protect this endpoint:
      1. Per-email counter  ``security_answer_attempts:{email}``    — max 5 per 15 min.
         Prevents exhaustive enumeration of answers for a *specific* account.
      2. Per-IP counter     ``security_answer_attempts:ip:{ip}``    — max 20 per 15 min.
         Prevents an attacker with N target accounts from making 5×N attempts from
         a single IP by cycling through accounts (bypassing the per-email limit).
    Both counters are incremented on *every* failed verification (including
    non-existent users) and cleared for the email counter on success.
    """
    data = request.get_json()
    email = data.get('email', '').lower().strip()
    answers = data.get('answers', [])  # List of answers in order
    
    if not email or not answers:
        return jsonify({'error': 'Email and answers are required'}), 400
    
    client_ip = get_real_client_ip()

    # --- S21: per-IP rate check (20 attempts / 15 min across all target emails) ---
    ip_attempts_key = f'security_answer_attempts:ip:{client_ip}'
    if redis_client:
        try:
            ip_attempts = redis_client.get(ip_attempts_key)
            if ip_attempts and int(ip_attempts) >= 20:
                current_app.logger.warning(
                    f"[Security] Security-question IP lockout: {client_ip} reached 20 attempts"
                )
                return jsonify({
                    'error': 'Too many failed attempts. Please try again later.',
                    'locked': True
                }), 429
        except Exception as e:
            current_app.logger.error(f"Redis error checking IP answer attempts: {e}")

    # --- Per-email rate check (5 attempts / 15 min for this specific account) ---
    attempts_key = f'security_answer_attempts:{email}'
    if redis_client:
        try:
            attempts = redis_client.get(attempts_key)
            if attempts and int(attempts) >= 5:
                return jsonify({
                    'error': 'Too many failed attempts. Please try again later.',
                    'locked': True
                }), 429
        except Exception as e:
            current_app.logger.error(f"Redis error checking answer attempts: {e}")
    
    user = User.query.filter_by(email=email).first()
    
    if not user:
        # Record attempt even for non-existent users (prevents enumeration).
        # S21: increment both counters so IP-cycling through fake emails still
        # burns the IP's global budget.
        if redis_client:
            try:
                redis_client.incr(attempts_key)
                redis_client.expire(attempts_key, 900)  # 15 min lockout
                redis_client.incr(ip_attempts_key)
                redis_client.expire(ip_attempts_key, 900)
            except:
                pass
        return jsonify({'error': 'Verification failed'}), 401
    
    if not user.has_security_questions():
        return jsonify({'error': 'Security questions not configured'}), 400
    
    # Verify the answers
    if not user.verify_security_answers(answers):
        # Record failed attempt — both email and IP counters (S21).
        if redis_client:
            try:
                redis_client.incr(attempts_key)
                redis_client.expire(attempts_key, 900)
                redis_client.incr(ip_attempts_key)
                redis_client.expire(ip_attempts_key, 900)
            except:
                pass
        
        # Log failed verification
        security_audit.log(
            security_audit.EVENT_PASSWORD_RESET_REQUEST,
            user_id=user.id,
            user_email=user.email,
            success=False,
            details={'method': 'security_questions', 'reason': 'wrong_answers'}
        )
        
        return jsonify({'error': 'One or more answers are incorrect'}), 401
    
    # Clear failed attempts on success (email counter only — IP counter is not
    # cleared on success to prevent using a valid account as a "reset token"
    # to clear the IP budget after burning attempts on other accounts).
    if redis_client:
        try:
            redis_client.delete(attempts_key)
        except:
            pass
    
    # Generate a one-time password reset token
    reset_token = user.generate_reset_token(expires_hours=1)  # Only 1 hour for security question recovery
    
    # Log successful security question verification
    security_audit.log(
        security_audit.EVENT_PASSWORD_RESET_REQUEST,
        user_id=user.id,
        user_email=user.email,
        success=True,
        details={'method': 'security_questions'}
    )
    
    return jsonify({
        'success': True,
        'message': 'Security questions verified. You can now reset your password.',
        'reset_token': reset_token,
        'expires_in': 3600  # 1 hour
    })


@auth_bp.route('/password/recover/reset', methods=['POST'])
def reset_password_with_token():
    """
    Reset password using the token from security question verification.
    """
    data = request.get_json()
    reset_token = data.get('reset_token')
    new_password = data.get('new_password')
    confirm_password = data.get('confirm_password')
    
    if not reset_token or not new_password:
        return jsonify({'error': 'Reset token and new password are required'}), 400
    
    if confirm_password and new_password != confirm_password:
        return jsonify({'error': 'Passwords do not match'}), 400
    
    user = User.verify_reset_token(reset_token)
    if not user:
        return jsonify({'error': 'Invalid or expired reset token'}), 401
    
    # Validate password strength
    is_valid, errors, score, strength = validate_password_strength(new_password)
    
    if not is_valid:
        return jsonify({
            'error': errors[0] if errors else 'Password is too weak',
            'password_errors': errors,
            'strength_score': score,
            'strength': strength
        }), 400
    
    # Set the new password
    user.set_password(new_password)
    user.password_reset_token = None
    user.password_reset_expires = None
    user.must_change_password = False
    db.session.commit()
    
    # Invalidate all existing sessions for security
    invalidate_user_sessions(user.id)
    
    # Log password reset
    security_audit.log(
        security_audit.EVENT_PASSWORD_RESET_COMPLETE,
        user_id=user.id,
        user_email=user.email,
        details={'method': 'security_questions'}
    )
    
    security_audit.password_change(user.id, user.email, success=True)
    
    ActivityLog.log(
        event_type='password_reset',
        event_category='auth',
        user_id=user.id,
        description=f'Password reset via security questions: {user.email}',
        success=True
    )
    
    return jsonify({
        'message': 'Password reset successfully. Please login with your new password.',
        'strength': strength
    })

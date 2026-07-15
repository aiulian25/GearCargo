"""
GearCargo - Ollama API helper (Sections 3.11 / 3.12 / 3.14)

Single entry-point for every Ollama call in the codebase.
Provides model resolution and the chat/generate helper.

Model resolution (resolve_model)
---------------------------------
Order (highest → lowest priority):
  1. DB app_settings row for the task   (e.g. 'ollama_model_predict')
  2. Task-specific env / config var     (e.g. OLLAMA_MODEL_PREDICT)
  3. DB app_settings row for global     ('ollama_model_global')
  4. Global OLLAMA_MODEL config var
  5. Empty string → chat() raises OllamaError asking admin to configure a model

No model name is ever hardcoded here.  The user is fully in charge.

Chat / Generate strategy (chat)
---------------------------------
Prefer POST /api/chat with a JSON-schema ``format`` object (Ollama ≥ 0.3).
Falls back to POST /api/generate with ``"format": "json"`` on HTTP 404.
Returns a parsed dict — callers never need json.loads().

Security
---------
* validate_ollama_url() is the single authoritative SSRF guard for every call.
* No user content is embedded here — prompts are built by callers.
"""

import ipaddress
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)


class OllamaError(Exception):
    """Raised when Ollama returns a non-2xx status, a network error,
    or when no model is configured."""


# ---------------------------------------------------------------------------
# SSRF guard — canonical Ollama URL validator
# ---------------------------------------------------------------------------

# IP ranges that must never be reachable via an Ollama call, regardless of
# who configured the URL.  We intentionally allow:
#   • loopback (127.x) — local Ollama installations
#   • RFC-1918 private (10.x, 172.16-31.x, 192.168.x) — LAN Ollama
# because those are the two most common real-world deployments.
# We DO block:
#   • link-local (169.254.x.x) — cloud metadata endpoints
#     (AWS 169.254.169.254, GCP, Azure, etc.)
#   • multicast (224-239.x.x.x) — not a valid server address
#   • reserved / unspecified (0.0.0.0, 240-255.x.x.x)
_OLLAMA_BLOCKED_IP_RANGES = (
    ipaddress.ip_network('169.254.0.0/16'),   # link-local / cloud metadata
    ipaddress.ip_network('100.64.0.0/10'),    # shared address space (Alibaba metadata)
    ipaddress.ip_network('224.0.0.0/4'),      # IPv4 multicast
    ipaddress.ip_network('240.0.0.0/4'),      # IPv4 reserved / future use
    ipaddress.ip_network('0.0.0.0/8'),        # unspecified / "this" network
    ipaddress.ip_network('fe80::/10'),        # IPv6 link-local
    ipaddress.ip_network('ff00::/8'),         # IPv6 multicast
)


def validate_ollama_url(url: str) -> str:
    """Validate the configured Ollama base URL against SSRF and misconfiguration.

    This is the **single authoritative validator** for every Ollama HTTP call in
    the codebase.  All call sites must use this function instead of writing their
    own inline checks.

    Allowed
    -------
    * ``http://`` and ``https://`` schemes (Ollama usually serves plain HTTP)
    * Loopback hostnames / IPs (``localhost``, ``127.x.x.x``) — local Ollama
    * RFC-1918 private IPs (``10.x``, ``172.16-31.x``, ``192.168.x``) — LAN Ollama
    * Hostname-based URLs (``host.docker.internal``, custom DNS) — safe; DNS
      rebinding is mitigated at the network-egress / firewall layer

    Blocked
    -------
    * Missing / non-http(s) scheme
    * Missing ``netloc``
    * Embedded credentials (``user:pass@host``)
    * IP literals in link-local (169.254.0.0/16), cloud shared-space
      (100.64.0.0/10), multicast, reserved, or unspecified ranges — these
      cover every known cloud metadata endpoint

    Transport (§14.2)
    -----------------
    This guards the URL (scheme/host/SSRF) but cannot enforce transport security.
    Ollama has no auth by default and the prompt carries user data, so for a
    REMOTE Ollama use **https + a private network** (VPN/WireGuard/VLAN) or a
    TLS reverse proxy with auth, and never expose port 11434 publicly. Startup
    logs a warning if the URL is plain http to a public IP.

    Parameters
    ----------
    url : str
        Raw URL string to validate (typically from ``app.config``).

    Returns
    -------
    str
        The URL unchanged if it passes all checks.

    Raises
    ------
    ValueError
        Descriptive message explaining the specific violation.
    """
    if not url:
        raise ValueError('Ollama URL is not configured')
    try:
        parsed = urlparse(url)
    except Exception as exc:
        raise ValueError(f'Ollama URL is malformed: {exc}') from exc

    if parsed.scheme not in ('http', 'https'):
        raise ValueError(
            f'Ollama URL scheme must be http or https, got: {parsed.scheme!r}'
        )
    host = (parsed.hostname or '').lower()
    if not host:
        raise ValueError('Ollama URL must include a host')
    if parsed.username or parsed.password:
        raise ValueError('Ollama URL must not contain embedded credentials')

    # Block IP literals that fall within SSRF-dangerous ranges.
    # Hostname-based URLs (e.g. "localhost", "host.docker.internal") are
    # resolved at request time via the system resolver and are not blocked here;
    # DNS rebinding is a network-egress concern, not a URL-validation concern.
    try:
        addr = ipaddress.ip_address(host)
        for blocked in _OLLAMA_BLOCKED_IP_RANGES:
            if addr in blocked:
                raise ValueError(
                    f'Ollama URL points to a blocked IP range ({host}). '
                    'Use a hostname or a non-restricted IP address.'
                )
    except ValueError as exc:
        if 'blocked IP range' in str(exc):
            raise
        # Not an IP literal (hostname) — allowed
    return url


# ---------------------------------------------------------------------------
# Redis AI cache
# ---------------------------------------------------------------------------

# Default TTLs (seconds) per AI task.
# Prediction / reminder caches are invalidated implicitly via data fingerprints
# embedded in the cache key, so old keys expire naturally; the TTL is a safety net.
AI_CACHE_TTL: dict[str, int] = {
    'predict':  86_400,   # 24 h — re-computed only when new entries arrive
    'anomaly':  604_800,  # 7 d  — per-entry; the entry never changes
    'ocr':      604_800,  # 7 d  — per-attachment file; files are immutable
    'reminder': 3_600,    # 1 h  — service history changes relatively often
}

_CACHE_PREFIX = 'ai_cache:'


def _get_redis():
    """Safely obtain the app-level Redis client (may be None if Redis is down)."""
    try:
        from app import redis_client  # noqa: PLC0415
        return redis_client
    except Exception:
        return None


def ai_cache_get(key: str) -> dict | None:
    """Return a cached dict from Redis, or ``None`` on miss / error.

    All exceptions are swallowed — a cache miss is always the safe fallback.
    """
    r = _get_redis()
    if not r:
        return None
    try:
        raw = r.get(key)
        if raw:
            logger.debug('AI cache HIT  key=%s', key)
            return json.loads(raw)
    except Exception as exc:
        logger.debug('AI cache GET error (ignored): %s', exc)
    return None


def ai_cache_set(key: str, data: dict, ttl: int = AI_CACHE_TTL['predict']) -> None:
    """Persist *data* in Redis under *key* with a TTL.

    All exceptions are swallowed — a write failure is always the safe fallback.
    """
    r = _get_redis()
    if not r:
        return
    try:
        r.setex(key, ttl, json.dumps(data, default=str))
        logger.debug('AI cache SET   key=%s  ttl=%ds', key, ttl)
    except Exception as exc:
        logger.debug('AI cache SET error (ignored): %s', exc)


def ai_cache_flush(pattern: str = f'{_CACHE_PREFIX}*') -> int:
    """Delete all AI cache keys matching *pattern*.

    Returns the number of keys deleted, or 0 on error / unavailability.
    This is intended for the admin "Flush AI Cache" action.

    Uses SCAN instead of KEYS to avoid blocking the Redis server on large
    key-spaces.
    """
    r = _get_redis()
    if not r:
        return 0
    deleted = 0
    try:
        cursor = 0
        while True:
            cursor, keys = r.scan(cursor, match=pattern, count=100)
            if keys:
                deleted += r.delete(*keys)
            if cursor == 0:
                break
    except Exception as exc:
        logger.warning('AI cache flush error: %s', exc)
    return deleted


def ai_cache_stats() -> dict[str, Any]:
    """Return basic AI cache statistics for the admin panel.

    Uses SCAN to count matching keys without blocking Redis.
    """
    r = _get_redis()
    if not r:
        return {'available': False, 'keys': 0}
    try:
        count = 0
        cursor = 0
        while True:
            cursor, keys = r.scan(cursor, match=f'{_CACHE_PREFIX}*', count=100)
            count += len(keys)
            if cursor == 0:
                break
        return {'available': True, 'keys': count}
    except Exception:
        return {'available': False, 'keys': 0}


# ---------------------------------------------------------------------------
# Ollama connectivity / downtime tracking
# ---------------------------------------------------------------------------

_OLLAMA_OFFLINE_KEY = 'ollama:offline_since'
_OLLAMA_LAST_FAILURE_KEY = 'ollama:last_failure'   # refreshed on EVERY failure
_OLLAMA_PROBE_LOCK_KEY = 'ollama:probe_lock'       # single half-open probe slot
# Keep the marker for up to 4 h after the last failure so the admin banner
# survives a short Redis restart; cleared immediately on any successful call.
_OLLAMA_OFFLINE_TTL = 14_400   # 4 h
# Half-open breaker (self-heal): after this many seconds since the LAST
# failure, exactly one request is allowed through to probe Ollama.
_OLLAMA_PROBE_COOLDOWN = 120
# Probe-slot TTL must outlive the worst-case probe (default 300 s read
# timeout) so a hung probe can't be joined by a second one.
_OLLAMA_PROBE_LOCK_TTL = 330


def ollama_record_failure() -> None:
    """Record that Ollama is unreachable right now.

    Uses SETNX so the *first* failure timestamp is preserved (admin banner);
    a separate last-failure key is refreshed every time (probe cooldown).
    TTLs are refreshed each time so the keys survive repeated failures.
    Cleared immediately by ``ollama_record_success()`` on any live response.
    All exceptions are swallowed — tracking is best-effort.
    """
    r = _get_redis()
    if not r:
        return
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        # Only set if not already present (preserve first-failure timestamp)
        r.setnx(_OLLAMA_OFFLINE_KEY, now_iso)
        r.expire(_OLLAMA_OFFLINE_KEY, _OLLAMA_OFFLINE_TTL)
        # Last failure — restarts the probe cooldown window.
        r.set(_OLLAMA_LAST_FAILURE_KEY, now_iso, ex=_OLLAMA_OFFLINE_TTL)
        # The failed attempt (probe or otherwise) is finished — free the slot
        # so the NEXT cooldown expiry can probe again.
        r.delete(_OLLAMA_PROBE_LOCK_KEY)
    except Exception as exc:
        logger.debug('ollama_record_failure Redis error (ignored): %s', exc)


def ollama_record_success() -> None:
    """Record that Ollama is reachable — clear all breaker state.

    All exceptions are swallowed — tracking is best-effort.
    """
    r = _get_redis()
    if not r:
        return
    try:
        r.delete(_OLLAMA_OFFLINE_KEY, _OLLAMA_LAST_FAILURE_KEY, _OLLAMA_PROBE_LOCK_KEY)
    except Exception as exc:
        logger.debug('ollama_record_success Redis error (ignored): %s', exc)


def ollama_breaker_allows_probe() -> bool:
    """Half-open circuit breaker: may THIS request probe a down Ollama?

    Called only when the breaker is open (``ollama_downtime_info()['down']``).
    Returns True for exactly ONE request once ``_OLLAMA_PROBE_COOLDOWN`` has
    passed since the last recorded failure — that request proceeds normally
    and its own success/failure updates the breaker (``chat()`` already calls
    ``ollama_record_success``/``ollama_record_failure``). Every other request
    keeps fast-failing, so a burst can never stampede a down Ollama and starve
    the worker pool (§14.4). Previously the breaker could only be cleared by
    an unrelated successful Ollama call or the 4 h TTL.
    """
    r = _get_redis()
    if not r:
        return True   # no Redis → no breaker state (down is never True anyway)
    try:
        raw = r.get(_OLLAMA_LAST_FAILURE_KEY)
        if raw:
            last_str = raw.decode() if isinstance(raw, bytes) else str(raw)
            last_dt = datetime.fromisoformat(last_str)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds()
            if elapsed < _OLLAMA_PROBE_COOLDOWN:
                return False
        # Cooldown elapsed (or legacy marker with no last-failure key, e.g.
        # written before this feature deployed) — claim the single probe slot.
        return bool(r.set(_OLLAMA_PROBE_LOCK_KEY,
                          datetime.now(timezone.utc).isoformat(),
                          nx=True, ex=_OLLAMA_PROBE_LOCK_TTL))
    except Exception as exc:
        logger.debug('ollama_breaker_allows_probe Redis error (ignored): %s', exc)
        return False  # conservative: keep fast-failing on breaker-state errors


def ollama_downtime_info() -> dict[str, Any]:
    """Return current Ollama downtime information.

    Returns
    -------
    dict
        ``{'down': bool, 'since': str | None, 'duration_min': int | None}``

        *down* is ``True`` only if a failure was recorded and not yet cleared.
        *since* is an ISO-8601 string of the first failure timestamp.
        *duration_min* is whole minutes since first failure.
    """
    r = _get_redis()
    if not r:
        return {'down': False, 'since': None, 'duration_min': None}
    try:
        raw = r.get(_OLLAMA_OFFLINE_KEY)
        if not raw:
            return {'down': False, 'since': None, 'duration_min': None}
        since_str = raw.decode() if isinstance(raw, bytes) else str(raw)
        since_dt = datetime.fromisoformat(since_str)
        if since_dt.tzinfo is None:
            since_dt = since_dt.replace(tzinfo=timezone.utc)
        duration_min = int((datetime.now(timezone.utc) - since_dt).total_seconds() / 60)
        return {'down': True, 'since': since_str, 'duration_min': duration_min}
    except Exception as exc:
        logger.debug('ollama_downtime_info Redis error (ignored): %s', exc)
        return {'down': False, 'since': None, 'duration_min': None}




def resolve_model(task_key: str, config: Any) -> str:
    """Return the configured model name for *task_key*.

    Parameters
    ----------
    task_key : str
        One of ``'predict'``, ``'ocr'``, ``'anomaly'``, ``'reminder'``,
        ``'chat'``.  May also be ``'global'`` to read the global override.
    config : dict-like
        Flask ``app.config`` or ``current_app.config``.

    Returns
    -------
    str
        Model name, or empty string if nothing is configured anywhere.
        Callers should pass the result directly to ``chat()`` — an empty
        string will raise ``OllamaError`` with a clear message asking the
        admin to configure a model.
    """
    try:
        from app.models.app_setting import AppSetting  # noqa: PLC0415

        # 1. Task-specific DB setting
        db_task = AppSetting.get(f'ollama_model_{task_key}')
        if db_task:
            return db_task

        # 2. Task-specific env / config var
        env_task = (config.get(f'OLLAMA_MODEL_{task_key.upper()}') or '').strip()
        if env_task:
            return env_task

        # 3. Global DB setting (admin UI "Default model")
        db_global = AppSetting.get('ollama_model_global')
        if db_global:
            return db_global

    except Exception:
        # DB may not be ready during migrations or tests — fall through.
        pass

    # 4. Global env var (may be empty — that is intentional)
    return (config.get('OLLAMA_MODEL') or '').strip()


# ---------------------------------------------------------------------------
# Ollama HTTP call
# ---------------------------------------------------------------------------

# Default connect timeout (seconds) for the backend→Ollama hop. Kept short so a
# dead/unrouteable remote machine fails in seconds instead of holding a sync
# gunicorn worker for the full read window (§14.3).
_DEFAULT_CONNECT_TIMEOUT = 5

# §14.5 — keep-alive HTTP session for the (often remote/https) Ollama hop, so we
# skip repeated TCP/TLS setup on every cross-machine call. Lazily created and
# keyed by PID: with gunicorn preload_app=True the app is forked into workers,
# and a Session/socket pool created in the master must NOT be shared across
# forked processes — re-creating per PID gives each worker its own pool.
_session = None
_session_pid = None


def _get_session():
    """Return a per-process keep-alive requests Session (fork-safe)."""
    global _session, _session_pid
    pid = os.getpid()
    if _session is None or _session_pid != pid:
        _session = requests.Session()
        _session_pid = pid
    return _session


def _ollama_post(url: str, payload: dict, connect_timeout: float, read_timeout: float):
    """POST to Ollama with a (connect, read) timeout and bounded retry (§14.3/14.5).

    - **Connect** errors (dead/unrouteable remote, incl. ConnectTimeout) are
      retried **once**, then trip the circuit breaker (`ollama_record_failure`).
    - **Read** timeouts are **never retried** and do **not** trip the breaker —
      the remote is reachable but slow (retrying just doubles the worker hold).
    Returns the ``requests.Response`` (caller inspects status); raises
    ``OllamaError`` on network failure.
    """
    attempts = 0
    while True:
        attempts += 1
        try:
            return _get_session().post(url, json=payload, timeout=(connect_timeout, read_timeout))
        except requests.ReadTimeout as exc:
            # Reachable but slow — do not retry, do not trip the breaker.
            raise OllamaError(f'Ollama read timed out after {read_timeout}s: {exc}') from exc
        except requests.ConnectionError as exc:
            # Connect-level failure (includes ConnectTimeout). Retry once.
            if attempts < 2:
                logger.debug('Ollama connect error (attempt %d) — retrying once: %s', attempts, exc)
                continue
            ollama_record_failure()
            raise OllamaError(f'Ollama connection error: {exc}') from exc
        except requests.RequestException as exc:
            ollama_record_failure()
            raise OllamaError(f'Ollama request error: {exc}') from exc


def chat(
    base_url: str,
    model: str,
    prompt: str,
    schema: dict | None = None,
    timeout: int = 120,
    options: dict | None = None,
    connect_timeout: float = _DEFAULT_CONNECT_TIMEOUT,
) -> dict[str, Any]:
    """Call Ollama and return a parsed dict.

    Parameters
    ----------
    base_url : str
        Pre-validated Ollama base URL.
    model : str
        Model name — must NOT be empty (use ``resolve_model()`` to obtain it).
    prompt : str
        Full prompt text, already sanitised by the caller.
    schema : dict | None
        Optional JSON-Schema dict for structured output enforcement.
    timeout : int
        **Read** timeout in seconds (how long to wait for the model's response).
    options : dict | None
        Optional Ollama generation options (e.g. ``{'temperature': 0.3}``).
        Lower temperature makes the model less likely to "creatively" escape
        guardrails. Applied to both the /api/chat and /api/generate paths.
    connect_timeout : float
        **Connect** timeout in seconds for the (often remote) Ollama hop. Kept
        short so a dead/unrouteable remote fails fast instead of holding a sync
        worker for the whole read window (§14.3).

    Returns
    -------
    dict
        Parsed JSON dict.

    Raises
    ------
    OllamaError
        Empty model name, HTTP errors, or network failures.
    """
    if not model or not model.strip():
        raise OllamaError(
            'No AI model is configured. '
            'Please select a model in Admin → AI Settings → Task Model Assignment.'
        )

    base_url = base_url.rstrip('/')

    # ------------------------------------------------------------------
    # 1. Try POST /api/chat with JSON schema enforcement (Ollama ≥ 0.3)
    # ------------------------------------------------------------------
    if schema is not None:
        payload: dict[str, Any] = {
            'model': model,
            'messages': [{'role': 'user', 'content': prompt}],
            'stream': False,
            'format': schema,
        }
        if options:
            payload['options'] = options
        # _ollama_post handles connect/read timeouts, the single connect-retry,
        # and breaker-on-connect-failure; it raises OllamaError on network error.
        resp = _ollama_post(f'{base_url}/api/chat', payload, connect_timeout, timeout)
        # We got an HTTP response → the remote is reachable; heal the breaker.
        ollama_record_success()
        if resp.status_code == 200:
            content = resp.json().get('message', {}).get('content', '{}')
            try:
                return json.loads(content) if isinstance(content, str) else content
            except (json.JSONDecodeError, ValueError):
                logger.warning('Ollama chat response was not valid JSON despite schema; falling back')
        elif resp.status_code == 404:
            logger.debug('Ollama /api/chat returned 404; falling back to /api/generate')
        else:
            raise OllamaError(
                f'Ollama /api/chat returned HTTP {resp.status_code}: {resp.text[:200]}'
            )

    # ------------------------------------------------------------------
    # 2. Fallback: POST /api/generate with format="json"
    # ------------------------------------------------------------------
    gen_payload: dict[str, Any] = {
        'model': model,
        'prompt': prompt,
        'stream': False,
        'format': 'json',
    }
    if options:
        gen_payload['options'] = options
    resp = _ollama_post(f'{base_url}/api/generate', gen_payload, connect_timeout, timeout)
    # Reachable (any HTTP response) → heal the breaker before inspecting status.
    ollama_record_success()
    if resp.status_code != 200:
        raise OllamaError(
            f'Ollama /api/generate returned HTTP {resp.status_code}: {resp.text[:200]}'
        )
    raw = resp.json().get('response', '{}')
    try:
        return json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, ValueError):
        logger.warning('Ollama /api/generate returned non-JSON despite format=json')
        return {}

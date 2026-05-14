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
# Keep the marker for up to 4 h after the last failure so the admin banner
# survives a short Redis restart; cleared immediately on any successful call.
_OLLAMA_OFFLINE_TTL = 14_400   # 4 h


def ollama_record_failure() -> None:
    """Record that Ollama is unreachable right now.

    Uses SETNX so the *first* failure timestamp is preserved.
    TTL is refreshed each time so the key survives repeated failures.
    Cleared immediately by ``ollama_record_success()`` on any live response.
    All exceptions are swallowed — tracking is best-effort.
    """
    r = _get_redis()
    if not r:
        return
    try:
        # Only set if not already present (preserve first-failure timestamp)
        r.setnx(_OLLAMA_OFFLINE_KEY, datetime.now(timezone.utc).isoformat())
        r.expire(_OLLAMA_OFFLINE_KEY, _OLLAMA_OFFLINE_TTL)
    except Exception as exc:
        logger.debug('ollama_record_failure Redis error (ignored): %s', exc)


def ollama_record_success() -> None:
    """Record that Ollama is reachable — clear any stored downtime marker.

    All exceptions are swallowed — tracking is best-effort.
    """
    r = _get_redis()
    if not r:
        return
    try:
        r.delete(_OLLAMA_OFFLINE_KEY)
    except Exception as exc:
        logger.debug('ollama_record_success Redis error (ignored): %s', exc)


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

def chat(
    base_url: str,
    model: str,
    prompt: str,
    schema: dict | None = None,
    timeout: int = 120,
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
        HTTP timeout in seconds.

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
        try:
            resp = requests.post(
                f'{base_url}/api/chat',
                json=payload,
                timeout=timeout,
            )
            if resp.status_code == 404:
                logger.debug('Ollama /api/chat returned 404; falling back to /api/generate')
            elif resp.status_code == 200:
                content = resp.json().get('message', {}).get('content', '{}')
                try:
                    return json.loads(content) if isinstance(content, str) else content
                except (json.JSONDecodeError, ValueError):
                    logger.warning('Ollama chat response was not valid JSON despite schema; falling back')
            else:
                # HTTP error from reachable server — still reachable, clear offline marker
                ollama_record_success()
                raise OllamaError(
                    f'Ollama /api/chat returned HTTP {resp.status_code}: {resp.text[:200]}'
                )
        except requests.RequestException as exc:
            # Network error — Ollama is unreachable
            ollama_record_failure()
            raise OllamaError(f'Ollama /api/chat network error: {exc}') from exc

    # ------------------------------------------------------------------
    # 2. Fallback: POST /api/generate with format="json"
    # ------------------------------------------------------------------
    try:
        resp = requests.post(
            f'{base_url}/api/generate',
            json={
                'model': model,
                'prompt': prompt,
                'stream': False,
                'format': 'json',
            },
            timeout=timeout,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        # Network error — Ollama is unreachable
        ollama_record_failure()
        raise OllamaError(f'Ollama /api/generate network error: {exc}') from exc

    # Successful response from /api/generate — clear any offline marker
    ollama_record_success()
    raw = resp.json().get('response', '{}')
    try:
        return json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, ValueError):
        logger.warning('Ollama /api/generate returned non-JSON despite format=json')
        return {}

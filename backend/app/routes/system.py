"""System / build-metadata endpoint.

Exposes the image's build manifest (baked at Docker build time into
``/app/build-info.json``) so the running PWA can detect a newer published build
and tell a feature update (``git_sha`` changed) apart from a weekly OS-security
rebuild (same ``git_sha``, newer ``build_date``).

When ``UPDATE_CHECK_ENABLED`` is set, the response also carries ``latest_release``
— the newest version published on GitHub — so version-pinned deployments (which
never see the git_sha/build_date change) can still surface that a newer release
exists. This is opt-in to preserve the default no-phone-home posture.

Authenticated on purpose: build/package details are only returned to signed-in
users, so anonymous scanners can't fingerprint the exact OS package versions.
"""
import os
import re
import json
import time

import requests
from flask import Blueprint, jsonify, current_app

from app.routes.auth import token_required

system_bp = Blueprint('system', __name__)

# Parsed once per process — the manifest is static for the life of the container.
_BUILD_INFO_CACHE = None

# GitHub latest-release cache. Server-side so GitHub is queried at most a few
# times a day regardless of how many clients poll /api/app-version.
_GITHUB_API = 'https://api.github.com'
_RELEASE_REPO_RE = re.compile(r'^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$')
_RELEASE_TTL = 6 * 3600          # cache a successful lookup for 6h
_RELEASE_TTL_MISS = 900          # cache a failure for 15 min (avoid hammering)
_release_fallback = {'ts': 0.0, 'data': None}   # in-process fallback when no Redis


def _load_build_info():
    global _BUILD_INFO_CACHE
    if _BUILD_INFO_CACHE is not None:
        return _BUILD_INFO_CACHE

    path = os.environ.get('BUILD_INFO_PATH', '/app/build-info.json')
    # Dev / missing file → neutral defaults so the frontend reads "up to date".
    data = {'version': '0.0.0', 'git_sha': 'dev', 'build_date': '', 'patched_packages': []}
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            loaded = json.load(fh)
        if isinstance(loaded, dict):
            data = {
                'version': str(loaded.get('version') or '0.0.0'),
                'git_sha': str(loaded.get('git_sha') or 'dev'),
                'build_date': str(loaded.get('build_date') or ''),
                'patched_packages': [str(p) for p in (loaded.get('patched_packages') or [])][:120],
            }
    except (FileNotFoundError, ValueError, OSError):
        pass

    _BUILD_INFO_CACHE = data
    return data


def _get_redis():
    """Shared app Redis client, or None (imported lazily like other routes)."""
    try:
        from app import redis_client
        return redis_client
    except Exception:
        return None


def _fetch_latest_release():
    """Return ``{'version', 'url', 'published_at'}`` for the configured repo's
    latest GitHub release, or ``None``.

    Server-side and heavily cached (Redis preferred, else a per-process fallback).
    Never raises — any failure degrades to ``None`` so the update UI simply omits
    the "newer release" hint. The only host contacted is api.github.com and the
    repo comes from config (validated), never from user input, so there is no
    SSRF surface.
    """
    repo = current_app.config.get('UPDATE_CHECK_REPO', '') or ''
    if not _RELEASE_REPO_RE.match(repo):
        return None

    key = f'latest_release:{repo}'
    now = time.time()
    rc = _get_redis()

    # --- cache read ---
    if rc is not None:
        try:
            raw = rc.get(key)
            if raw is not None:
                return json.loads(raw) or None
        except Exception:
            pass
    elif _release_fallback['data'] is not None and now - _release_fallback['ts'] < _RELEASE_TTL:
        return _release_fallback['data']

    # --- miss → query GitHub ---
    data = None
    try:
        resp = requests.get(
            f'{_GITHUB_API}/repos/{repo}/releases/latest',
            headers={'Accept': 'application/vnd.github+json',
                     'User-Agent': 'GearCargo-update-check'},
            timeout=5,
        )
        if resp.status_code == 200:
            j = resp.json()
            tag = (j.get('tag_name') or '').lstrip('vV')
            if tag:
                data = {
                    'version': tag,
                    'url': j.get('html_url') or '',
                    'published_at': j.get('published_at') or '',
                }
    except Exception as e:
        current_app.logger.debug(f'latest-release check failed: {e}')

    # --- cache write (short TTL on failure so we retry sooner) ---
    ttl = _RELEASE_TTL if data else _RELEASE_TTL_MISS
    if rc is not None:
        try:
            rc.setex(key, ttl, json.dumps(data))
        except Exception:
            pass
    else:
        _release_fallback['ts'] = now
        _release_fallback['data'] = data
    return data


@system_bp.route('/app-version', methods=['GET'])
@token_required
def app_version(current_user):
    """Return the running image's build manifest (version, git_sha, build_date,
    patched_packages) so the client can detect updates. Includes ``latest_release``
    when the optional GitHub update check is enabled."""
    data = dict(_load_build_info())
    if current_app.config.get('UPDATE_CHECK_ENABLED', False):
        rel = _fetch_latest_release()
        if rel:
            data['latest_release'] = rel
    return jsonify(data)

"""System / build-metadata endpoint.

Exposes the image's build manifest (baked at Docker build time into
``/app/build-info.json``) so the running PWA can detect a newer published build
and tell a feature update (``git_sha`` changed) apart from a weekly OS-security
rebuild (same ``git_sha``, newer ``build_date``).

Authenticated on purpose: build/package details are only returned to signed-in
users, so anonymous scanners can't fingerprint the exact OS package versions.
"""
import os
import json

from flask import Blueprint, jsonify

from app.routes.auth import token_required

system_bp = Blueprint('system', __name__)

# Parsed once per process — the manifest is static for the life of the container.
_BUILD_INFO_CACHE = None


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


@system_bp.route('/app-version', methods=['GET'])
@token_required
def app_version(current_user):
    """Return the running image's build manifest (version, git_sha, build_date,
    patched_packages) so the client can detect updates."""
    return jsonify(_load_build_info())

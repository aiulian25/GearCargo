"""Regression tests for L5: /health must serve the version from the build
manifest (the same source as /api/app-version), not a hardcoded '1.2.0' that
drifts on every release.

The build-info loader caches per-process in system._BUILD_INFO_CACHE, so each
test resets it (via monkeypatch.setattr, which also restores it afterwards) and
points BUILD_INFO_PATH at a temp file.
"""

import json

import app.routes.system as system
from app import db
from app.models import User


def _reset_cache(monkeypatch):
    # setattr (not raw assignment) so the cache is restored at teardown and a
    # temp version can't leak into other tests.
    monkeypatch.setattr(system, '_BUILD_INFO_CACHE', None)


def test_health_version_from_manifest_and_matches_app_version(
        app, client, auth_headers, tmp_path, monkeypatch):
    _reset_cache(monkeypatch)
    info = {'version': '7.7.7', 'git_sha': 'realsha', 'build_date': '2026-05-01', 'patched_packages': []}
    build_file = tmp_path / 'build-info.json'
    build_file.write_text(json.dumps(info))
    monkeypatch.setenv('BUILD_INFO_PATH', str(build_file))

    with app.app_context():
        u = User(username='hv', email='hv@example.com', is_active=True)
        u.set_password('StrongPass123!')
        db.session.add(u)
        db.session.commit()
        uid = u.id

    # /health is public (no auth) and now reads the manifest.
    health = client.get('/health').get_json()
    assert health['version'] == '7.7.7'          # was the hardcoded '1.2.0'
    assert health['status'] == 'healthy'         # unchanged shape

    # Same source of truth as /api/app-version.
    av = client.get('/api/app-version', headers=auth_headers(uid)).get_json()
    assert av['version'] == '7.7.7'
    assert health['version'] == av['version']


def test_health_version_falls_back_to_default_when_missing(app, client, monkeypatch):
    """No build-info file → the loader's neutral default (0.0.0), NOT the stale
    hardcoded '1.2.0'."""
    _reset_cache(monkeypatch)
    monkeypatch.setenv('BUILD_INFO_PATH', '/nonexistent/build-info.json')

    health = client.get('/health').get_json()
    assert health['version'] == '0.0.0'
    assert health['version'] != '1.2.0'

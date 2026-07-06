"""Tests for GET /api/app-version (build manifest for the in-app update check)."""

import json

import app.routes.system as system


def _reset_cache():
    system._BUILD_INFO_CACHE = None


def test_app_version_requires_auth(client):
    _reset_cache()
    resp = client.get('/api/app-version')
    assert resp.status_code == 401


def test_app_version_returns_manifest(client, user, auth_headers, tmp_path, monkeypatch):
    _reset_cache()
    info = {
        'version': '1.2.3',
        'git_sha': 'abc1234',
        'build_date': '2026-07-06T04:00:00Z',
        'patched_packages': ['libc6 2.36-9+deb12u4', 'openssl 3.0.14-1~deb12u2'],
    }
    p = tmp_path / 'build-info.json'
    p.write_text(json.dumps(info))
    monkeypatch.setenv('BUILD_INFO_PATH', str(p))

    resp = client.get('/api/app-version', headers=auth_headers(user.id))
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['version'] == '1.2.3'
    assert body['git_sha'] == 'abc1234'
    assert body['build_date'] == '2026-07-06T04:00:00Z'
    assert 'libc6 2.36-9+deb12u4' in body['patched_packages']


def test_app_version_missing_file_returns_dev_defaults(client, user, auth_headers, monkeypatch):
    _reset_cache()
    monkeypatch.setenv('BUILD_INFO_PATH', '/nonexistent/build-info.json')
    resp = client.get('/api/app-version', headers=auth_headers(user.id))
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['git_sha'] == 'dev'
    assert body['version'] == '0.0.0'
    assert body['patched_packages'] == []

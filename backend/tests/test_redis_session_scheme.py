"""Tests for R4-34 — the Redis session backend is chosen by URL scheme.

`'redis://' in redis_url` is a substring test, and `'redis://'` is not a
substring of `'rediss://'` — the TLS scheme has an extra `s` before the colon.
So a deployment pointing at a managed, TLS-only Redis (the common case for
hosted providers) silently fell through to filesystem sessions: no error, no
log line, just sessions that stop being shared between gunicorn workers.
`unix://` was missed for the same reason.
"""

import pytest

from app import create_app
from app.config import TestingConfig


def _app_with_redis_url(tmp_path, redis_url):
    class _Config(TestingConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'scheme.sqlite'}"
        JWT_SECRET_KEY = 'test-jwt-secret'
        SECRET_KEY = 'test-secret'
        REDIS_URL = redis_url
        SESSION_TYPE = 'redis'
        SESSION_FILE_DIR = str(tmp_path / 'flask_session')
        VOLUMES_PATH = str(tmp_path / 'volumes')
        UPLOAD_FOLDER = str(tmp_path / 'uploads')
        BACKUP_FOLDER = str(tmp_path / 'backups')

    for directory in ('volumes', 'uploads', 'backups', 'flask_session'):
        (tmp_path / directory).mkdir(parents=True, exist_ok=True)

    return create_app(_Config)


@pytest.mark.parametrize('redis_url', [
    'redis://localhost:6379/0',
    'rediss://user:pass@managed.example.com:6380/0',   # was: silently ignored
    'unix:///var/run/redis/redis.sock',                # was: silently ignored
])
def test_every_supported_scheme_configures_redis_sessions(tmp_path, redis_url):
    flask_app = _app_with_redis_url(tmp_path, redis_url)

    assert flask_app.config.get('SESSION_REDIS') is not None, redis_url
    assert flask_app.config['SESSION_TYPE'] == 'redis'


@pytest.mark.parametrize('redis_url', [
    'memory://',
    '',
    None,
])
def test_a_non_redis_url_does_not_configure_a_redis_backend(tmp_path, redis_url):
    flask_app = _app_with_redis_url(tmp_path, redis_url)

    assert flask_app.config.get('SESSION_REDIS') is None


def test_a_url_that_merely_mentions_the_scheme_is_rejected(tmp_path):
    """The substring test also matched anything CONTAINING 'redis://'."""
    flask_app = _app_with_redis_url(tmp_path, 'http://example.com/?next=redis://x')

    assert flask_app.config.get('SESSION_REDIS') is None


def test_the_scheme_list_is_what_redis_from_url_accepts():
    # Imported here, not at module scope, so the cases above still run (and
    # fail) against a build that has no such constant yet.
    from app import REDIS_URL_SCHEMES

    assert REDIS_URL_SCHEMES == ('redis://', 'rediss://', 'unix://')

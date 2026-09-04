"""Tests for R4-25 — session invalidation must not use Redis KEYS.

`KEYS` walks the entire keyspace and blocks the Redis server for the whole
scan. `invalidate_user_sessions` runs on password change, on logout-everywhere
and on single-device eviction, so on a busy instance it stalled every other
client. `SCAN` returns in bounded batches instead.

The fake below raises if `keys()` is touched, so this is a real regression
guard rather than a snapshot of the current implementation.
"""

import fnmatch

import pytest

import app.routes.auth as auth_module


class BlockingKeysUsed(BaseException):
    """Derives from BaseException so the handler's `except Exception` cannot
    swallow it — otherwise a reintroduced KEYS call is merely logged and the
    test reports a confusing "nothing was deleted" instead of the real cause."""


class _FakeRedis:
    """Enough of the Redis interface for invalidate_user_sessions."""

    def __init__(self, keyspace):
        self.store = dict.fromkeys(keyspace, b'1')
        self._snapshot = []
        self.scan_calls = []
        self.deleted = []

    def keys(self, pattern):
        raise BlockingKeysUsed(
            f'KEYS is blocking and must not be used (pattern={pattern!r})')

    def scan(self, cursor=0, match=None, count=10):
        """Bounded paging with real SCAN's coverage guarantee.

        The snapshot is taken when the iteration starts (cursor 0) and paged
        from there, because the caller DELETES as it goes — indexing into a
        shrinking list would silently skip keys, which real Redis does not do.
        """
        self.scan_calls.append({'cursor': cursor, 'match': match, 'count': count})
        if cursor == 0:
            self._snapshot = sorted(self.store)

        page = self._snapshot[cursor:cursor + count]
        next_cursor = cursor + count
        if next_cursor >= len(self._snapshot):
            next_cursor = 0
        matched = [key for key in page if match is None or fnmatch.fnmatch(key, match)]
        return next_cursor, matched

    def delete(self, *keys):
        removed = 0
        for key in keys:
            if self.store.pop(key, None) is not None:
                removed += 1
        self.deleted.extend(keys)
        return removed


@pytest.fixture
def fake_redis(monkeypatch):
    def _install(keyspace):
        fake = _FakeRedis(keyspace)
        monkeypatch.setattr(auth_module, 'redis_client', fake)
        return fake
    return _install


def test_sessions_are_removed_without_calling_keys(app, fake_redis):
    fake = fake_redis(['session:7:aaa', 'session:7:bbb', 'session:9:ccc'])

    with app.app_context():
        auth_module.invalidate_user_sessions(7)      # raises if KEYS is used

    assert sorted(fake.store) == ['session:9:ccc']   # another user untouched
    assert sorted(fake.deleted) == ['session:7:aaa', 'session:7:bbb']


def test_the_scan_is_batched_and_bounded(app, fake_redis):
    fake = fake_redis([f'session:7:{index:04d}' for index in range(250)])

    with app.app_context():
        auth_module.invalidate_user_sessions(7)

    assert fake.store == {}
    assert len(fake.scan_calls) > 1, 'a single unbounded pass is what KEYS did'
    for call in fake.scan_calls:
        assert call['match'] == 'session:7:*'
        assert call['count'] == auth_module.SESSION_SCAN_BATCH


def test_no_sessions_is_not_an_error(app, fake_redis):
    fake = fake_redis(['session:9:ccc'])

    with app.app_context():
        auth_module.invalidate_user_sessions(7)

    assert sorted(fake.store) == ['session:9:ccc']
    assert fake.deleted == []


def test_a_redis_failure_still_revokes_the_durable_mirror(app, monkeypatch):
    """S01: the DB mirror is what makes logout hold when Redis is down."""
    class _BrokenRedis:
        def scan(self, *args, **kwargs):
            raise RuntimeError('redis is down')

    monkeypatch.setattr(auth_module, 'redis_client', _BrokenRedis())
    revoked = []
    monkeypatch.setattr(auth_module, '_db_revoke_all_sessions', revoked.append)

    with app.app_context():
        auth_module.invalidate_user_sessions(7)      # must not raise

    assert revoked == [7]


def test_the_durable_mirror_is_revoked_when_redis_is_absent(app, monkeypatch):
    monkeypatch.setattr(auth_module, 'redis_client', None)
    revoked = []
    monkeypatch.setattr(auth_module, '_db_revoke_all_sessions', revoked.append)

    with app.app_context():
        auth_module.invalidate_user_sessions(7)

    assert revoked == [7]

"""Exercise the real migration shell flow without touching a database/service."""
import os
from pathlib import Path
import shlex
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'docker/rootfs/etc/gearcargo/scripts/migrate.sh'


def run_migration(tmp_path, *, upgrade=0, recovery=0, schema=False,
                  schema_failure='', readiness_failures=0, env_failure=False,
                  missing_cwd=False):
    bindir = tmp_path / 'bin'; bindir.mkdir()
    envfile = tmp_path / 'env.sh'
    envfile.write_text('return 17\n' if env_failure else
                      'GC_DB_HOST=disposable\nGC_DB_PORT=5432\nDATABASE_URL=disposable\n')
    events = tmp_path / 'events'
    events.write_text('')
    # The real heredoc is executed for schema sync, with only the app/SQL
    # boundary replaced. This catches swallowed individual ALTER failures too.
    (bindir / 'python3').write_text(f'#!{sys.executable}\n' + r'''
import contextlib, os, sys, types
from pathlib import Path
source = sys.stdin.read()
events = Path(os.environ['GC_TEST_EVENTS'])
def record(value):
    with events.open('a') as stream: stream.write(value + '\n')
if not os.environ.get('GC_TEST_AS_APP'):
    record('readiness')
    count = events.read_text().splitlines().count('readiness')
    sys.exit(1 if count <= int(os.environ['GC_TEST_READINESS_FAILURES']) else 0)
record('schema')
failure = os.environ['GC_TEST_SCHEMA_FAILURE']
def fail(stage):
    if failure == stage: raise RuntimeError('synthetic ' + stage + ' failure')
def execute(sql):
    record('alter'); fail('alter')
def commit():
    record('commit'); fail('commit')
def rollback(): record('rollback')
column = types.SimpleNamespace(name='added_column', nullable=True,
    type=types.SimpleNamespace(compile=lambda _: 'INTEGER'))
class Columns(dict):
    def __iter__(self): return iter(self.values())
table = types.SimpleNamespace(name='fixture_table', columns=Columns(added_column=column))
db = types.SimpleNamespace(create_all=lambda: fail('create_all'),
    engine=types.SimpleNamespace(dialect=None), metadata=types.SimpleNamespace(tables={'fixture_table': table}),
    session=types.SimpleNamespace(execute=execute, commit=commit, rollback=rollback))
app = types.ModuleType('app')
app.create_app = lambda: types.SimpleNamespace(app_context=contextlib.nullcontext)
app.db = db
sqlalchemy = types.ModuleType('sqlalchemy')
def inspect(_):
    fail('inspect')
    return types.SimpleNamespace(get_table_names=lambda: ['fixture_table'], get_columns=lambda _: [])
sqlalchemy.inspect = inspect
sqlalchemy.text = lambda sql: sql
sys.modules.update(app=app, sqlalchemy=sqlalchemy)
exec(compile(source, '<schema-sync-heredoc>', 'exec'))
''')
    (bindir / 'flask').write_text('''#!/bin/sh
case "$*" in
 recover-restores) echo recovery >> "$GC_TEST_EVENTS"; exit "$GC_TEST_RECOVERY" ;;
 'db upgrade') echo upgrade >> "$GC_TEST_EVENTS"; exit "$GC_TEST_UPGRADE" ;;
 *) exit 99 ;;
esac
''')
    (bindir / 's6-setuidgid').write_text('#!/bin/sh\nshift\nGC_TEST_AS_APP=1 exec "$@"\n')
    (bindir / 'sleep').write_text('#!/bin/sh\nexit 0\n')
    for path in bindir.iterdir(): path.chmod(0o755)
    script = tmp_path / 'migrate.sh'
    cwd = tmp_path / 'missing' if missing_cwd else tmp_path
    script.write_text(SCRIPT.read_text().replace('. /etc/gearcargo/env.sh', '. '+shlex.quote(str(envfile)))
                      .replace('cd /app', 'cd '+shlex.quote(str(cwd))))
    result = subprocess.run(['bash', str(script)], capture_output=True, text=True, timeout=20,
        env={**os.environ, 'PATH': str(bindir)+':'+os.environ['PATH'],
             'DB_SCHEMA_SYNC': 'true' if schema else 'false',
             'GC_TEST_EVENTS': str(events), 'GC_TEST_RECOVERY': str(recovery),
             'GC_TEST_UPGRADE': str(upgrade), 'GC_TEST_SCHEMA_FAILURE': schema_failure,
             'GC_TEST_READINESS_FAILURES': str(readiness_failures), 'GC_TEST_AS_APP': ''})
    return result, events.read_text().splitlines()


def test_successful_upgrade_completes_without_schema_sync(tmp_path):
    result, events = run_migration(tmp_path)
    assert result.returncode == 0, result.stderr
    assert events == ['readiness', 'recovery', 'upgrade']
    assert 'Database setup complete.' in result.stdout


@pytest.mark.parametrize('schema', [False, True])
def test_failed_upgrade_blocks_completion_and_schema_sync(tmp_path, schema):
    result, events = run_migration(tmp_path, upgrade=42, schema=schema)
    assert result.returncode != 0
    assert events == ['readiness', 'recovery', 'upgrade']
    assert 'migration failed' in result.stderr.lower()
    assert 'Database setup complete.' not in result.stdout


def test_readiness_retries_are_expected_not_fatal(tmp_path):
    result, events = run_migration(tmp_path, readiness_failures=2)
    assert result.returncode == 0, result.stderr
    assert events == ['readiness'] * 3 + ['recovery', 'upgrade']


def test_readiness_timeout_never_attempts_recovery_or_upgrade(tmp_path):
    result, events = run_migration(tmp_path, readiness_failures=60)
    assert result.returncode != 0
    assert events == ['readiness'] * 60
    assert 'database never became ready' in result.stderr
    assert 'Database setup complete.' not in result.stdout


def test_restore_recovery_failure_still_blocks_upgrade(tmp_path):
    result, events = run_migration(tmp_path, recovery=17, schema=True)
    assert result.returncode != 0
    assert events == ['readiness', 'recovery']
    assert 'refusing schema changes' in result.stderr
    assert 'Database setup complete.' not in result.stdout


def test_optional_schema_sync_success_completes(tmp_path):
    result, events = run_migration(tmp_path, schema=True)
    assert result.returncode == 0, result.stderr
    assert events == ['readiness', 'recovery', 'upgrade', 'schema', 'alter', 'commit']
    assert 'Schema verification complete.' in result.stdout
    assert 'Database setup complete.' in result.stdout


@pytest.mark.parametrize('failure', ['create_all', 'inspect', 'alter', 'commit'])
def test_optional_schema_sync_failure_blocks_completion(tmp_path, failure):
    result, events = run_migration(tmp_path, schema=True, schema_failure=failure)
    assert result.returncode != 0
    assert events[:4] == ['readiness', 'recovery', 'upgrade', 'schema']
    if failure in ('alter', 'commit'):
        assert events[-1] == 'rollback'
    assert 'schema synchronization failed' in result.stderr.lower()
    assert 'Schema verification complete.' not in result.stdout
    assert 'Database setup complete.' not in result.stdout


@pytest.mark.parametrize('setup_failure', ['env_failure', 'missing_cwd'])
def test_required_environment_or_app_directory_failure_stops_early(tmp_path, setup_failure):
    result, events = run_migration(tmp_path, **{setup_failure: True})
    assert result.returncode != 0
    assert events == []
    assert 'Database setup complete.' not in result.stdout


def test_s6_dependents_require_migration_success():
    tree = ROOT / 'docker/rootfs/etc/s6-overlay/s6-rc.d'
    assert (tree / 'migrate/type').read_text().strip() == 'oneshot'
    assert '/etc/gearcargo/scripts/migrate.sh' in (tree / 'migrate/up').read_text()
    for service in ('gunicorn', 'cron', 'scheduler', 'ocr-1', 'ocr-2'):
        assert (tree / service / 'dependencies.d/migrate').is_file()
    assert 'S6_BEHAVIOUR_IF_STAGE2_FAILS=2' in (ROOT / 'Dockerfile').read_text()

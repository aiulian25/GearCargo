"""GC-118: a system archive that is already on the server restores without a browser upload.

The upload route is capped by MAX_UPLOAD_SIZE_MB and by any proxy in front; the archive holds
every attachment, so a second copy has to be restorable from a file.
"""
import pytest

from app import db
from app.models import Vehicle
from app.routes import backup
from app.routes.backup import OPERATOR_ACTOR
from app.services import backup_encryption as backup_crypto
from app.services import restore_transaction as restore_tx
from tests.test_restore_fault_recovery import system_fixture

COMMAND = 'restore-system-archive'
PASSPHRASE = 'correct horse battery staple'


@pytest.fixture()
def audited(monkeypatch):
    events = []
    monkeypatch.setattr(backup.security_audit, 'data_import',
                        lambda user_id, email, kind, success=True: events.append((user_id, email, kind, success)))
    return events


def _vehicle_name(vehicle_id):
    db.session.expire_all()
    return db.session.get(Vehicle, vehicle_id).name


def _media(roots):
    return sorted(path.name for root in roots for path in root.rglob('*') if path.is_file())


def _encrypted(archive):
    protected = archive.with_name(archive.name + '.gcb')
    with archive.open('rb') as plaintext:
        backup_crypto.atomic_write(backup_crypto.protect_stream(plaintext, PASSPHRASE, 'tar.gz'), protected)
    return protected


def _key_file(tmp_path, passphrase=PASSPHRASE):
    key_file = tmp_path / 'backup-passphrase'
    key_file.write_text(passphrase + '\n')
    return key_file


def test_an_archive_on_the_server_is_restored_and_audited_as_an_operator_action(app, user, tmp_path, monkeypatch, audited):
    archive, roots, vehicle_id, _calls = system_fixture(app, user, tmp_path, monkeypatch)

    result = app.test_cli_runner().invoke(args=[COMMAND, str(archive)])

    assert result.exit_code == 0, result.output
    state, restore_id = result.output.split()
    assert state == 'completed' and len(restore_id) == 32
    assert _vehicle_name(vehicle_id) == 'new database'
    assert _media(roots) == ['new.txt', 'new.txt']
    assert audited == [(None, OPERATOR_ACTOR, 'system_full', True)]


def test_an_encrypted_archive_is_unlocked_from_a_passphrase_file(app, user, tmp_path, monkeypatch):
    archive, _roots, vehicle_id, _calls = system_fixture(app, user, tmp_path, monkeypatch)

    result = app.test_cli_runner().invoke(
        args=[COMMAND, str(_encrypted(archive)), '--passphrase-file', str(_key_file(tmp_path))])

    assert result.exit_code == 0, result.output
    assert _vehicle_name(vehicle_id) == 'new database'


def test_the_configured_passphrase_file_is_the_default(app, user, tmp_path, monkeypatch):
    archive, _roots, vehicle_id, _calls = system_fixture(app, user, tmp_path, monkeypatch)
    app.config['BACKUP_PASSPHRASE_FILE'] = str(_key_file(tmp_path))

    result = app.test_cli_runner().invoke(args=[COMMAND, str(_encrypted(archive))])

    assert result.exit_code == 0, result.output
    assert _vehicle_name(vehicle_id) == 'new database'


def test_a_plaintext_archive_restores_even_when_a_passphrase_file_is_configured(app, user, tmp_path, monkeypatch):
    archive, _roots, vehicle_id, _calls = system_fixture(app, user, tmp_path, monkeypatch)
    app.config['BACKUP_PASSPHRASE_FILE'] = str(_key_file(tmp_path))

    result = app.test_cli_runner().invoke(args=[COMMAND, str(archive)])

    assert result.exit_code == 0, result.output
    assert _vehicle_name(vehicle_id) == 'new database'


@pytest.mark.parametrize('key, expected', [
    (None, '--passphrase-file'),
    ('a different passphrase', 'wrong passphrase'),
], ids=['no-passphrase', 'wrong-passphrase'])
def test_an_archive_that_cannot_be_unlocked_changes_nothing(app, user, tmp_path, monkeypatch, audited, key, expected):
    archive, roots, vehicle_id, calls = system_fixture(app, user, tmp_path, monkeypatch)
    arguments = [COMMAND, str(_encrypted(archive))]
    if key:
        arguments += ['--passphrase-file', str(_key_file(tmp_path, key))]

    result = app.test_cli_runner().invoke(args=arguments)

    assert result.exit_code == 1
    assert expected in result.output
    assert not calls
    assert _vehicle_name(vehicle_id) == 'old database'
    assert _media(roots) == ['old.txt', 'old.txt']
    assert audited == [(None, OPERATOR_ACTOR, 'system_full', False)]


def test_a_damaged_archive_is_refused_before_any_live_change(app, user, tmp_path, monkeypatch, audited):
    archive, roots, vehicle_id, calls = system_fixture(app, user, tmp_path, monkeypatch, invalid_checksum=True)

    result = app.test_cli_runner().invoke(args=[COMMAND, str(archive)])

    assert result.exit_code == 1
    assert 'checksum' in result.output
    assert not calls
    assert _vehicle_name(vehicle_id) == 'old database'
    assert _media(roots) == ['old.txt', 'old.txt']
    assert audited == [(None, OPERATOR_ACTOR, 'system_full', False)]


def test_a_missing_file_is_a_usage_error(app):
    result = app.test_cli_runner().invoke(args=[COMMAND, '/nowhere/system.tar.gz'])

    assert result.exit_code == 2
    assert 'does not exist' in result.output


def test_the_command_waits_for_work_in_flight_instead_of_failing_while_busy(app, user, tmp_path, monkeypatch):
    archive, _roots, _vehicle_id, _calls = system_fixture(app, user, tmp_path, monkeypatch)
    guard, requested = restore_tx.activity_guard, []

    def recording_guard(**options):
        requested.append(options)
        return guard(**options)

    monkeypatch.setattr(restore_tx, 'activity_guard', recording_guard)

    result = app.test_cli_runner().invoke(args=[COMMAND, str(archive)])

    assert result.exit_code == 0, result.output
    assert requested[0] == {'exclusive': True, 'blocking': True}

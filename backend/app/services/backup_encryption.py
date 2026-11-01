"""Versioned, streaming backup encryption, independent of runtime PII keys.

V1: magic | version (1 byte) | format (1 byte) | salt (16) | nonce (12)
    | AES-256-GCM ciphertext | tag (16). The entire header is authenticated.
The version fixes Argon2id parameters; an input cannot request arbitrary work.
Never expose decrypted bytes until the final authentication tag has verified.
"""
from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import tempfile

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

MAGIC = b'GEARCARGO-BACKUP\x00'
VERSION = 1
FORMATS = {'json': 1, 'zip': 2, 'tar.gz': 3}
HEADER_SIZE = len(MAGIC) + 2 + 16 + 12
CHUNK_SIZE = 1024 * 1024
ERROR = 'Cannot unlock backup: wrong passphrase, damaged file, or unsupported encryption format.'


class BackupEncryptionError(ValueError):
    """Safe to show to clients. Never include key material in the message."""


def validate_passphrase(passphrase):
    if not isinstance(passphrase, str) or not 12 <= len(passphrase) <= 1024:
        raise BackupEncryptionError('Use a backup passphrase of 12–1024 characters.')
    try:
        passphrase.encode('utf-8')
    except UnicodeError:
        raise BackupEncryptionError('Backup passphrase must contain valid Unicode characters.') from None
    return passphrase


def request_passphrase(payload):
    enabled = payload.get('encrypt', False)
    if not isinstance(enabled, bool):
        raise BackupEncryptionError('encrypt must be true or false.')
    if enabled:
        return validate_passphrase(payload.get('passphrase'))
    if payload.get('passphrase'):
        raise BackupEncryptionError('Set encrypt to true when providing a backup passphrase.')
    return None


def _key(passphrase, salt):
    # RFC 9106's second recommended Argon2id option (64 MiB, three passes).
    return Argon2id(salt=salt, length=32, iterations=3, lanes=4,
                    memory_cost=64 * 1024).derive(validate_passphrase(passphrase).encode('utf-8'))


def is_encrypted(source):
    """A format hint, not proof of authenticity; restores must still verify."""
    position = source.tell()
    try:
        source.seek(0)
        return source.read(len(MAGIC)) == MAGIC
    finally:
        source.seek(position)


def file_protection(path):
    with open(path, 'rb') as source:
        encrypted = is_encrypted(source)
    return {'encrypted': encrypted, 'protection': 'encrypted' if encrypted else 'plaintext'}


def encrypt_stream(source, target, passphrase, inner_format):
    """Encrypt from current source position. Caller publishes only on success."""
    if inner_format not in FORMATS:
        raise BackupEncryptionError('Unsupported backup content format.')
    salt, nonce = os.urandom(16), os.urandom(12)
    header = MAGIC + bytes([VERSION, FORMATS[inner_format]]) + salt + nonce
    encryptor = Cipher(algorithms.AES(_key(passphrase, salt)), modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(header)
    target.write(header)
    while chunk := source.read(CHUNK_SIZE):
        target.write(encryptor.update(chunk))
    target.write(encryptor.finalize())
    target.write(encryptor.tag)


def protect_stream(source, passphrase, inner_format='zip'):
    """Return a rewindable artifact; encrypted output uses an anonymous 0600 file.

    Ownership of the returned stream passes to the caller/HTTP file response.
    The completed unencrypted input is closed when replaced by ciphertext.
    """
    source.seek(0)
    if passphrase is None:
        return source
    target = tempfile.TemporaryFile()
    try:
        encrypt_stream(source, target, passphrase, inner_format)
        target.seek(0)
        return target
    except BaseException:
        target.close()
        raise
    finally:
        source.close()


@contextmanager
def open_backup(source, filename, passphrase=None):
    """Yield (authenticated plaintext stream, format), or a legacy plain file.

    Temporary plaintext remains private and is discarded on every exit. No
    archive parser, extractor or database operation runs before GCM finalizes.
    A .gcb file with a damaged magic never falls back to legacy parsing.
    """
    source.seek(0)
    if not is_encrypted(source) and not filename.lower().endswith('.gcb'):
        if passphrase:
            raise BackupEncryptionError('This file is not an encrypted backup. Leave the restore passphrase empty for legacy plaintext files.')
        inner_format = next((fmt for fmt in FORMATS if filename.lower().endswith('.' + fmt)), None)
        if filename.lower().endswith('.tgz'):
            inner_format = 'tar.gz'
        if inner_format is None:
            raise BackupEncryptionError('Unsupported backup file format.')
        yield source, inner_format
        return
    header = source.read(HEADER_SIZE)
    if (len(header) != HEADER_SIZE or not header.startswith(MAGIC)
            or header[len(MAGIC)] != VERSION or header[len(MAGIC) + 1] not in FORMATS.values()):
        raise BackupEncryptionError(ERROR)
    inner_format = next(k for k, v in FORMATS.items() if v == header[len(MAGIC) + 1])
    source.seek(0, os.SEEK_END)
    remaining = source.tell() - HEADER_SIZE - 16
    if remaining < 0:
        raise BackupEncryptionError(ERROR)
    source.seek(-16, os.SEEK_END)
    tag = source.read(16)
    source.seek(HEADER_SIZE)
    salt, nonce = header[-28:-12], header[-12:]
    decryptor = Cipher(algorithms.AES(_key(passphrase, salt)), modes.GCM(nonce, tag)).decryptor()
    decryptor.authenticate_additional_data(header)
    with tempfile.TemporaryFile() as plaintext:
        try:
            while remaining:
                chunk = source.read(min(CHUNK_SIZE, remaining))
                if not chunk:
                    raise BackupEncryptionError(ERROR)
                remaining -= len(chunk)
                plaintext.write(decryptor.update(chunk))
            plaintext.write(decryptor.finalize())
        except InvalidTag:
            raise BackupEncryptionError(ERROR) from None
        plaintext.seek(0)
        yield plaintext, inner_format


def atomic_write(source, destination, before_publish=None):
    """Publish a complete, private artifact, preserving existing files on error."""
    partial = None
    try:
        with tempfile.NamedTemporaryFile(dir=Path(destination).parent, prefix='.backup-',
                                         suffix='.partial', delete=False) as target:
            partial = target.name
            shutil.copyfileobj(source, target, CHUNK_SIZE)
            target.flush()
            os.fsync(target.fileno())
        if before_publish:
            before_publish()
        os.replace(partial, destination)
    finally:
        if partial and os.path.exists(partial):
            os.unlink(partial)


def schedule_passphrase(schedule):
    if not schedule or not schedule.encryption_enabled:
        return None
    from app.utils.encryption import decrypt_field
    value = decrypt_field(schedule.backup_passphrase_encrypted)
    if not value:
        raise BackupEncryptionError('Saved backup passphrase is unavailable. Save it again before running backups.')
    return validate_passphrase(value)


def update_schedule_protection(schedule, payload):
    from app.utils.encryption import encrypt_field
    enabled = payload.get('encryption_enabled', bool(schedule.encryption_enabled))
    if not isinstance(enabled, bool):
        raise BackupEncryptionError('encryption_enabled must be true or false.')
    passphrase = payload.get('passphrase')
    if passphrase and not enabled:
        raise BackupEncryptionError('Enable backup encryption before saving a passphrase.')
    if enabled:
        if passphrase:
            schedule.backup_passphrase_encrypted = encrypt_field(validate_passphrase(passphrase))
        if not schedule.backup_passphrase_encrypted:
            raise BackupEncryptionError('A backup passphrase is required to enable scheduled encryption.')
    else:
        schedule.backup_passphrase_encrypted = None
    schedule.encryption_enabled = enabled
    # Also refuse to save an enabled policy whose retained key cannot be read.
    schedule_passphrase(schedule)


def read_passphrase_file(path):
    try:
        with open(path, 'r', encoding='utf-8') as key_file:
            value = key_file.read(1026).removesuffix('\n').removesuffix('\r')
    except (OSError, UnicodeError):
        raise BackupEncryptionError('Backup passphrase file is unavailable or invalid.') from None
    return validate_passphrase(value)

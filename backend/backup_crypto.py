"""Offline backup encryption/recovery. Key material is read only from a file."""
import argparse
import sys
import tempfile

from app.services.backup_encryption import (
    BackupEncryptionError, atomic_write, encrypt_stream, open_backup, read_passphrase_file,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['encrypt', 'decrypt', 'verify', 'check-key'])
    parser.add_argument('--passphrase-file', required=True)
    parser.add_argument('--input')
    parser.add_argument('--output')
    parser.add_argument('--format', choices=['json', 'zip', 'tar.gz'], default='tar.gz')
    args = parser.parse_args()
    if args.operation != 'check-key' and not args.input:
        parser.error('--input is required')
    if args.operation in ('encrypt', 'decrypt') and not args.output:
        parser.error('--output is required')
    try:
        passphrase = read_passphrase_file(args.passphrase_file)
        if args.operation == 'check-key':
            return 0
        with open(args.input, 'rb') as source:
            if args.operation == 'encrypt':
                with tempfile.TemporaryFile() as encrypted:
                    encrypt_stream(source, encrypted, passphrase, args.format)
                    encrypted.seek(0)
                    atomic_write(encrypted, args.output)
            else:
                # Force encrypted parsing even when a caller renamed the file.
                with open_backup(source, 'backup.gcb', passphrase) as (plaintext, _):
                    if args.operation == 'decrypt':
                        atomic_write(plaintext, args.output)
        return 0
    except (BackupEncryptionError, OSError):
        # Do not disclose secret paths, input data or key values in cron logs.
        print('Backup encryption/recovery failed: check passphrase file, archive and destination.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())

#!/usr/bin/env python3
"""
GearCargo - Attachment file-size repair (R4-01)

``Attachment.file_size_human`` used to divide the mapped ``file_size`` column in
place, so every read shrank the stored value and the next commit persisted it
(5242880 -> 5.0 after one backup export). The property is fixed; this script
repairs rows that were already corrupted, by re-reading the true size from disk.

Only rows whose stored size DISAGREES with the file on disk are touched, so the
script is idempotent and safe to re-run. Attachments whose file is missing (an
external/cloud restore, a pruned volume) are reported and left untouched — the
stored value is the only record left and guessing would be worse.

Usage (from the backend/ directory, or /app inside the container):
  python ../scripts/repair_attachment_file_sizes.py            # dry-run (default, safe)
  python ../scripts/repair_attachment_file_sizes.py --execute  # apply

Inside the running container:
  docker compose exec gearcargo python /app/scripts/repair_attachment_file_sizes.py
  docker compose exec gearcargo python /app/scripts/repair_attachment_file_sizes.py --execute

Requires the same environment as the app (DATABASE_URL, SECRET_KEY, ...).
"""

import argparse
import os
import sys


def main():
    parser = argparse.ArgumentParser(
        description='Repair attachment file_size values corrupted by R4-01.')
    parser.add_argument('--execute', action='store_true',
                        help='Apply changes (default is a dry run).')
    args = parser.parse_args()
    dry_run = not args.execute

    from app import create_app, db
    from app.models import Attachment

    app = create_app()
    with app.app_context():
        attachments = Attachment.query.order_by(Attachment.id).all()

        repaired = 0
        missing = 0
        unchanged = 0

        for attachment in attachments:
            if not attachment.filepath or not os.path.exists(attachment.filepath):
                missing += 1
                print(f'  [SKIP]    id={attachment.id} file not on disk '
                      f'(stored file_size={attachment.file_size})')
                continue

            actual = os.path.getsize(attachment.filepath)
            if attachment.file_size == actual:
                unchanged += 1
                continue

            print(f"  [{'DRY-RUN' if dry_run else 'REPAIR '}] id={attachment.id} "
                  f'{attachment.file_size} -> {actual}')
            if not dry_run:
                attachment.file_size = actual
            repaired += 1

        if repaired and not dry_run:
            db.session.commit()
        else:
            db.session.rollback()

        print()
        print(f'Attachments scanned : {len(attachments)}')
        print(f'Already correct     : {unchanged}')
        print(f'File missing (kept) : {missing}')
        print(f"{'Would repair' if dry_run else 'Repaired'}        : {repaired}")
        if dry_run and repaired:
            print('\nRe-run with --execute to apply.')

    return 0


if __name__ == '__main__':
    sys.exit(main())

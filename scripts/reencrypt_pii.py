#!/usr/bin/env python3
"""
GearCargo - Encryption Key Rotation / Re-encryption Script (S06)

Re-encrypts every at-rest encrypted PII field under the CURRENT primary
ENCRYPTION_KEY, using the versioned/rotatable scheme in app/utils/encryption.py.

Encrypted fields handled:
  users.two_factor_secret
  users.email_otp_secret
  users.notification_email
  users.calendar_password   (CalDAV credential)

USE CASES
---------
1) Rotate the encryption key (compromise / scheduled rotation):
     a. Generate a new key:  python -c "import secrets; print(secrets.token_hex(32))"
     b. Deploy with:  ENCRYPTION_KEY=<new>  ENCRYPTION_KEYS_OLD=<old>
        (the app keeps decrypting old data with <old> while writing new data
         under <new> — zero downtime).
     c. Run this script:  python scripts/reencrypt_pii.py --execute
     d. Once it reports 0 remaining legacy/old rows, remove ENCRYPTION_KEYS_OLD
        and redeploy.

2) Upgrade pre-S06 ciphertext (single-SHA-256, unprefixed) to the v2 HKDF scheme
   in bulk instead of waiting for each value to be rewritten:
     python scripts/reencrypt_pii.py --execute

Runs INSIDE the backend container (needs the app importable and DB reachable):
     docker compose exec gearcargo python scripts/reencrypt_pii.py --execute

Default is a safe DRY RUN; pass --execute to write changes.
"""

import argparse
import os
import sys

# Allow running from the repo root or the scripts/ dir.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

ENCRYPTED_FIELDS = (
    'two_factor_secret',
    'email_otp_secret',
    'notification_email',
    'calendar_password',
)


def main():
    parser = argparse.ArgumentParser(description='Re-encrypt PII under the current ENCRYPTION_KEY.')
    parser.add_argument('--execute', action='store_true',
                        help='Apply changes (default is a dry run).')
    parser.add_argument('--batch', type=int, default=200,
                        help='Commit every N updated users (default 200).')
    args = parser.parse_args()

    from app import create_app, db
    from app.models import User
    from app.utils.encryption import decrypt_field, encrypt_field

    app = create_app()
    with app.app_context():
        users = User.query.all()
        total = len(users)
        scanned = 0
        changed_fields = 0
        changed_users = 0
        skipped_undecryptable = 0

        print(f"Scanning {total} user(s)… ({'EXECUTE' if args.execute else 'DRY RUN'})")

        pending = 0
        for user in users:
            scanned += 1
            user_dirty = False
            for field in ENCRYPTED_FIELDS:
                raw = getattr(user, field, None)
                if not raw:
                    continue
                plaintext = decrypt_field(raw)
                if plaintext == '':
                    # Not decryptable with primary or any ENCRYPTION_KEYS_OLD key.
                    # Could be true plaintext (very old CalDAV) — leave for on-save
                    # migration — or a wrong/missing rotation key. Report and skip.
                    skipped_undecryptable += 1
                    print(f"  ! user={user.id} field={field}: could not decrypt "
                          f"(check ENCRYPTION_KEYS_OLD) — skipped")
                    continue
                # Always re-encrypt decryptable values: we cannot tell which key a
                # v2 token used without trial, so to guarantee every value lands on
                # the new primary key during a rotation we rewrite all of them.
                # (Fernet randomises the IV, so the ciphertext changes every time.)
                if args.execute:
                    setattr(user, field, encrypt_field(plaintext))
                changed_fields += 1
                user_dirty = True
            if user_dirty:
                changed_users += 1
                pending += 1
                if args.execute and pending >= args.batch:
                    db.session.commit()
                    pending = 0

        if args.execute:
            db.session.commit()

        print("-" * 60)
        print(f"Users scanned         : {scanned}")
        print(f"Fields re-encrypted   : {changed_fields}")
        print(f"Users updated         : {changed_users}")
        print(f"Undecryptable (skipped): {skipped_undecryptable}")
        if not args.execute:
            print("\nDRY RUN — no changes written. Re-run with --execute to apply.")
        elif skipped_undecryptable:
            print("\nWARNING: some fields could not be decrypted. If you are rotating, "
                  "ensure the OLD key is set in ENCRYPTION_KEYS_OLD and re-run.")
        else:
            print("\nDone. If you were rotating, you can now remove ENCRYPTION_KEYS_OLD.")


if __name__ == '__main__':
    main()

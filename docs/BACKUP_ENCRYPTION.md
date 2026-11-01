# Backup protection and recovery

GearCargo supports two explicit artifact states. **Unencrypted** JSON, ZIP and
system tar.gz files are readable by anyone who obtains them. **Encrypted** files
end in `.gcb` (for example, `.zip.gcb` or `.tar.gz.gcb`) and require their original
backup passphrase. Plaintext remains the default for existing installations;
upgrading does not encrypt old files. HTTPS protects transfer, not stored copies.
Use access-restricted encrypted destination storage even when artifact encryption
is enabled. CSV spreadsheet exports remain unencrypted.

## Personal backups

In Settings → Backup, choose encryption under **Protection for Download and Run
backup now**, enter and confirm a separate passphrase of 12–1024 characters, then
download or run the backup. These controls apply to that manual operation and its
external copies. The passphrase is not saved for manual exports.

Under **Protection for automatic backups**, enable encryption and save a
passphrase with the schedule. The server must retain this secret to run unattended;
it seals the value with the deployment's runtime `ENCRYPTION_KEY`. API responses
expose only whether a key is saved. Empty passphrase fields retain an existing key;
disabling encryption removes it. An unavailable saved key fails the job instead
of producing plaintext. Save a replacement after runtime-key loss. Runtime key
rotation with `scripts/reencrypt_pii.py --execute` includes saved schedule keys;
keep `ENCRYPTION_KEYS_OLD` until all fields have been re-encrypted successfully.

Changing a passphrase affects **future files only**. Keep old passphrases for old
backups. Store recovery passphrases separately from archives, preferably in a
password manager with an independent recovery copy. There is no reset or recovery
backdoor for a lost backup passphrase.

To restore, enter the original passphrase in **Passphrase for restore or upload**,
then choose the `.gcb` file, stored backup or external backup. Review and apply the
import as usual. Legacy JSON/ZIP restores need no backup passphrase. Uploading an
encrypted backup into stored backups also requires authentication; the stored and
external copies remain ciphertext. Encrypted files are authenticated before ZIP,
JSON or tar parsers, media staging or database changes are invoked. Wrong keys,
unsupported versions and damaged files fail without applying a restore. Supplying
a passphrase also prevents fallback to plaintext if an encrypted file was renamed.

### API contract

- `POST /api/backup/export`: `format` (`json` or `zip`), `encrypt: true`,
  `passphrase`; ZIP can also use `save_to_storage`. Defaults to unencrypted when
  `encrypt` is omitted. Download MIME is `application/octet-stream` for `.gcb`.
- `POST /api/backup/run-now`: the same encryption fields protect local and external
  copies. If both encryption fields are omitted, this endpoint uses the saved
  schedule's policy. Explicit `encrypt: false` requests plaintext. The web UI
  always sends its explicit manual choice.
- `PUT /api/backup/schedule`: `encryption_enabled` and optional `passphrase`.
  Enabling without a saved/new valid key fails. Other schedule edits retain it.
- Personal import and stored upload accept multipart `passphrase`; stored/external
  restore accept JSON `passphrase`. Preview and apply require the same original
  passphrase. Never put secrets in a query string.
- Downloads carry `X-Backup-Protection: encrypted|plaintext`. Backup records and
  local listings include `encrypted` and `protection`. External directory listings
  can only report the `.gcb` filename hint (`encrypted_unverified`); authentication
  occurs on restore. Local format detection also is not an integrity check.

## System archives (administrators)

Set `BACKUP_PASSPHRASE_FILE` to the **container path** of a separately mounted,
readable secret file containing the passphrase, with an optional final newline.
Do not mount the key under attachments, uploads or backups. Compose passes this
path to GearCargo; you must supply the corresponding read-only mount, for example
in a local Compose override:

```yaml
services:
  gearcargo:
    environment:
      BACKUP_PASSPHRASE_FILE: /run/secrets/gearcargo_backup_passphrase
    volumes:
      - ./secrets/backup-passphrase:/run/secrets/gearcargo_backup_passphrase:ro
```

Create that secret outside version control with restricted permissions and ensure
the GearCargo service user can read it. The same policy applies to daily/weekly
system jobs and `/etc/gearcargo/scripts/run-backup.sh manual`. Configured but
missing/invalid key files fail closed. Without the setting, the script writes
`.tar.gz` and logs an explicit plaintext warning. Encrypted archives use
`.tar.gz.gcb`; retention handles both formats. A scheduled retry authenticates
its existing encrypted archive before accepting it as complete.

`POST /api/backup/system/export` uses the operator file by default, or accepts an
explicit `encrypt` / `passphrase` choice for that export. System import accepts
multipart `file` and `passphrase`, including `.tar.gz.gcb`. These administrator
endpoints restore the entire deployment; personal restore controls do not accept
system archives. System recovery retains its existing requirement for a matching
database schema and migration revision. For a pre-upgrade system snapshot, restore
with its matching application release and runtime keys, then upgrade normally;
GC-028 does not bypass the schema gate. Plaintext personal backups retain their
existing versioned import support. See [transactional recovery](RESTORE_RECOVERY.md).

For offline recovery inside an image with the current backend installed:

```sh
python /app/backup_crypto.py verify \
  --input /recovery/system.tar.gz.gcb \
  --passphrase-file /run/secrets/gearcargo_backup_passphrase
python /app/backup_crypto.py decrypt \
  --input /recovery/system.tar.gz.gcb --output /recovery/system.tar.gz \
  --passphrase-file /run/secrets/gearcargo_backup_passphrase
```

The second command deliberately creates a **plaintext**, mode-0600 recovery file.
Protect and remove it after use. It publishes only after authentication succeeds,
so a bad key/corrupt archive leaves an existing output untouched. Keys are read
from files, never command-line values or logs. The same CLI has `encrypt --format
json|zip|tar.gz` for wrapping a completed archive; this does not delete its original.

## Envelope and boundaries

The `.gcb` envelope is versioned independently of the personal/system data schema.
Version 1 is exactly:

| Bytes | Meaning |
| --- | --- |
| 16 | ASCII `GEARCARGO-BACKUP` followed by NUL |
| 1 | Version `1` |
| 1 | Content format: `1` JSON, `2` ZIP, `3` tar.gz |
| 16 | Random KDF salt |
| 12 | Random GCM nonce |
| variable | Ciphertext |
| 16 | GCM authentication tag |

The version fixes **AES-256-GCM**, Argon2id with 64 MiB memory, 3 passes, 4 lanes
and a 32-byte derived key. The entire header is authenticated as additional data.
Unknown versions/formats are rejected before key derivation; attacker-supplied KDF
costs are not accepted. Salt/nonce are fresh for each export. No passphrase, runtime
key or plaintext digest is stored in the envelope. File names, format and file size remain
visible. Parameters follow [RFC 9106's second recommended option](https://www.rfc-editor.org/rfc/rfc9106.html#section-4)
and the [cryptography Argon2id API](https://cryptography.io/en/50.0.0/hazmat/primitives/key-derivation-functions/#argon2id).

Encryption and authentication read bounded 1 MiB chunks. Completed artifacts are
published by an atomic rename after the file is flushed; failures remove partial
files. Authentication uses a private temporary plaintext file and exposes it only
after the tag verifies, following the [GCM authentication contract](https://cryptography.io/en/50.0.0/hazmat/primitives/symmetric-encryption/#cryptography.hazmat.primitives.ciphers.modes.GCM).
Temporary storage must have room for the archive. The existing ZIP builder and
system SQL-dump builder still have their pre-existing memory use; this envelope
does not claim to make those entire workflows constant-memory. An abrupt machine
failure can leave private shell staging files; restrict/encrypt host temporary
storage and include cleanup in operational recovery.

Artifact encryption protects a stolen file; it does not protect a running server
that can read its saved schedule key or mounted system secret. Runtime field keys
are independent of the export passphrase: a personal portable backup can be
unlocked without the source `ENCRYPTION_KEY`, while a **full database restore still
needs the original runtime key (and applicable old keys)** to read encrypted PII,
CalDAV credentials and saved schedule secrets inside the restored database. Keep
those deployment keys separately as well. Do not downgrade to a release that
cannot read `.gcb` until archives have been recovered or a compatible recovery
image and all required keys have been retained. The migration corrects old backup
rows that falsely claimed encryption; it does not rewrite existing artifacts.

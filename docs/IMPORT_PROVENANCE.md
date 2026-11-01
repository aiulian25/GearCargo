# Import identity and review (GC-016)

Imports recognize records by the destination owner, source namespace, entity type
and source ID. Matching dates, amounts, titles or file bytes never removes an
expense. Two equal rows with different source IDs remain two records. Exact
source replays retain local edits to business records. A changed source record requires review before
any records or files are written.

## Preview and decisions

Backup Settings previews uploaded JSON/ZIP, CSV and LubeLogger files, stored
personal backups, and external personal backups. Counts distinguish new records,
exact source repeats, possible duplicates, conflicts and invalid CSV rows. Similar
content is advisory: applying imports it as a separate record. Cancel leaves the
data unchanged. The result remains visible until an explicit refresh.

For changed source data, **Keep existing and import new records** acknowledges the
new source version while retaining destination fields and files. It explicitly
links an untracked vehicle with the same VIN or plate. Previously deleted targets
and their children stay deleted. A distance-unit mismatch blocks this decision.
To apply a source correction instead, cancel and review/edit the destination
record first. There is no automatic overwrite, destructive deduplication or
batch-wide delete. The compatibility `replace` option uses these same safe rules.

Portable account preferences retain the existing backup-restore behavior and are
reapplied; preview counts describe vehicle records and their related data.

The API accepts `preview=true`, `preview_token` and
`conflict_policy=reject|keep_existing` on the existing import endpoints. Uploaded
files use multipart fields; stored/external restores use JSON options. A stale
preview or unresolved conflict returns HTTP 409, `IMPORT_REVIEW_REQUIRED` and a
fresh preview. Existing clients can apply an unambiguous import without a preview
token. Per-owner PostgreSQL transaction locks (SQLite write transactions in tests)
and a unique source-key constraint protect concurrent retries. Preview itself does
not create batches, identities, business rows, journals or files.

## Selecting a source

- Native personal backups now use version 4.2 and a persistent account export
  namespace. CSV exports include `source_namespace` and `source_id`. Keep these
  columns when editing a file. CSV vehicle IDs must still identify vehicles owned
  by the destination account.
- For older backups and external files, use a stable **Source label** for the same
  source database. Choose a different label for another source, even if it reuses
  numeric IDs. The namespace is scoped to the destination owner and format.
- Without a label or embedded namespace, the file content identifies the source.
  Replaying the identical file is safe. Changed files cannot establish continuity
  without stable source IDs and a consistent namespace.
- Rows without IDs use the file fingerprint plus row position, including legacy
  synthesized IDs and grouped LubeLogger policies. Identical rows within that file
  remain distinct. Editing/reordering an identity-free file produces new source
  identities; review suggestions before applying it. A source label alone cannot
  reconstruct missing row IDs.

## Media and recovery

Attachment byte sharing is independent of expense identity. Separate receipt
records keep their respective expense links even when identical bytes share a
file. Replaying a ZIP keeps existing photo paths and receipt links; a ZIP can
supply missing bytes to documents previously restored from JSON. Existing local
files are retained, including local edits. Changed source files with known byte
fingerprints require the same explicit conflict decision as changed metadata.

Backup and LubeLogger imports use the durable personal-restore journal. Business
rows, source mappings and batch metadata commit together; interruption rolls them
all back with newly staged files. CSV metadata and business rows also share one
transaction. See [Restore recovery](RESTORE_RECOVERY.md).

## Migration and retained metadata

Apply Alembic revision `gc016_import_provenance` after `gc008_mutation_identity`
before starting updated import clients. It assigns account namespaces and creates
`import_batches` and `import_identities`. It does not merge, delete or guess links
for any legacy business rows. Existing records can be reviewed through the
preview; matching vehicle links require explicit acceptance. Similar expenses
without known provenance remain suggestions, never automatic backfills.

The mapping retains the original source payload, latest acknowledged source
payload, and first/last batch identities. Batch metadata retains the source
records, decisions and imported origin metadata. Version-4.2 personal exports
carry active source aliases, allowing a restored account to recognize its original
source again. Deleted-target receipts remain local operational tombstones and are
included in full database snapshots, not personal exports. Deleting the account
removes its batches and source payloads. Protect exports as vehicle/financial data.

Downgrade refuses to discard populated source mappings. Preserve a full database
snapshot and stop import clients before rollback; an older snapshot cannot
remember imports performed after it. Version 4.0/4.1 and legacy 1.0/2.0 imports
remain supported, but older application releases cannot read new 4.2 exports.
No production database migration is performed by the local implementation work.

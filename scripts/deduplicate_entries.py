#!/usr/bin/env python3
"""
GearCargo - Entry Deduplication Script

Finds and removes duplicate entries caused by multiple LubeLogger imports.
Deduplication key: (vehicle_id, date, amount, type) — keeps the LOWEST id in each group.

Usage:
  python deduplicate_entries.py              # dry-run (default, safe)
  python deduplicate_entries.py --execute    # actually delete duplicates

Requires:
  DATABASE_URL env var (e.g. postgresql://user:pass@localhost:5432/dbname)
  or individual: POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
"""

import os
import sys
import argparse
from collections import defaultdict

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("ERROR: psycopg2 not installed. Run: pip install psycopg2-binary")
    sys.exit(1)


# Child tables for polymorphic entry types (joined table inheritance)
CHILD_TABLES = {
    'fuel': 'fuel_entries',
    'service': 'service_entries',
    'tax': 'tax_entries',
    'repair': 'repair_entries',
    'parking': 'parking_entries',
}


def get_db_connection():
    """Connect to PostgreSQL using DATABASE_URL or individual env vars."""
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        # Fix for SQLAlchemy-style postgres:// vs postgresql://
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        return psycopg2.connect(database_url)

    # Fallback to individual env vars
    host = os.environ.get('POSTGRES_HOST', 'localhost')
    port = os.environ.get('POSTGRES_PORT', '5432')
    dbname = os.environ.get('POSTGRES_DB', 'gearcargo')
    user = os.environ.get('POSTGRES_USER', 'gearcargo')
    password = os.environ.get('POSTGRES_PASSWORD', '')
    return psycopg2.connect(host=host, port=port, dbname=dbname, user=user, password=password)


def find_duplicates(cur):
    """
    Find duplicate entries grouped by (vehicle_id, date, amount, type).
    Returns a list of dicts: {key, keep_id, delete_ids, delete_count}
    """
    cur.execute("""
        SELECT
            vehicle_id,
            date,
            amount::numeric,
            type,
            COUNT(*) AS cnt,
            MIN(id) AS keep_id,
            ARRAY_AGG(id ORDER BY id) AS all_ids
        FROM entries
        GROUP BY vehicle_id, date, amount::numeric, type
        HAVING COUNT(*) > 1
        ORDER BY type, date, vehicle_id
    """)
    rows = cur.fetchall()

    duplicates = []
    for row in rows:
        vehicle_id, date, amount, entry_type, cnt, keep_id, all_ids = row
        delete_ids = [i for i in all_ids if i != keep_id]
        duplicates.append({
            'vehicle_id': vehicle_id,
            'date': date,
            'amount': float(amount),
            'type': entry_type,
            'keep_id': keep_id,
            'delete_ids': delete_ids,
            'count': cnt,
        })
    return duplicates


def get_attachments_for_entries(cur, entry_ids):
    """
    Get all attachment records for a list of entry IDs.
    Returns list of dicts: {id, filepath, entry_id}
    """
    if not entry_ids:
        return []
    cur.execute(
        "SELECT id, filepath, entry_id FROM attachments WHERE entry_id = ANY(%s)",
        (list(entry_ids),)
    )
    return [{'id': r[0], 'filepath': r[1], 'entry_id': r[2]} for r in cur.fetchall()]


def get_safe_files_to_delete(cur, attachment_ids_to_delete, all_filepaths):
    """
    Given a set of attachment IDs being deleted and their filepaths,
    return the subset of filepaths that are ONLY referenced by the attachments
    being deleted (i.e. safe to physically remove).
    """
    if not all_filepaths:
        return set()

    # Find filepaths referenced by attachments NOT in the delete set
    cur.execute(
        """
        SELECT DISTINCT filepath FROM attachments
        WHERE filepath = ANY(%s)
          AND id != ALL(%s)
        """,
        (list(all_filepaths), list(attachment_ids_to_delete))
    )
    filepath_still_in_use = {r[0] for r in cur.fetchall()}

    safe_to_delete = set(all_filepaths) - filepath_still_in_use
    return safe_to_delete


def delete_entries(cur, entry_ids, attachment_ids, files_to_delete, dry_run=True):
    """Delete entries, their child-table rows, their attachments, and optionally physical files."""
    if not entry_ids:
        return

    # 1. Delete attachment records
    if attachment_ids:
        if not dry_run:
            cur.execute("DELETE FROM attachments WHERE id = ANY(%s)", (list(attachment_ids),))
        print(f"  [{'DRY-RUN' if dry_run else 'DELETED'}] {len(attachment_ids)} attachment record(s)")

    # 2. Delete from child tables (joined table inheritance)
    cur.execute(
        "SELECT id, type FROM entries WHERE id = ANY(%s)",
        (list(entry_ids),)
    )
    typed_entries = cur.fetchall()

    child_counts = defaultdict(int)
    for entry_id, entry_type in typed_entries:
        child_table = CHILD_TABLES.get(entry_type)
        if child_table:
            child_counts[child_table] += 1
            if not dry_run:
                cur.execute(f"DELETE FROM {child_table} WHERE id = %s", (entry_id,))

    for tbl, cnt in child_counts.items():
        print(f"  [{'DRY-RUN' if dry_run else 'DELETED'}] {cnt} row(s) from {tbl}")

    # 3. Delete from entries (parent table)
    if not dry_run:
        cur.execute("DELETE FROM entries WHERE id = ANY(%s)", (list(entry_ids),))
    print(f"  [{'DRY-RUN' if dry_run else 'DELETED'}] {len(entry_ids)} entry row(s) from entries")

    # 4. Delete physical files
    deleted_files = 0
    skipped_files = 0
    for filepath in files_to_delete:
        if filepath and os.path.isfile(filepath):
            if not dry_run:
                os.remove(filepath)
                deleted_files += 1
            else:
                deleted_files += 1
        else:
            skipped_files += 1

    if files_to_delete:
        print(f"  [{'DRY-RUN' if dry_run else 'DELETED'}] {deleted_files} physical file(s)"
              f"{', ' + str(skipped_files) + ' already missing' if skipped_files else ''}")


def main():
    parser = argparse.ArgumentParser(description='Deduplicate GearCargo entries')
    parser.add_argument('--execute', action='store_true',
                        help='Actually delete duplicates (default is dry-run)')
    parser.add_argument('--user-id', type=int, default=None,
                        help='Limit deduplication to a specific user_id (optional)')
    args = parser.parse_args()

    dry_run = not args.execute

    print("=" * 60)
    print(f"GearCargo Entry Deduplication {'[DRY-RUN]' if dry_run else '[EXECUTE MODE]'}")
    print("=" * 60)
    if dry_run:
        print("NOTE: Run with --execute to actually delete duplicates.\n")

    conn = get_db_connection()
    conn.autocommit = False
    cur = conn.cursor()

    try:
        # Find all duplicates
        duplicates = find_duplicates(cur)

        if not duplicates:
            print("No duplicate entries found. Database is clean.")
            return

        print(f"Found {len(duplicates)} duplicate group(s):\n")

        all_delete_ids = []
        all_attachment_ids = []
        all_filepaths = set()

        for dup in duplicates:
            print(f"  [{dup['type'].upper()}] vehicle={dup['vehicle_id']} "
                  f"date={dup['date']} amount={dup['amount']:.2f} "
                  f"→ keep id={dup['keep_id']} "
                  f"delete ids={dup['delete_ids']}")
            all_delete_ids.extend(dup['delete_ids'])

        print(f"\nTotal entries to delete: {len(all_delete_ids)}")

        # Collect attachments for entries to be deleted
        attachments = get_attachments_for_entries(cur, all_delete_ids)
        all_attachment_ids = [a['id'] for a in attachments]
        all_filepaths_list = [a['filepath'] for a in attachments if a['filepath']]
        all_filepaths = set(all_filepaths_list)

        print(f"Total attachment records to remove: {len(all_attachment_ids)}")

        # Figure out which physical files are safe to delete
        files_to_delete = get_safe_files_to_delete(cur, all_attachment_ids, all_filepaths)
        shared_files = all_filepaths - files_to_delete

        print(f"Physical files to delete: {len(files_to_delete)}")
        if shared_files:
            print(f"Physical files KEPT (referenced by other records): {len(shared_files)}")

        print()

        if not args.execute:
            print("--- Dry-run summary (no changes made) ---")
            delete_entries(cur, all_delete_ids, all_attachment_ids, files_to_delete, dry_run=True)
            print("\nRe-run with --execute to apply changes.")
        else:
            print("--- Applying changes ---")
            delete_entries(cur, all_delete_ids, all_attachment_ids, files_to_delete, dry_run=False)
            conn.commit()
            print("\nDone. All changes committed.")

    except Exception as e:
        conn.rollback()
        print(f"\nERROR: {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == '__main__':
    main()

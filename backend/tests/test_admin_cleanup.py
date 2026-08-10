"""Regression test for H1: admin Maintenance Cleanup 500'd on `backup.file_path`.

The `Backup` model column is `filepath` (models/backup.py), but `run_cleanup`
read `backup.file_path` (nonexistent) → `AttributeError` → HTTP 500 whenever any
`Backup` row was older than 30 days, in BOTH preview and real modes. These tests
create an old backup row (with a real file on disk) and assert the endpoint
succeeds, reports the row, and — in real mode — removes the file and DB row.
"""

import os
import tempfile
from datetime import datetime, timedelta

from flask import current_app

from app import db
from app.models import Attachment, Backup, User


def _admin(email):
    u = User(username=email.split("@")[0], email=email, is_active=True, is_admin=True)
    u.set_password("StrongPass123!")
    db.session.add(u)
    db.session.commit()
    return u


def test_cleanup_preview_with_old_backup_does_not_500(app, client, auth_headers):
    """Preview mode over an >30-day-old backup returns 200 (was 500)."""
    with app.app_context():
        admin = _admin("cleanadmin1@example.com")
        aid = admin.id
        db.session.add(Backup(
            user_id=aid, backup_type="manual", status="completed",
            created_at=datetime.utcnow() - timedelta(days=40),
        ))
        db.session.commit()

    resp = client.post(
        "/api/admin/maintenance/cleanup",
        json={"preview": True},
        headers=auth_headers(aid, is_admin=True),
    )
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    old = next(i for i in body["items"] if i["type"] == "old_backups")
    assert old["count"] >= 1


def test_cleanup_real_removes_old_backup_file_and_row(app, client, auth_headers):
    """Real mode deletes the on-disk file and the DB row (exercises every
    `backup.filepath` access: exists/getsize/remove)."""
    fd, path = tempfile.mkstemp(prefix="gc-backup-test-")
    os.write(fd, b"dummy backup bytes")
    os.close(fd)

    with app.app_context():
        admin = _admin("cleanadmin2@example.com")
        aid = admin.id
        b = Backup(
            user_id=aid, backup_type="manual", status="completed", filepath=path,
            created_at=datetime.utcnow() - timedelta(days=40),
        )
        db.session.add(b)
        db.session.commit()
        bid = b.id

    resp = client.post(
        "/api/admin/maintenance/cleanup",
        json={"preview": False},
        headers=auth_headers(aid, is_admin=True),
    )
    assert resp.status_code == 200, resp.get_json()

    # File removed from disk and the Backup row deleted.
    assert not os.path.exists(path)
    with app.app_context():
        assert db.session.get(Backup, bid) is None


# ---------------------------------------------------------------------------
# A3: the orphan-attachment scan must scan the CONFIGURED UPLOAD_FOLDER, not a
# cwd-derived path. Under the test/CI config UPLOAD_FOLDER is a tmp dir, so the
# pre-fix os.getcwd()-based scan looked at the wrong (nonexistent) directory and
# found nothing. These tests place a real orphan + a DB-referenced file in
# UPLOAD_FOLDER and assert only the orphan is detected/removed.
# ---------------------------------------------------------------------------

def test_cleanup_detects_orphan_in_configured_upload_folder(app, client, auth_headers):
    """An unreferenced file in UPLOAD_FOLDER is reported; a referenced one is not."""
    with app.app_context():
        admin = _admin("cleanadmin3@example.com")
        aid = admin.id
        upload_folder = current_app.config["UPLOAD_FOLDER"]
        os.makedirs(upload_folder, exist_ok=True)

        # Orphan: on disk, no Attachment row.
        orphan = os.path.join(upload_folder, "orphan_deadbeef.jpg")
        with open(orphan, "wb") as fh:
            fh.write(b"orphan bytes")

        # Referenced: on disk AND has an Attachment row pointing at it.
        referenced = os.path.join(upload_folder, "kept_cafef00d.jpg")
        with open(referenced, "wb") as fh:
            fh.write(b"kept bytes")
        db.session.add(Attachment(
            user_id=aid, filename="kept_cafef00d.jpg", filepath=referenced,
            file_type="image/jpeg", file_size=10,
        ))
        db.session.commit()

    resp = client.post(
        "/api/admin/maintenance/cleanup",
        json={"preview": True},
        headers=auth_headers(aid, is_admin=True),
    )
    assert resp.status_code == 200, resp.get_json()
    orphans = next(i for i in resp.get_json()["items"] if i["type"] == "orphaned_attachments")
    assert orphans["count"] == 1  # only the orphan, not the referenced file


def test_cleanup_real_removes_only_the_orphan_file(app, client, auth_headers):
    """Real mode deletes the orphan and leaves the DB-referenced file intact."""
    with app.app_context():
        admin = _admin("cleanadmin4@example.com")
        aid = admin.id
        upload_folder = current_app.config["UPLOAD_FOLDER"]
        os.makedirs(upload_folder, exist_ok=True)

        orphan = os.path.join(upload_folder, "orphan_11112222.jpg")
        with open(orphan, "wb") as fh:
            fh.write(b"orphan bytes")

        referenced = os.path.join(upload_folder, "kept_33334444.jpg")
        with open(referenced, "wb") as fh:
            fh.write(b"kept bytes")
        db.session.add(Attachment(
            user_id=aid, filename="kept_33334444.jpg", filepath=referenced,
            file_type="image/jpeg", file_size=10,
        ))
        db.session.commit()

    resp = client.post(
        "/api/admin/maintenance/cleanup",
        json={"preview": False},
        headers=auth_headers(aid, is_admin=True),
    )
    assert resp.status_code == 200, resp.get_json()
    assert not os.path.exists(orphan)      # orphan removed
    assert os.path.exists(referenced)      # referenced file preserved

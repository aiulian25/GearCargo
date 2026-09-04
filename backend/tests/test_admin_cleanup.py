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
from app.utils.timeutils import utc_naive_now

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
            created_at=utc_naive_now() - timedelta(days=40),
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
            created_at=utc_naive_now() - timedelta(days=40),
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


# ---------------------------------------------------------------------------
# R4-18 — the orphan scan ran one `filepath LIKE '%name'` query per file on
# disk (an unindexed suffix match), so an attachments folder with thousands of
# files meant thousands of queries. R4-17 — the admin user list called
# `self.vehicles.count()` once per user through `User.to_dict()`.
# ---------------------------------------------------------------------------

import pytest
from sqlalchemy import event

from app.models import Vehicle


@pytest.fixture
def statement_counter(app):
    """Count SQL statements issued while the block runs."""
    counted = []

    def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        counted.append(statement)

    with app.app_context():
        engine = db.engine
    event.listen(engine, 'before_cursor_execute', _before_cursor_execute)
    yield counted
    event.remove(engine, 'before_cursor_execute', _before_cursor_execute)


def _seed_upload_folder(app, admin_id, file_count, referenced_count):
    """`file_count` files on disk, the first `referenced_count` with a DB row."""
    with app.app_context():
        upload_folder = current_app.config["UPLOAD_FOLDER"]
        os.makedirs(upload_folder, exist_ok=True)
        for index in range(file_count):
            name = f"scan_{index:04d}_cafe.jpg"
            with open(os.path.join(upload_folder, name), "wb") as fh:
                fh.write(b"x" * 10)
            if index < referenced_count:
                db.session.add(Attachment(
                    user_id=admin_id, filename=name,
                    filepath=os.path.join(upload_folder, name),
                    file_type="image/jpeg", file_size=10,
                ))
        db.session.commit()


def test_orphan_scan_query_count_does_not_grow_with_the_folder(
        app, client, auth_headers, statement_counter):
    """One query for the whole folder, not one per file."""
    with app.app_context():
        aid = _admin("cleanadmin_count@example.com").id

    _seed_upload_folder(app, aid, file_count=10, referenced_count=2)
    statement_counter.clear()
    client.post("/api/admin/maintenance/cleanup", json={"preview": True},
                headers=auth_headers(aid, is_admin=True))
    ten_files = len(statement_counter)

    _seed_upload_folder(app, aid, file_count=50, referenced_count=10)
    statement_counter.clear()
    response = client.post("/api/admin/maintenance/cleanup", json={"preview": True},
                           headers=auth_headers(aid, is_admin=True))
    fifty_files = len(statement_counter)

    assert response.status_code == 200, response.get_json()
    assert fifty_files == ten_files, (
        f'{fifty_files} statements for 50 files vs {ten_files} for 10 — '
        'the scan is still querying per file')


def test_orphan_scan_result_is_unchanged(app, client, auth_headers):
    with app.app_context():
        aid = _admin("cleanadmin_result@example.com").id
    _seed_upload_folder(app, aid, file_count=50, referenced_count=10)

    response = client.post("/api/admin/maintenance/cleanup", json={"preview": True},
                           headers=auth_headers(aid, is_admin=True))

    assert response.status_code == 200
    orphans = next(i for i in response.get_json()["items"]
                   if i["type"] == "orphaned_attachments")
    assert orphans["count"] == 40          # 50 on disk - 10 referenced
    assert orphans["size"] == 40 * 10


def test_orphan_scan_matches_the_whole_filename_not_a_suffix(app, client, auth_headers):
    """A file whose name is a SUFFIX of a referenced one is still an orphan.

    `filepath LIKE '%1.jpg'` also matched `.../kept_1.jpg`, so `1.jpg` was
    wrongly treated as referenced and survived cleanup forever.
    """
    with app.app_context():
        admin = _admin("cleanadmin_suffix@example.com")
        aid = admin.id
        upload_folder = current_app.config["UPLOAD_FOLDER"]
        os.makedirs(upload_folder, exist_ok=True)

        referenced = os.path.join(upload_folder, "kept_1.jpg")
        with open(referenced, "wb") as fh:
            fh.write(b"kept bytes")
        db.session.add(Attachment(
            user_id=aid, filename="kept_1.jpg", filepath=referenced,
            file_type="image/jpeg", file_size=10,
        ))
        # Its name is a suffix of the referenced file's name, but it has no row.
        suffix_orphan = os.path.join(upload_folder, "1.jpg")
        with open(suffix_orphan, "wb") as fh:
            fh.write(b"orphan bytes")
        db.session.commit()

    response = client.post("/api/admin/maintenance/cleanup", json={"preview": True},
                           headers=auth_headers(aid, is_admin=True))

    assert response.status_code == 200
    orphans = next(i for i in response.get_json()["items"]
                   if i["type"] == "orphaned_attachments")
    assert orphans["count"] == 1           # was 0 — the suffix match hid it


def test_admin_user_list_query_count_does_not_grow_with_the_user_count(
        app, client, auth_headers, statement_counter):
    with app.app_context():
        aid = _admin("cleanadmin_users@example.com").id

    def _add_users_with_vehicles(count, offset):
        with app.app_context():
            for index in range(count):
                user = User(username=f'listed{offset + index}',
                            email=f'listed{offset + index}@example.com',
                            is_active=True)
                user.set_password('StrongPass123!')
                db.session.add(user)
                db.session.flush()
                for vehicle_index in range(2):
                    db.session.add(Vehicle(user_id=user.id,
                                           name=f'Car {vehicle_index}'))
            db.session.commit()

    _add_users_with_vehicles(2, 0)
    statement_counter.clear()
    client.get("/api/admin/users", headers=auth_headers(aid, is_admin=True))
    few_users = len(statement_counter)

    _add_users_with_vehicles(8, 100)
    statement_counter.clear()
    response = client.get("/api/admin/users", headers=auth_headers(aid, is_admin=True))
    many_users = len(statement_counter)

    assert response.status_code == 200, response.get_json()
    assert many_users == few_users, (
        f'{many_users} statements for 11 users vs {few_users} for 3 — '
        'to_dict is still counting vehicles per user')


def test_admin_user_list_still_reports_the_vehicle_count(app, client, auth_headers):
    with app.app_context():
        admin = _admin("cleanadmin_vcount@example.com")
        aid = admin.id
        owner = User(username='owner2', email='owner2@example.com', is_active=True)
        owner.set_password('StrongPass123!')
        db.session.add(owner)
        db.session.commit()
        db.session.add(Vehicle(user_id=owner.id, name='One'))
        db.session.add(Vehicle(user_id=owner.id, name='Two'))
        db.session.commit()

    response = client.get("/api/admin/users", headers=auth_headers(aid, is_admin=True))

    assert response.status_code == 200
    listed = {u['email']: u['vehicle_count'] for u in response.get_json()['users']}
    assert listed['owner2@example.com'] == 2
    assert listed['cleanadmin_vcount@example.com'] == 0   # admin has none

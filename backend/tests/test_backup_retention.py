"""Regression tests for H2: manual-backup retention & 'send latest' used a
'backup_' filename prefix that save_backup_to_disk() never produces (files are
named "{App}_{User}_{timestamp}.zip"). Consequently run-now retention pruned
NOTHING (disk filled) and "Send latest to external" 404'd with "No stored
backups found." Both now match ANY .zip, consistent with get_backup_status()
and the scheduler's cleanup_user_backups().
"""

import os
import time

from app import db
from app.models import BackupSchedule, User


def _make_user(email="backup@example.com"):
    u = User(username=email.split("@")[0], email=email, is_active=True)
    u.set_password("StrongPass123!")
    db.session.add(u)
    db.session.commit()
    return u


def _write_zip(folder, name, mtime):
    path = os.path.join(folder, name)
    with open(path, "wb") as fh:
        fh.write(b"zipbytes")
    os.utime(path, (mtime, mtime))
    return path


def test_retention_prunes_prefixless_backups_beyond_max(app):
    """12 '{App}_{User}_*.zip' files, max_backups=10 → the 2 oldest are pruned."""
    from app.routes.backup import cleanup_old_backups, get_backup_folder
    with app.app_context():
        u = _make_user()
        folder = os.path.join(get_backup_folder(), str(u.id))
        os.makedirs(folder, exist_ok=True)
        base = time.time()
        for i in range(12):  # named exactly like save_backup_to_disk()
            _write_zip(folder, f"GearCargo_test_202601{i:02d}_120000.zip",
                       base - (12 - i) * 3600)  # distinct mtimes, ascending

        # retention_days huge so ONLY the max_backups rule applies (keep 10 newest).
        deleted = cleanup_old_backups(u.id, max_backups=10, retention_days=3650)
        assert deleted == 2
        remaining = [f for f in os.listdir(folder) if f.endswith(".zip")]
        assert len(remaining) == 10


def test_send_latest_selects_newest_zip_regardless_of_prefix(app, client, user, auth_headers, monkeypatch):
    """POST /backup/send-external with no filename picks the newest .zip by mtime
    (previously 404'd because nothing matched the 'backup_' prefix)."""
    from app.routes.backup import get_backup_folder
    uid = user.id
    with app.app_context():
        folder = os.path.join(get_backup_folder(), str(uid))
        os.makedirs(folder, exist_ok=True)
        _write_zip(folder, "GearCargo_test_20260101_120000.zip", 1000)  # older
        _write_zip(folder, "GearCargo_test_20260201_120000.zip", 2000)  # newer
        db.session.add(BackupSchedule(
            user_id=uid, external_enabled=True, external_url="https://example.com/dav"))
        db.session.commit()

    captured = {}

    def fake_send(backup_data, schedule, filename=None):
        captured["filename"] = filename
        captured["size"] = len(backup_data)
        return ([{"name": "dest"}], [])

    # The endpoint's real WebDAV send is replaced — we only assert file selection.
    monkeypatch.setattr("app.routes.backup.send_to_all_external_destinations", fake_send)

    resp = client.post("/api/backup/send-external", json={}, headers=auth_headers(uid))
    assert resp.status_code == 200, resp.get_json()
    assert captured["filename"] == "GearCargo_test_20260201_120000.zip"  # newest by mtime
    assert captured["size"] == len(b"zipbytes")

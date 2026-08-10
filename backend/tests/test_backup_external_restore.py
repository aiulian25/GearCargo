"""Regression tests for M5 + A2 (Step 9).

M5: restore_from_external no longer re-implements ~130 lines of ZIP restore; it
delegates to restore_from_zip, so external restores now get the existing-
attachment DEDUP (no row multiplication on repeat) and os.chmod(0o640) on the
written files — both of which the inline copy had lost.

A2: import_backup_data no longer attaches an orphaned insurance policy (whose
vehicle isn't in the backup) to an arbitrary vehicle; it skips + counts it.
"""

import os
from datetime import date

from app import db
from app.models import Attachment, FuelEntry, InsurancePolicy, User, Vehicle


def _make_user(email):
    u = User(username=email.split("@")[0], email=email, is_active=True)
    u.set_password("StrongPass123!")
    db.session.add(u)
    db.session.commit()
    return u


# ---------------------------------------------------------------------------
# A2 — orphaned insurance policy is skipped, not reassigned.
# ---------------------------------------------------------------------------

def test_unmatched_insurance_policy_is_skipped_not_reassigned(app):
    from app.routes.backup import import_backup_data
    with app.app_context():
        u = _make_user("a2@example.com")
        backup_data = {
            "vehicles": [{"id": 1, "name": "Real Car", "make": "Ford", "model": "Focus"}],
            "insurance_policies": [
                {"vehicle_id": 1, "provider": "GoodIns", "start_date": "2026-01-01",
                 "end_date": "2027-01-01", "premium": 500},
                # vehicle 999 is NOT in the backup — must be skipped, never
                # attached to the real vehicle.
                {"vehicle_id": 999, "provider": "OrphanIns", "start_date": "2026-01-01",
                 "end_date": "2027-01-01", "premium": 999},
            ],
        }
        imported, _vmap, _emap = import_backup_data(u, backup_data, "merge")

        assert imported["insurance_policies"] == 1
        assert imported["skipped_unmatched_policies"] == 1
        providers = {p.provider for p in InsurancePolicy.query.filter_by(user_id=u.id).all()}
        assert providers == {"GoodIns"}  # OrphanIns was NOT imported anywhere


# ---------------------------------------------------------------------------
# M5 — restore_from_external delegates: dedup on repeat + 0o640 file mode.
# ---------------------------------------------------------------------------

def test_external_restore_dedups_on_repeat_and_chmods(app, client, user, auth_headers, monkeypatch):
    from app.routes.backup import create_backup_zip, get_attachment_folder

    # --- build a real backup ZIP from a seeded SOURCE user (plate, no VIN, so
    #     the per-user plate dedup works and there is no global VIN collision) ---
    with app.app_context():
        src = _make_user("extsrc@example.com")
        v = Vehicle(user_id=src.id, name="Car", make="Ford", model="Focus", license_plate="ABC123")
        db.session.add(v)
        db.session.commit()
        e = FuelEntry(user_id=src.id, vehicle_id=v.id, date=date(2026, 1, 1), amount=50.0, total_price=50.0)
        db.session.add(e)
        db.session.commit()
        up = os.path.join(get_attachment_folder(), str(src.id))
        os.makedirs(up, exist_ok=True)
        fp = os.path.join(up, "ext_att.jpg")
        with open(fp, "wb") as fh:
            fh.write(b"bytes")
        db.session.add(Attachment(
            user_id=src.id, vehicle_id=v.id, entry_id=e.id,
            filename="ext_att.jpg", original_filename="a.jpg",
            filepath=fp, file_type="image/jpeg", file_size=5,
        ))
        db.session.commit()
        zbytes = create_backup_zip(src, include_attachments=True)[0].getvalue()

    class _Resp:
        status_code = 200
        content = zbytes

    # Replace the real WebDAV GET with our in-memory ZIP.
    monkeypatch.setattr("app.routes.backup._safe_webdav_request", lambda *a, **k: _Resp())

    uid = user.id  # restore target = the `user` fixture (starts with no vehicles)
    body = {"filename": "x.zip", "url": "https://example.com/dav", "api_key": "u:p"}

    r1 = client.post("/api/backup/external/restore", json=body, headers=auth_headers(uid))
    assert r1.status_code == 200, r1.get_json()
    r2 = client.post("/api/backup/external/restore", json=body, headers=auth_headers(uid))
    assert r2.status_code == 200, r2.get_json()

    with app.app_context():
        atts = Attachment.query.filter_by(user_id=uid).all()
        assert len(atts) == 1, [(a.id, a.filepath) for a in atts]  # dedup: not multiplied
        mode = oct(os.stat(atts[0].filepath).st_mode)[-3:]
        assert mode == "640", mode  # chmod applied (the old inline copy never did)

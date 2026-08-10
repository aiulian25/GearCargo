"""Regression tests for M4: a deduplicated attachment (its physical file already
added to the ZIP by another attachment) was written with NO member of its own, so
restore_from_zip — which rebuilds one Attachment row per ZIP member — silently
dropped it (and any document_attachment_id pointing at it). Backups were not
lossless. Now every DB record gets its own member.
"""

import io
import os
import zipfile
from datetime import date

from app import db
from app.models import Attachment, FuelEntry, User, Vehicle


def _make_user(email):
    u = User(username=email.split("@")[0], email=email, is_active=True)
    u.set_password("StrongPass123!")
    db.session.add(u)
    db.session.commit()
    return u


def _seed_shared_file_user(email):
    """One vehicle, two DISTINCT fuel entries, and two Attachment rows that share
    ONE physical file — the exact shape that used to lose a row on restore."""
    from app.routes.backup import get_attachment_folder

    u = _make_user(email)
    v = Vehicle(user_id=u.id, name="Car", make="Ford", model="Focus")
    db.session.add(v)
    db.session.commit()

    e1 = FuelEntry(user_id=u.id, vehicle_id=v.id, date=date(2026, 1, 1), amount=50.0, total_price=50.0)
    e2 = FuelEntry(user_id=u.id, vehicle_id=v.id, date=date(2026, 2, 2), amount=60.0, total_price=60.0)
    db.session.add_all([e1, e2])
    db.session.commit()

    upload = os.path.join(get_attachment_folder(), str(u.id))
    os.makedirs(upload, exist_ok=True)
    shared = os.path.join(upload, "deadbeef.jpg")
    with open(shared, "wb") as fh:
        fh.write(b"receipt-bytes")

    for entry in (e1, e2):  # both point at the SAME file
        db.session.add(Attachment(
            user_id=u.id, vehicle_id=v.id, entry_id=entry.id,
            filename="deadbeef.jpg", original_filename="r.jpg",
            filepath=shared, file_type="image/jpeg", file_size=13,
        ))
    db.session.commit()
    return u


def test_shared_file_gets_a_member_per_attachment(app):
    """Export: each of the two attachments has its OWN ZIP member (not deduped away)."""
    from app.routes.backup import create_backup_zip
    with app.app_context():
        src = _seed_shared_file_user("m4src@example.com")
        zip_buffer, _ = create_backup_zip(src, include_attachments=True)
        zip_bytes = zip_buffer.getvalue()

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        members = [n for n in zf.namelist()
                   if n.startswith("attachments/") and n.endswith("deadbeef.jpg")]
    # One member per DB record — previously only ONE (the dedup dropped the other).
    assert len(members) == 2, members


def test_shared_file_attachments_survive_restore(app):
    """Round-trip: restoring into a fresh user recreates BOTH attachment rows."""
    from app.routes.backup import create_backup_zip, restore_from_zip

    class _Wrap:
        def __init__(self, data):
            self._d = data
            self.filename = "backup.zip"

        def read(self):
            return self._d

    with app.app_context():
        src = _seed_shared_file_user("m4export@example.com")
        zip_buffer, _ = create_backup_zip(src, include_attachments=True)
        zip_bytes = zip_buffer.getvalue()

    # restore_from_zip returns a jsonify() Response and audits — needs a request ctx.
    with app.test_request_context():
        dst = _make_user("m4restore@example.com")
        did = dst.id
        restore_from_zip(dst, _Wrap(zip_bytes), "merge")
        db.session.commit()

    with app.app_context():
        atts = Attachment.query.filter_by(user_id=did).all()
        assert len(atts) == 2, [(a.id, a.entry_id, a.filepath) for a in atts]
        # Both rows reference the SAME restored file (the original shared shape).
        assert len({a.filepath for a in atts}) == 1

"""Regression tests for R4-01: ``Attachment.file_size_human`` divided the MAPPED
``file_size`` column in place (``self.file_size /= 1024``), so merely rendering an
attachment shrank its stored size, and the next commit persisted the corruption.

Reading a value must never mutate it. The property now formats a local copy —
the same shape ``Backup.file_size_human`` already uses.

The second test pins the real-world corruption path: every backup export calls
``a.to_dict()`` (which reads the property) for each attachment and then commits,
so a single backup rewrote every attachment row: 5242880 -> 5.0.
"""

import os
from datetime import date

from app import db
from app.models import Attachment, User


FIVE_MB = 5 * 1024 * 1024


def _make_user(email):
    user = User(username=email.split("@")[0], email=email, is_active=True)
    user.set_password("StrongPass123!")
    db.session.add(user)
    db.session.commit()
    return user


def _make_attachment(user, file_size=FIVE_MB):
    attachment = Attachment(
        user_id=user.id,
        filename="receipt.jpg",
        original_filename="receipt.jpg",
        filepath=f"/tmp/{user.id}/receipt.jpg",
        file_type="image/jpeg",
        file_size=file_size,
        category="receipt",
    )
    db.session.add(attachment)
    db.session.commit()
    return attachment


def test_file_size_human_does_not_mutate_stored_size(app):
    """Reading the property repeatedly leaves file_size untouched, in memory
    and in the database."""
    with app.app_context():
        user = _make_user("sizes@example.com")
        attachment = _make_attachment(user)

        first = attachment.to_dict()
        assert first["file_size"] == FIVE_MB
        assert first["file_size_human"] == "5.0 MB"

        # Before the fix this returned '5.0 B' — the first read had already
        # divided the column down to 5.0.
        second = attachment.to_dict()
        assert second["file_size"] == FIVE_MB
        assert second["file_size_human"] == "5.0 MB"

        db.session.commit()
        db.session.expire_all()
        assert db.session.get(Attachment, attachment.id).file_size == FIVE_MB


def test_backup_export_leaves_attachment_sizes_intact(app):
    """The export path (to_dict per attachment, then commit) must not rewrite
    the stored sizes — this is how the corruption reached the database."""
    from app.routes.backup import gather_user_data

    with app.app_context():
        user = _make_user("export-sizes@example.com")
        attachment = _make_attachment(user)

        for _ in range(2):
            gather_user_data(user, include_attachments=True)
            db.session.commit()

        db.session.expire_all()
        assert db.session.get(Attachment, attachment.id).file_size == FIVE_MB


def test_file_size_human_units(app):
    """Formatting is unchanged across the unit ladder (and 0/None stays '0 B')."""
    with app.app_context():
        user = _make_user("units@example.com")
        cases = [
            (0, "0 B"),
            (None, "0 B"),
            (512, "512.0 B"),
            (2048, "2.0 KB"),
            (FIVE_MB, "5.0 MB"),
            (3 * 1024 ** 3, "3.0 GB"),
            (2 * 1024 ** 4, "2.0 TB"),
        ]
        for size, expected in cases:
            attachment = Attachment(
                user_id=user.id,
                filename="f.bin",
                filepath="/tmp/f.bin",
                file_size=size,
            )
            assert attachment.file_size_human == expected

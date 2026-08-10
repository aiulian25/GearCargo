"""Regression tests for M6: reject ZIP decompression bombs before any member is
read into memory. Uses a monkeypatched tiny per-member ceiling so the tests
allocate only a few KB (never GBs). Covers the helper and all three ZIP entry
points: /backup/import (restore_from_zip — also guards the delegated external &
stored restores), /backup/upload, and /backup/import/lubelog.
"""

import io
import zipfile

import pytest


def _zip(members):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    buf.seek(0)
    return buf


def test_check_zip_budget_passes_and_rejects(monkeypatch):
    from app.routes import backup as b

    # A normal small archive passes.
    with zipfile.ZipFile(_zip({"a.txt": b"hello"})) as zf:
        b._check_zip_budget(zf)  # no raise

    # A single oversized member is rejected.
    monkeypatch.setattr(b, "_MAX_MEMBER_BYTES", 3)
    with zipfile.ZipFile(_zip({"a.txt": b"hello"})) as zf:  # 5 > 3
        with pytest.raises(ValueError, match="too large"):
            b._check_zip_budget(zf)

    # The running total is rejected even when each member is small.
    monkeypatch.setattr(b, "_MAX_MEMBER_BYTES", 1000)
    monkeypatch.setattr(b, "_MAX_TOTAL_UNCOMPRESSED", 6)
    with zipfile.ZipFile(_zip({"a.txt": b"aaaa", "b.txt": b"bbbb"})) as zf:  # 8 > 6
        with pytest.raises(ValueError, match="expands"):
            b._check_zip_budget(zf)


def test_import_rejects_zip_bomb(app, client, user, auth_headers, monkeypatch):
    monkeypatch.setattr("app.routes.backup._MAX_MEMBER_BYTES", 1000)
    z = _zip({"backup_data.json": '{"vehicles":[]}', "attachments/1/big.bin": b"x" * 5000})
    resp = client.post(
        "/api/backup/import",
        data={"file": (z, "backup.zip"), "merge_mode": "merge"},
        headers=auth_headers(user.id),
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400, resp.get_json()
    msg = (resp.get_json() or {}).get("error", "").lower()
    assert "too large" in msg or "expands" in msg


def test_upload_rejects_zip_bomb(app, client, user, auth_headers, monkeypatch):
    monkeypatch.setattr("app.routes.backup._MAX_MEMBER_BYTES", 1000)
    z = _zip({"backup_data.json": '{"vehicles":[]}', "attachments/1/big.bin": b"x" * 5000})
    resp = client.post(
        "/api/backup/upload",
        data={"file": (z, "backup.zip")},
        headers=auth_headers(user.id),
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400, resp.get_json()
    msg = (resp.get_json() or {}).get("error", "").lower()
    assert "too large" in msg or "expands" in msg


def test_lubelog_rejects_zip_bomb(app, client, user, auth_headers, monkeypatch):
    """The budget check runs at the ZIP entry, before any LiteDB parsing, so a
    bomb is rejected (400) even without a valid LubeLogger structure."""
    monkeypatch.setattr("app.routes.backup._MAX_MEMBER_BYTES", 1000)
    z = _zip({"data.db": b"x" * 5000})
    resp = client.post(
        "/api/backup/import/lubelog",
        data={"file": (z, "lube.zip")},
        headers=auth_headers(user.id),
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400, resp.get_json()

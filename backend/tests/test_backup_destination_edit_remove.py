"""Bug: a configured External Backup destination cannot be edited or removed.

Reported from Settings → External Backup with one destination ("Primary
Destination"). Clicking Remove appeared to do nothing.

Cause: with a single destination the UI replaced it with a BLANK placeholder
instead of clearing the list, and `PUT /api/backup/schedule` rejects a
destination whose `external_url` is empty (400) — so the save failed and the
old destination was still there after the page reloaded.
"""

import json

from app import db
from app.models import User
from app.models.backup import BackupSchedule

SCHEDULE_URL = "/api/backup/schedule"
URL = "https://files.example.com"
KEY = "user:app-password"


def _user_with_destination(email="dest@example.com"):
    u = User(username=email.split("@")[0], email=email, is_active=True)
    u.set_password("StrongPass123!")
    db.session.add(u)
    db.session.commit()

    schedule = BackupSchedule(user_id=u.id, enabled=True, external_enabled=True,
                              external_url=URL, external_path="/GearCargo")
    schedule.set_external_destinations([{
        "id": "legacy_primary",
        "name": "Primary Destination",
        "provider": "webdav",
        "enabled": True,
        "external_url": URL,
        "external_api_key": KEY,
        "external_path": "/GearCargo",
    }])
    db.session.add(schedule)
    db.session.commit()
    return u.id


def _destinations(app, uid):
    with app.app_context():
        db.session.remove()
        s = BackupSchedule.query.filter_by(user_id=uid).first()
        return s.get_external_destinations() or []


# --- removal ------------------------------------------------------------------

def test_removing_the_only_destination_clears_it(app, client, auth_headers):
    """An empty list must clear the destinations (what Remove now sends)."""
    with app.app_context():
        uid = _user_with_destination()

    resp = client.put(SCHEDULE_URL, json={"external_destinations": [],
                                          "external_enabled": False},
                      headers=auth_headers(uid))
    assert resp.status_code == 200, resp.data[:200]
    assert _destinations(app, uid) == []


def test_blank_placeholder_destination_is_rejected(app, client, auth_headers):
    """The old UI behaviour — replacing the last destination with a blank one —
    is a 400, which is exactly why Remove looked like a no-op."""
    with app.app_context():
        uid = _user_with_destination("dest2@example.com")

    resp = client.put(SCHEDULE_URL, json={"external_destinations": [{
        "id": "destination_1", "name": "Destination 1", "provider": "webdav",
        "enabled": False, "external_url": "", "external_api_key": "",
        "external_path": "/GearCargo",
    }]}, headers=auth_headers(uid))

    assert resp.status_code == 400
    assert "external_url" in resp.get_json()["error"]
    # ...and the original destination survives, matching the reported symptom.
    assert len(_destinations(app, uid)) == 1


# --- editing ------------------------------------------------------------------

def test_editing_name_and_path_persists_without_resending_the_api_key(app, client, auth_headers):
    """The API key is never returned by the API, so the UI resends it empty —
    the stored key must be preserved rather than failing validation."""
    with app.app_context():
        uid = _user_with_destination("dest3@example.com")

    resp = client.put(SCHEDULE_URL, json={"external_destinations": [{
        "id": "legacy_primary", "name": "Synology NAS", "provider": "webdav",
        "enabled": True, "external_url": URL, "external_api_key": "",
        "external_path": "/Documents/Backups",
    }]}, headers=auth_headers(uid))
    assert resp.status_code == 200, resp.data[:200]

    dests = _destinations(app, uid)
    assert len(dests) == 1
    assert dests[0]["name"] == "Synology NAS"
    assert dests[0]["external_path"] == "/Documents/Backups"
    assert dests[0]["external_api_key"] == KEY      # preserved, not wiped


def test_editing_the_url_keeps_the_stored_api_key(app, client, auth_headers):
    """Changing the URL must still match the existing destination by id."""
    with app.app_context():
        uid = _user_with_destination("dest4@example.com")

    new_url = "https://nas.example.com"
    resp = client.put(SCHEDULE_URL, json={"external_destinations": [{
        "id": "legacy_primary", "name": "Primary Destination", "provider": "webdav",
        "enabled": True, "external_url": new_url, "external_api_key": "",
        "external_path": "/GearCargo",
    }]}, headers=auth_headers(uid))
    assert resp.status_code == 200, resp.data[:200]

    dests = _destinations(app, uid)
    assert dests[0]["external_url"] == new_url
    assert dests[0]["external_api_key"] == KEY


def test_disabling_a_destination_persists(app, client, auth_headers):
    with app.app_context():
        uid = _user_with_destination("dest5@example.com")

    resp = client.put(SCHEDULE_URL, json={"external_destinations": [{
        "id": "legacy_primary", "name": "Primary Destination", "provider": "webdav",
        "enabled": False, "external_url": URL, "external_api_key": "",
        "external_path": "/GearCargo",
    }]}, headers=auth_headers(uid))
    assert resp.status_code == 200, resp.data[:200]
    assert _destinations(app, uid)[0]["enabled"] is False

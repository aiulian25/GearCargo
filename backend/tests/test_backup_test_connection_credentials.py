"""Bug: "Test Connection" on a NEW external destination reports
"Authentication failed. Use format username:app-password".

Two causes, both here:

1. A blank API key fell back to the LEGACY top-level ``external_api_key`` —
   the credential saved for a different destination. Testing a newly added
   destination therefore reported someone else's auth result, and the stale
   legacy key is never cleared (PUT /schedule skips empty values), so it
   outlives the destination it belonged to.

2. A credential with no ``username:`` part was turned into ``(token, token)``
   and the username half is interpolated into the request path — sending the
   app password as a URL path segment, where the server and any proxy logs it.

No outbound request is made: ``_safe_webdav_request`` is monkeypatched.
"""

import pytest

import app.routes.backup as bk
from app import db
from app.models import User
from app.models.backup import BackupSchedule

TEST_URL = "/api/backup/external/test"
SAVED_URL = "https://saved.example.com"
NEW_URL = "https://brand-new.example.com"
SAVED_KEY = "saved-user:saved-app-password"
LEGACY_KEY = "legacy-user:legacy-app-password"


@pytest.fixture
def calls(monkeypatch):
    """Record every WebDAV request instead of making one."""
    recorded = []

    class _Response:
        status_code = 207

    def _record(method, url, **kwargs):
        recorded.append({"method": method, "url": url, "auth": kwargs.get("auth")})
        return _Response()

    monkeypatch.setattr(bk, "_safe_webdav_request", _record)
    monkeypatch.setattr(bk, "_is_allowed_webdav_url", lambda url: True)
    return recorded


def _user_with_saved_destination(email="test-conn@example.com"):
    user = User(username=email.split("@")[0], email=email, is_active=True)
    user.set_password("StrongPass123!")
    db.session.add(user)
    db.session.commit()

    schedule = BackupSchedule(user_id=user.id, enabled=True, external_enabled=True,
                              external_url=SAVED_URL, external_api_key=LEGACY_KEY,
                              external_path="/GearCargo")
    schedule.set_external_destinations([{
        "id": "legacy_primary",
        "name": "Saved Destination",
        "provider": "webdav",
        "enabled": True,
        "external_url": SAVED_URL,
        "external_api_key": SAVED_KEY,
        "external_path": "/GearCargo",
    }])
    db.session.add(schedule)
    db.session.commit()
    return user.id


# --- credential selection -----------------------------------------------------

def test_new_destination_with_blank_key_does_not_borrow_the_legacy_key(app, client, auth_headers, calls):
    """The reported bug: a new destination silently tested with the old key."""
    with app.app_context():
        uid = _user_with_saved_destination()

    resp = client.post(TEST_URL, json={"url": NEW_URL, "api_key": ""},
                       headers=auth_headers(uid))

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is False
    assert body["message_key"] == "backup.apiKeyRequired"
    assert calls == []          # nothing was sent using another destination's key


def test_typed_key_is_used_verbatim(app, client, auth_headers, calls):
    with app.app_context():
        uid = _user_with_saved_destination("test-conn2@example.com")

    resp = client.post(TEST_URL, json={"url": NEW_URL, "api_key": "new-user:new-secret"},
                       headers=auth_headers(uid))

    assert resp.get_json()["success"] is True
    assert calls[0]["auth"] == ("new-user", "new-secret")
    assert calls[0]["url"].endswith("/new-user")


def test_blank_key_reuses_that_destinations_stored_key(app, client, auth_headers, calls):
    """Re-testing a SAVED destination still works without retyping the key."""
    with app.app_context():
        uid = _user_with_saved_destination("test-conn3@example.com")

    resp = client.post(TEST_URL, json={"url": SAVED_URL, "api_key": ""},
                       headers=auth_headers(uid))

    assert resp.get_json()["success"] is True
    assert calls[0]["auth"] == ("saved-user", "saved-app-password")


# --- credential format --------------------------------------------------------

def test_key_without_username_is_rejected_before_any_request(app, client, auth_headers, calls):
    """A colon-less key would otherwise be sent as ``.../<app-password>``."""
    with app.app_context():
        uid = _user_with_saved_destination("test-conn4@example.com")

    resp = client.post(TEST_URL, json={"url": NEW_URL, "api_key": "AAAAA-BBBBB-CCCCC-DDDDD"},
                       headers=auth_headers(uid))

    body = resp.get_json()
    assert body["success"] is False
    assert body["message_key"] == "backup.apiKeyFormat"
    assert calls == []          # the password never reached a URL


@pytest.mark.parametrize("token", ["", "   ", "onlypassword", ":no-username", "user:", ":"])
def test_malformed_credentials_have_no_username(token):
    assert bk._webdav_credential_parts(token) is None


def test_webdav_auth_never_puts_the_password_in_the_username_slot(app):
    """Legacy rows saved before validation must not leak via auth[0]."""
    with app.app_context():
        schedule = BackupSchedule(user_id=1, external_api_key="colonless-secret")
        assert bk._webdav_auth(schedule) == ("", "")

        schedule.external_api_key = "person:secret"
        assert bk._webdav_auth(schedule) == ("person", "secret")


# --- save path ----------------------------------------------------------------

def test_saving_a_destination_rejects_a_key_without_a_username(app, client, auth_headers):
    with app.app_context():
        uid = _user_with_saved_destination("test-conn5@example.com")

    resp = client.put("/api/backup/schedule", json={"external_destinations": [{
        "id": "destination_1", "name": "Destination 1", "provider": "webdav",
        "enabled": True, "external_url": NEW_URL,
        "external_api_key": "onlythepassword", "external_path": "/GearCargo",
    }]}, headers=auth_headers(uid))

    assert resp.status_code == 400
    assert resp.get_json()["message_key"] == "backup.apiKeyFormat"

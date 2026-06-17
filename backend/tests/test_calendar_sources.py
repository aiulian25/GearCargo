from app import db
from app.models import User
from app.services.calendar_service import get_user_calendar_sources


def test_calendar_settings_accept_multiple_sources(client, user, auth_headers):
    response = client.post(
        "/api/calendar/settings",
        headers=auth_headers(user.id),
        json={
            "enabled": True,
            "sources": [
                {
                    "id": "source_google",
                    "name": "Google Main",
                    "provider": "google",
                    "url": "https://apidata.googleusercontent.com/caldav/v2/test@example.com/events",
                    "username": "test@example.com",
                    "password": "app-password-1",
                    "calendar_id": "primary",
                    "enabled": True,
                },
                {
                    "id": "source_nextcloud",
                    "name": "Nextcloud",
                    "provider": "nextcloud",
                    "url": "https://cloud.example.com/remote.php/dav/calendars/test/",
                    "username": "test",
                    "password": "app-password-2",
                    "calendar_id": "personal",
                    "enabled": True,
                },
            ],
        },
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["message_key"] == "calendar.settings.updated"
    assert len(body["sources"]) == 2
    assert all("password" not in source for source in body["sources"])


def test_calendar_settings_reject_insecure_source_url(client, user, auth_headers):
    response = client.post(
        "/api/calendar/settings",
        headers=auth_headers(user.id),
        json={
            "enabled": True,
            "sources": [
                {
                    "id": "source_insecure",
                    "name": "Insecure",
                    "provider": "caldav",
                    "url": "http://example.com/caldav",
                    "username": "test",
                    "password": "secret",
                    "enabled": True,
                }
            ],
        },
    )

    assert response.status_code == 400
    body = response.get_json()
    assert body["message_key"] == "calendar.source.https_required"


def test_calendar_settings_preserve_existing_password_when_omitted(client, app, user, auth_headers):
    first_response = client.post(
        "/api/calendar/settings",
        headers=auth_headers(user.id),
        json={
            "enabled": True,
            "sources": [
                {
                    "id": "source_primary",
                    "name": "Primary",
                    "provider": "caldav",
                    "url": "https://calendar.example.com/caldav",
                    "username": "test",
                    "password": "initial-secret",
                    "calendar_id": "home",
                    "enabled": True,
                }
            ],
        },
    )

    assert first_response.status_code == 200

    second_response = client.post(
        "/api/calendar/settings",
        headers=auth_headers(user.id),
        json={
            "enabled": True,
            "sources": [
                {
                    "id": "source_primary",
                    "name": "Primary Updated",
                    "provider": "caldav",
                    "url": "https://calendar.example.com/caldav",
                    "username": "test",
                    "password": "",
                    "calendar_id": "work",
                    "enabled": True,
                }
            ],
        },
    )

    assert second_response.status_code == 200

    with app.app_context():
        saved_user = User.query.get(user.id)
        assert saved_user is not None
        sources = get_user_calendar_sources(saved_user, include_secrets=True)
        assert len(sources) == 1
        assert sources[0]["has_password"] is True
        assert sources[0]["calendar_id"] == "work"

        preferences = saved_user.preferences or {}
        stored_sources = preferences.get("calendar_sources") or []
        assert stored_sources[0]["password"]
        assert stored_sources[0]["password"] != "initial-secret"

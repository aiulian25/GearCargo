from app import db
from app.models import BackupSchedule


def test_update_schedule_rejects_non_list_destinations(client, user, auth_headers):
    response = client.put(
        "/api/backup/schedule",
        headers=auth_headers(user.id),
        json={"external_destinations": "not-a-list"},
    )

    assert response.status_code == 400
    body = response.get_json()
    assert body["error"] == "external_destinations must be a list"


def test_update_schedule_rejects_destination_without_api_key(client, user, auth_headers):
    response = client.put(
        "/api/backup/schedule",
        headers=auth_headers(user.id),
        json={
            "external_enabled": True,
            "external_destinations": [
                {
                    "id": "dest_1",
                    "name": "Primary",
                    "enabled": True,
                    "external_url": "https://backup.example.com/webdav",
                    "external_api_key": "",
                    "external_path": "/GearCargo",
                }
            ],
        },
    )

    assert response.status_code == 400
    body = response.get_json()
    assert "missing external_api_key" in body["error"]


def test_update_schedule_preserves_existing_destination_api_key(client, app, user, auth_headers):
    with app.app_context():
        schedule = BackupSchedule(user_id=user.id, enabled=True, external_enabled=True)
        schedule.set_external_destinations(
            [
                {
                    "id": "dest_primary",
                    "name": "Primary",
                    "enabled": True,
                    "external_url": "https://backup.example.com/webdav",
                    "external_api_key": "existing-secret",
                    "external_path": "/GearCargo",
                }
            ]
        )
        db.session.add(schedule)
        db.session.commit()

    response = client.put(
        "/api/backup/schedule",
        headers=auth_headers(user.id),
        json={
            "enabled": True,
            "external_enabled": True,
            "external_destinations": [
                {
                    "id": "dest_primary",
                    "name": "Primary",
                    "enabled": True,
                    "external_url": "https://backup.example.com/webdav",
                    "external_api_key": "",
                    "external_path": "/SecureBackups",
                }
            ],
        },
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["schedule"]["external_destinations"][0]["has_external_api_key"] is True

    with app.app_context():
        saved = BackupSchedule.query.filter_by(user_id=user.id).first()
        destinations = saved.get_external_destinations()
        assert destinations[0]["external_api_key"] == "existing-secret"
        assert destinations[0]["external_path"] == "/SecureBackups"

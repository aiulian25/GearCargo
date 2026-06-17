from datetime import date

from app import db
from app.models import FuelEntry, Vehicle


def _create_vehicle_and_entries(user_id, vehicle_mileage=0, odometers=None):
    vehicle = Vehicle(
        user_id=user_id,
        name="Test Vehicle",
        fuel_type="petrol",
        current_mileage=vehicle_mileage,
    )
    db.session.add(vehicle)
    db.session.flush()

    created_entries = []
    for value in odometers or []:
        entry = FuelEntry(
            user_id=user_id,
            vehicle_id=vehicle.id,
            date=date.today(),
            odometer=value,
            liters=10,
            total_price=20,
            amount=20,
            currency="EUR",
            fuel_type="petrol",
            full_tank=True,
        )
        db.session.add(entry)
        created_entries.append(entry)

    db.session.commit()
    return vehicle.id, [entry.id for entry in created_entries]


def test_update_vehicle_mileage_allows_decrease_above_recorded_max(app, client, user, auth_headers):
    with app.app_context():
        vehicle_id, _ = _create_vehicle_and_entries(
            user.id,
            vehicle_mileage=20000,
            odometers=[15000, 18000],
        )

    response = client.post(
        f"/api/vehicles/{vehicle_id}/mileage",
        headers=auth_headers(user.id),
        json={"mileage": 19000},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["current_mileage"] == 19000


def test_update_vehicle_mileage_rejects_below_recorded_max(app, client, user, auth_headers):
    with app.app_context():
        vehicle_id, _ = _create_vehicle_and_entries(
            user.id,
            vehicle_mileage=22000,
            odometers=[15000, 18000],
        )

    response = client.post(
        f"/api/vehicles/{vehicle_id}/mileage",
        headers=auth_headers(user.id),
        json={"mileage": 17000},
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["message_key"] == "vehicles.mileageBelowRecordedMax"
    assert payload["min_allowed_mileage"] == 18000


def test_fuel_update_recalculates_vehicle_current_mileage(app, client, user, auth_headers):
    with app.app_context():
        vehicle_id, entry_ids = _create_vehicle_and_entries(
            user.id,
            vehicle_mileage=20000,
            odometers=[12000, 20000],
        )
        high_entry_id = entry_ids[-1]

    response = client.put(
        f"/api/fuel/{high_entry_id}",
        headers=auth_headers(user.id),
        json={"odometer": 13000},
    )

    assert response.status_code == 200

    with app.app_context():
        vehicle = db.session.get(Vehicle, vehicle_id)
        assert vehicle is not None
        assert vehicle.current_mileage == 13000

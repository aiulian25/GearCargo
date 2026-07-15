"""Tests for F30 — health scores persist on the Vehicle row after a Health view."""

from datetime import date, timedelta

from app import db
from app.models import Vehicle, ServiceEntry, FuelEntry

TODAY = date.today()


def _mk_vehicle_with_history(app, user):
    with app.app_context():
        v = Vehicle(user_id=user.id, name='Superb', make='Skoda', model='Superb',
                    year=2020, current_mileage=60000)
        db.session.add(v)
        db.session.commit()
        db.session.add(ServiceEntry(user_id=user.id, vehicle_id=v.id, amount=120,
                                    date=TODAY - timedelta(days=90),
                                    service_type='oil_change', odometer=58000))
        db.session.add(FuelEntry(user_id=user.id, vehicle_id=v.id, amount=80,
                                 total_price=80, liters=45, odometer=59000,
                                 date=TODAY - timedelta(days=30), fuel_type='diesel'))
        db.session.commit()
        return v.id


def test_health_view_persists_scores(app, client, user, auth_headers):
    vid = _mk_vehicle_with_history(app, user)

    # Before any Health view the cache is empty.
    before = client.get(f'/api/vehicles/{vid}', headers=auth_headers(user.id)).get_json()
    assert before['health_score'] is None
    assert before['stats']['maintenance_score'] is None

    health = client.get(f'/api/vehicles/{vid}/health', headers=auth_headers(user.id))
    assert health.status_code == 200
    payload = health.get_json()
    assert isinstance(payload['overall_score'], int)

    after = client.get(f'/api/vehicles/{vid}', headers=auth_headers(user.id)).get_json()
    assert after['health_score'] == payload['overall_score']
    assert after['health_computed_at'] is not None
    assert isinstance(after['stats']['maintenance_score'], int)

    with app.app_context():
        v = db.session.get(Vehicle, vid)
        assert v.health_score == payload['overall_score']
        assert v.health_computed_at is not None


def test_health_read_survives_persist_failure(app, client, user, auth_headers, monkeypatch):
    vid = _mk_vehicle_with_history(app, user)

    import app.routes.vehicles as vroutes

    # Fail ONLY the health-persist commit (the one with a dirty Vehicle row) —
    # auth-layer commits earlier in the request must keep working.
    real_commit = db.session.commit

    def _boom():
        if any(isinstance(o, Vehicle) for o in db.session.dirty):
            raise RuntimeError('simulated commit failure')
        return real_commit()

    monkeypatch.setattr(vroutes.db.session, 'commit', _boom)
    resp = client.get(f'/api/vehicles/{vid}/health', headers=auth_headers(user.id))
    assert resp.status_code == 200          # read unaffected by the write failure
    assert isinstance(resp.get_json()['overall_score'], int)
    monkeypatch.undo()

    with app.app_context():
        assert db.session.get(Vehicle, vid).health_score is None  # nothing stored

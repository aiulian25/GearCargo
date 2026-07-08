"""Tests for F17 — vehicle dimensions exposed in Vehicle.to_dict."""

from app import db
from app.models import User, Vehicle


def _mk_user():
    u = User(email='dim@example.com', username='dimuser', is_active=True)
    u.set_password('Str0ng!Passw0rd')
    db.session.add(u)
    db.session.commit()
    return u


def test_to_dict_includes_dimension_fields(app):
    with app.app_context():
        u = _mk_user()
        v = Vehicle(user_id=u.id, name='Van', make='Ford', model='Transit',
                    vehicle_height_cm=260, vehicle_width_cm=205,
                    vehicle_length_cm=540, vehicle_weight_kg=2100)
        db.session.add(v)
        db.session.commit()

        d = v.to_dict()
        assert d['vehicle_height_cm'] == 260
        assert d['vehicle_width_cm'] == 205
        assert d['vehicle_length_cm'] == 540
        assert d['vehicle_weight_kg'] == 2100


def test_to_dict_dimensions_null_when_unset(app):
    with app.app_context():
        u = _mk_user()
        v = Vehicle(user_id=u.id, name='Hatch', make='VW', model='Golf')
        db.session.add(v)
        db.session.commit()

        d = v.to_dict()
        # Keys always present (so the frontend can test them), value None when unset.
        assert d['vehicle_height_cm'] is None
        assert d['vehicle_weight_kg'] is None

"""Opt-in, synthetic browser fixture for the tire lifecycle feature."""
from tests.browser_queue_fixture import app
from app import db
from app.models import User, Vehicle, ConsumableEntry
from datetime import date
with app.app_context():
    owner = User.query.filter_by(username='queue_A').one()
    vehicle = Vehicle(user_id=owner.id, name='Seasonal test car', distance_unit='km', current_mileage=2500)
    db.session.add(vehicle); db.session.flush()
    db.session.add(ConsumableEntry(user_id=owner.id, vehicle_id=vehicle.id, title='Four tires and receipt',
        date=date(2026, 1, 1), amount=480, currency='EUR', consumable_type='tire'))
    db.session.commit()

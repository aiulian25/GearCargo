"""Opt-in, synthetic workshop browser data; no live accounts or providers."""
from tests.browser_queue_fixture import app
from app import db
from app.models import User, Vehicle, ServiceEntry, Todo
from datetime import date
with app.app_context():
    owner = User.query.filter_by(username='queue_A').one()
    owner.timezone = 'Europe/London'
    vehicle = Vehicle(user_id=owner.id, name='Workshop test car', distance_unit='km', current_mileage=25000)
    db.session.add(vehicle); db.session.flush()
    db.session.add(ServiceEntry(user_id=owner.id, vehicle_id=vehicle.id, title='Workshop invoice',
        date=date(2026, 11, 1), amount=230, currency='GBP', service_type='inspection'))
    db.session.add(Todo(user_id=owner.id, vehicle_id=vehicle.id, title='Inspect brakes', due_date=date(2026, 1, 1)))
    db.session.commit()

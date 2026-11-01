"""Opt-in synthetic statement workflow data; never uses live accounts."""
from tests.browser_queue_fixture import app
from app import db
from app.models import User, Vehicle, ServiceEntry
from datetime import date
with app.app_context():
    owner = User.query.filter_by(username='queue_A').one()
    car = Vehicle(user_id=owner.id, name='Statement test car', distance_unit='km', current_mileage=25000)
    db.session.add(car); db.session.flush()
    for title, amount in [('Invoice A',40),('Invoice B',60),('Refund',-20)]:
        db.session.add(ServiceEntry(user_id=owner.id, vehicle_id=car.id, title=title, date=date(2026,10,1), amount=amount, currency='GBP', service_type='inspection', garage_name='Garage'))
    db.session.commit()

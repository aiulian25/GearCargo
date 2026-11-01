"""GC-020 disposable data; inherits the explicitly gated browser fixture."""
from datetime import date
from tests.browser_queue_fixture import app
from app import db
from app.models import User, Vehicle, FuelEntry, ConsumableEntry, InsurancePolicy
from app.routes import vehicles
from app.services import currency

vehicles.get_rates_cached = currency.get_rates_cached = lambda app: {'GBP': .8, 'USD': 2}
with app.app_context():
    user = User.query.filter_by(username='queue_A').one()
    user.currency = 'GBP'
    vehicle = Vehicle(user_id=user.id, name='Long history', make='Test', model='History', fuel_type='petrol')
    insurance_only = Vehicle(user_id=user.id, name='Insurance only')
    db.session.add_all([vehicle, insurance_only])
    db.session.flush()
    for index in range(121):
        db.session.add(FuelEntry(user_id=user.id, vehicle_id=vehicle.id, date=date(2024, 1, 31),
            amount=10, total_price=10, currency='GBP', station=f'Station {index + 1}',
            liters=5, price_per_liter=2, odometer=1000 + index, full_tank=True))
    db.session.add(ConsumableEntry(user_id=user.id, vehicle_id=vehicle.id,
        date=date(2024, 1, 31), title='Tyres', amount=80, currency='GBP'))
    for v in (vehicle, insurance_only):
        db.session.add(InsurancePolicy(user_id=user.id, vehicle_id=v.id, provider='Monthly EUR',
            premium=10, currency='EUR', payment_frequency='monthly', status='expired',
            start_date=date(2024, 1, 31), end_date=date(2024, 12, 31)))
        db.session.add(InsurancePolicy(user_id=user.id, vehicle_id=v.id, provider='Old USD',
            premium=50, currency='USD', payment_frequency='one_time', status='expired',
            start_date=date(2020, 1, 1), end_date=date(2020, 12, 31)))
    db.session.commit()

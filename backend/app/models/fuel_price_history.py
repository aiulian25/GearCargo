"""
GearCargo - Weekly national fuel-price history (F25).

One row per (country, price_date). Accrues automatically from the Monday
refresh job and successful live fetches; baseline fallback data is never
recorded. Feeds the dashboard sparklines (and F26).
"""

from app import db


class FuelPriceHistory(db.Model):
    __tablename__ = 'fuel_price_history'

    id = db.Column(db.Integer, primary_key=True)
    country = db.Column(db.String(2), nullable=False, index=True)
    price_date = db.Column(db.Date, nullable=False, index=True)
    diesel = db.Column(db.Numeric(8, 3))
    petrol = db.Column(db.Numeric(8, 3))
    lpg = db.Column(db.Numeric(8, 3))
    premium = db.Column(db.Numeric(8, 3))
    currency_code = db.Column(db.String(3))
    source = db.Column(db.String(64))

    __table_args__ = (
        db.UniqueConstraint('country', 'price_date',
                            name='uq_fuel_price_history_country_date'),
    )

    def to_dict(self):
        def _f(v):
            return float(v) if v is not None else None
        return {
            'date': self.price_date.isoformat() if self.price_date else None,
            'diesel': _f(self.diesel),
            'petrol': _f(self.petrol),
            'lpg': _f(self.lpg),
            'premium': _f(self.premium),
            'currency_code': self.currency_code,
        }

    def __repr__(self):
        return f'<FuelPriceHistory {self.country} {self.price_date}>'

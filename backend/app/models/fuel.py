"""
GearCargo - Fuel Entry Model
"""

from app import db
from app.models.entry import Entry


class FuelEntry(Entry):
    """Fuel entry for tracking fuel purchases."""
    
    __tablename__ = 'fuel_entries'
    
    id = db.Column(db.Integer, db.ForeignKey('entries.id'), primary_key=True)
    
    # Fuel specific fields
    liters = db.Column(db.Numeric(8, 2))
    price_per_liter = db.Column(db.Numeric(6, 3))
    total_price = db.Column(db.Numeric(10, 2))
    fuel_type = db.Column(db.String(20))  # regular, premium, diesel, e85
    station = db.Column(db.String(100))
    station_address = db.Column(db.String(255))
    full_tank = db.Column(db.Boolean, default=True)
    
    # Computed
    fuel_efficiency = db.Column(db.Float)  # L/100km calculated
    trip_distance = db.Column(db.Integer)  # vehicle distance unit since previous full tank
    
    # OCR
    ocr_populated = db.Column(db.Boolean, default=False)
    receipt_image = db.Column(db.String(255))
    
    __mapper_args__ = {
        'polymorphic_identity': 'fuel'
    }
    
    def calculate_efficiency(self, previous_odometer):
        """SUPERSEDED (F29) — naive previous-fill calculation, blind to partial
        fills. Kept for backwards compatibility only; the app now computes
        full-to-full figures via services/fuel_efficiency.recalculate_efficiencies.
        """
        from app.utils.units import distance_to_km
        self.trip_distance = self.fuel_efficiency = None
        if previous_odometer is not None and self.odometer is not None and self.liters is not None:
            distance = self.odometer - previous_odometer
            if distance > 0:
                self.trip_distance = distance
                km = distance_to_km(distance, getattr(self.vehicle, 'distance_unit', None))
                if km:
                    self.fuel_efficiency = float(self.liters) / float(km) * 100

    def to_dict(self, **kwargs):
        """Convert to dictionary."""
        data = super().to_dict(**kwargs)
        data.update({
            'liters': float(self.liters) if self.liters is not None else None,
            'price_per_liter': float(self.price_per_liter) if self.price_per_liter is not None else None,
            'station_address': self.station_address,
            'total_price': float(self.total_price) if self.total_price is not None else None,
            'fuel_type': self.fuel_type,
            'station': self.station,
            'full_tank': self.full_tank,
            'fuel_efficiency': self.fuel_efficiency,
            'trip_distance': self.trip_distance,
            'volume_unit': 'liters',
            'efficiency_unit': 'L/100km',
        })
        return data

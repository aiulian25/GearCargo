"""
GearCargo - Vehicle Model
"""

from datetime import datetime
from app import db


class Vehicle(db.Model):
    """Vehicle model for tracking cars/motorcycles/etc."""
    
    __tablename__ = 'vehicles'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    
    # Identification
    name = db.Column(db.String(100), nullable=False)  # Friendly name
    make = db.Column(db.String(50))
    model = db.Column(db.String(50))
    year = db.Column(db.Integer)
    vin = db.Column(db.String(17), unique=True, index=True)
    license_plate = db.Column(db.String(20))
    
    # Technical specs
    fuel_type = db.Column(db.String(20), default='petrol')  # petrol, diesel, electric, hybrid
    engine_cc = db.Column(db.Integer)
    transmission = db.Column(db.String(20))  # manual, automatic
    drivetrain = db.Column(db.String(10))  # fwd, rwd, awd
    color = db.Column(db.String(30))
    
    # Dimensions
    vehicle_weight_kg = db.Column(db.Integer)
    vehicle_height_cm = db.Column(db.Integer)
    vehicle_length_cm = db.Column(db.Integer)
    vehicle_width_cm = db.Column(db.Integer)
    
    # Mileage
    current_mileage = db.Column(db.Integer, default=0)
    distance_unit = db.Column(db.String(10), default='km')  # km or miles
    
    # Financial
    purchase_date = db.Column(db.Date)
    purchase_price = db.Column(db.Numeric(12, 2))
    monthly_budget = db.Column(db.Numeric(10, 2))
    
    # Analytics (computed)
    avg_trip_distance = db.Column(db.Float)
    city_driving_percentage = db.Column(db.Integer)
    highway_driving_percentage = db.Column(db.Integer)
    cost_per_km = db.Column(db.Float)
    avg_fuel_efficiency = db.Column(db.Float)  # L/100km or kWh/100km
    maintenance_score = db.Column(db.Integer)  # 0-100
    prediction_accuracy_score = db.Column(db.Float)
    
    # Status
    archived = db.Column(db.Boolean, default=False)
    archived_at = db.Column(db.DateTime)
    last_prediction_at = db.Column(db.DateTime)  # Last AI prediction run timestamp
    
    # Display order for dashboard (user-customizable)
    display_order = db.Column(db.Integer, default=0)
    
    # Image
    photo = db.Column(db.String(255))
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    fuel_entries = db.relationship('FuelEntry', backref='vehicle', lazy='dynamic', cascade='all, delete-orphan')
    service_entries = db.relationship('ServiceEntry', backref='vehicle', lazy='dynamic', cascade='all, delete-orphan')
    repair_entries = db.relationship('RepairEntry', backref='vehicle', lazy='dynamic', cascade='all, delete-orphan')
    tax_entries = db.relationship('TaxEntry', backref='vehicle', lazy='dynamic', cascade='all, delete-orphan')
    parking_entries = db.relationship('ParkingEntry', backref='vehicle', lazy='dynamic', cascade='all, delete-orphan')
    reminders = db.relationship('Reminder', backref='vehicle', lazy='dynamic', cascade='all, delete-orphan')
    predictions = db.relationship('PredictionAlert', backref='vehicle', lazy='dynamic', cascade='all, delete-orphan')
    attachments = db.relationship('Attachment', backref='vehicle', lazy='dynamic', cascade='all, delete-orphan')
    insurance_policies = db.relationship('InsurancePolicy', backref='vehicle', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Vehicle {self.name} ({self.make} {self.model})>'
    
    @property
    def full_name(self):
        """Return full vehicle name."""
        parts = [str(self.year) if self.year else '', self.make or '', self.model or '']
        return ' '.join(filter(None, parts)) or self.name
    
    def update_mileage(self, new_mileage):
        """Update mileage if greater than current."""
        if new_mileage and new_mileage > (self.current_mileage or 0):
            self.current_mileage = new_mileage

    def _signed_photo_url(self):
        """Return a signed URL for the vehicle photo."""
        if not self.photo:
            return None
        from app.utils import sign_upload_url
        return sign_upload_url(self.photo)

    def to_dict(self, include_stats=False):
        """Convert to dictionary."""
        data = {
            'id': self.id,
            'name': self.name,
            'full_name': self.full_name,
            'make': self.make,
            'model': self.model,
            'year': self.year,
            'vin': self.vin,
            'license_plate': self.license_plate,
            'fuel_type': self.fuel_type,
            'engine_cc': self.engine_cc,
            'transmission': self.transmission,
            'color': self.color,
            'current_mileage': self.current_mileage,
            'distance_unit': self.distance_unit,
            'monthly_budget': float(self.monthly_budget) if self.monthly_budget else None,
            'photo': self._signed_photo_url(),
            'photo_url': self._signed_photo_url(),
            'archived': self.archived,
            'archived_at': self.archived_at.isoformat() if self.archived_at else None,
            'display_order': self.display_order or 0,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
        
        if include_stats:
            data['stats'] = {
                'avg_fuel_efficiency': self.avg_fuel_efficiency,
                'cost_per_km': self.cost_per_km,
                'maintenance_score': self.maintenance_score,
                'fuel_entries_count': self.fuel_entries.count(),
                'service_entries_count': self.service_entries.count(),
                'active_reminders_count': self.reminders.filter_by(completed=False).count(),
            }
        
        return data

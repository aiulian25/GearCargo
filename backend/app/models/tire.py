"""Tire identities and lifecycle history; purchases remain ordinary expenses."""
from app import db
from app.utils.revisions import next_revision
from app.utils.timeutils import utc_naive_now


class TireSet(db.Model):
    __tablename__ = 'tire_sets'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey('vehicles.id'), nullable=False, index=True)
    revision = db.Column(db.BigInteger, nullable=False, default=1, server_default='1')
    __mapper_args__ = {'version_id_col': revision, 'version_id_generator': next_revision}
    name = db.Column(db.String(100), nullable=False)
    season = db.Column(db.String(12), nullable=False, default='all_season')
    storage_location = db.Column(db.String(200))
    purchase_entry_id = db.Column(db.Integer, db.ForeignKey('entries.id', ondelete='SET NULL'))
    rotation_interval = db.Column(db.Numeric(16, 6))  # vehicle's declared distance unit
    tread_unit = db.Column(db.String(8), nullable=False, default='mm')
    tread_threshold = db.Column(db.Numeric(10, 4))  # chosen tread_unit; no legal default
    created_at = db.Column(db.DateTime, nullable=False, default=utc_naive_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_naive_now, onupdate=utc_naive_now)
    tires = db.relationship('Tire', cascade='all, delete-orphan', order_by='Tire.id', lazy='selectin')
    events = db.relationship('FitmentEvent', cascade='all, delete-orphan', order_by='FitmentEvent.date, FitmentEvent.id', lazy='selectin')
    readings = db.relationship('TreadReading', cascade='all, delete-orphan', order_by='TreadReading.date, TreadReading.id', lazy='selectin')

    def to_dict(self):
        from app.services.tire_lifecycle import serialize_set
        return serialize_set(self)


class Tire(db.Model):
    __tablename__ = 'tires'
    __table_args__ = (db.UniqueConstraint('tire_set_id', 'identifier', name='uq_tire_set_identifier'),)
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_naive_now)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey('vehicles.id'), nullable=False, index=True)
    tire_set_id = db.Column(db.Integer, db.ForeignKey('tire_sets.id', ondelete='CASCADE'), nullable=False, index=True)
    identifier = db.Column(db.String(60), nullable=False)


class FitmentEvent(db.Model):
    __tablename__ = 'tire_fitments'
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_naive_now)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey('vehicles.id'), nullable=False, index=True)
    tire_set_id = db.Column(db.Integer, db.ForeignKey('tire_sets.id', ondelete='CASCADE'), nullable=False, index=True)
    kind = db.Column(db.String(10), nullable=False)
    date = db.Column(db.Date, nullable=False)
    odometer = db.Column(db.Numeric(16, 6))
    # FL/FR/RL/RR -> stable identifiers within the set, not database IDs.
    positions = db.Column(db.JSON, nullable=False)
    __table_args__ = (
        db.CheckConstraint("kind IN ('install', 'remove', 'rotate')", name='ck_tire_fitment_kind'),
        db.CheckConstraint('odometer IS NULL OR odometer >= 0', name='ck_tire_fitment_odometer'),
        db.Index('ix_tire_fitments_vehicle_date_id', 'vehicle_id', 'date', 'id'),
    )


class TreadReading(db.Model):
    __tablename__ = 'tread_readings'
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_naive_now)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey('vehicles.id'), nullable=False, index=True)
    tire_set_id = db.Column(db.Integer, db.ForeignKey('tire_sets.id', ondelete='CASCADE'), nullable=False, index=True)
    tire_id = db.Column(db.Integer, db.ForeignKey('tires.id', ondelete='CASCADE'), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False)
    depth = db.Column(db.Numeric(10, 4), nullable=False)
    unit = db.Column(db.String(8), nullable=False)
    __table_args__ = (
        db.CheckConstraint('depth >= 0', name='ck_tread_depth'),
        db.CheckConstraint("unit IN ('mm', '32nds')", name='ck_tread_unit'),
    )

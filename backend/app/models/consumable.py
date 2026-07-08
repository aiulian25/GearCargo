"""
GearCargo - Consumable Entry Model (tires, battery, wipers, filters, …)

A first-class expense entry type for wear-and-tear parts, with a mileage- and
time-based wear estimate. Mirrors the joined-table-inheritance pattern used by
fuel/service/repair/tax/parking entries.
"""

from datetime import date

from app import db
from app.models.entry import Entry


# Supported consumable categories. Kept as a plain allow-list (validated in the
# route) — the human-readable labels live in the frontend i18n files.
CONSUMABLE_TYPES = (
    'tire', 'battery', 'wipers', 'brake_pads', 'brake_discs',
    'air_filter', 'oil_filter', 'cabin_filter', 'fuel_filter',
    'coolant', 'spark_plugs', 'belt', 'other',
)

# Average days per month, for converting an age in days to months.
_DAYS_PER_MONTH = 30.44


class ConsumableEntry(Entry):
    """A consumable / wear part purchase + its expected lifespan."""

    __tablename__ = 'consumable_entries'

    id = db.Column(db.Integer, db.ForeignKey('entries.id'), primary_key=True)

    # What was replaced/installed
    consumable_type = db.Column(db.String(30))   # see CONSUMABLE_TYPES
    brand = db.Column(db.String(100))
    quantity = db.Column(db.Integer, default=1)  # e.g. 4 tyres, 2 wipers

    # Installation reference point for wear estimation
    install_date = db.Column(db.Date)
    install_odometer = db.Column(db.Integer)

    # Expected lifespan — either / both may be set; wear uses whichever is further along
    expected_lifespan_km = db.Column(db.Integer)
    expected_lifespan_months = db.Column(db.Integer)

    # Warranty
    warranty_months = db.Column(db.Integer)

    # Sentinel for the daily check_consumables_due job: set True once we have
    # pushed a "due for replacement" notification, so an item is never notified
    # twice for the same replace crossing. Internal — not exposed in to_dict().
    replace_notified = db.Column(db.Boolean, default=False)
    # F2: set once we've pushed a "warranty expiring soon" notification.
    warranty_notified = db.Column(db.Boolean, default=False)

    __mapper_args__ = {
        'polymorphic_identity': 'consumable'
    }

    # ------------------------------------------------------------------
    # Wear estimate
    # ------------------------------------------------------------------
    def wear_estimate(self, current_mileage=None):
        """Compute a mileage- and time-based wear estimate.

        Returns a dict with: wear_percent (0-100+, or None if not estimable),
        status ('unknown'|'good'|'monitor'|'replace'), and the underlying
        km/time usage so the UI can show details. The estimate is the MAX of the
        mileage-based and time-based progress (whichever predicts replacement
        sooner), which is the conservative, safety-oriented choice.
        """
        install_odo = self.install_odometer if self.install_odometer is not None else self.odometer
        install_dt = self.install_date or self.date

        km_used = None
        km_fraction = None
        remaining_km = None
        if self.expected_lifespan_km and install_odo is not None and current_mileage is not None:
            km_used = max(0, int(current_mileage) - int(install_odo))
            km_fraction = km_used / self.expected_lifespan_km
            remaining_km = self.expected_lifespan_km - km_used

        months_used = None
        time_fraction = None
        remaining_months = None
        if self.expected_lifespan_months and install_dt:
            days_used = max(0, (date.today() - install_dt).days)
            months_used = round(days_used / _DAYS_PER_MONTH, 1)
            time_fraction = (days_used / _DAYS_PER_MONTH) / self.expected_lifespan_months
            remaining_months = round(self.expected_lifespan_months - months_used, 1)

        fractions = [f for f in (km_fraction, time_fraction) if f is not None]
        if not fractions:
            return {
                'wear_percent': None,
                'status': 'unknown',
                'km_used': km_used,
                'remaining_km': remaining_km,
                'months_used': months_used,
                'remaining_months': remaining_months,
            }

        fraction = max(fractions)
        wear_percent = round(fraction * 100, 1)
        if fraction >= 1.0:
            status = 'replace'
        elif fraction >= 0.7:
            status = 'monitor'
        else:
            status = 'good'

        return {
            'wear_percent': wear_percent,
            'status': status,
            'km_used': km_used,
            'remaining_km': remaining_km,
            'months_used': months_used,
            'remaining_months': remaining_months,
        }

    def to_dict(self, current_mileage=None, **kwargs):
        """Serialise. Pass current_mileage (the vehicle's odometer) to include a
        wear estimate; omit it for contexts where the vehicle isn't loaded."""
        data = super().to_dict(**kwargs)
        data.update({
            'consumable_type': self.consumable_type,
            'brand': self.brand,
            'quantity': self.quantity,
            'install_date': self.install_date.isoformat() if self.install_date else None,
            'install_odometer': self.install_odometer,
            'expected_lifespan_km': self.expected_lifespan_km,
            'expected_lifespan_months': self.expected_lifespan_months,
            'warranty_months': self.warranty_months,
            'wear': self.wear_estimate(current_mileage=current_mileage),
        })
        return data

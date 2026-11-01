"""Manual workshop planning; money and receipts remain existing Entry records."""
from app import db
from app.utils.revisions import next_revision
from app.utils.timeutils import utc_naive_now, isoformat_utc


class Appointment(db.Model):
    __tablename__ = 'appointments'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey('vehicles.id'), nullable=False, index=True)
    revision = db.Column(db.BigInteger, nullable=False, default=1, server_default='1')
    __mapper_args__ = {'version_id_col': revision, 'version_id_generator': next_revision}
    title = db.Column(db.String(255), nullable=False)
    shop_name = db.Column(db.String(100))
    shop_contact = db.Column(db.String(255))
    notes = db.Column(db.Text)
    status = db.Column(db.String(12), nullable=False, default='requested')
    time_zone = db.Column(db.String(64), nullable=False)
    # UTC instants, following the application's naive-UTC storage convention.
    start_at = db.Column(db.DateTime, nullable=False)
    end_at = db.Column(db.DateTime, nullable=False)
    confirmed_at = db.Column(db.DateTime)
    dropoff_at = db.Column(db.DateTime)
    pickup_at = db.Column(db.DateTime)
    prepare_minutes = db.Column(db.Integer, nullable=False, default=1440)
    notify_push = db.Column(db.Boolean, nullable=False, default=False)
    notify_email = db.Column(db.Boolean, nullable=False, default=False)
    preparation_reminder_id = db.Column(db.Integer, db.ForeignKey('reminders.id', ondelete='SET NULL'), unique=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_naive_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_naive_now, onupdate=utc_naive_now)
    vehicle = db.relationship('Vehicle')
    tasks = db.relationship('AppointmentTask', cascade='all, delete-orphan', lazy='selectin', order_by='AppointmentTask.id')
    expenses = db.relationship('AppointmentExpense', cascade='all, delete-orphan', lazy='selectin', order_by='AppointmentExpense.id')
    __table_args__ = (
        db.CheckConstraint("status IN ('requested','confirmed','completed','cancelled')", name='ck_appointment_status'),
        db.CheckConstraint('end_at > start_at', name='ck_appointment_interval'),
        db.CheckConstraint('prepare_minutes >= 0 AND prepare_minutes <= 43200', name='ck_appointment_preparation'),
    )

    def to_dict(self):
        from datetime import timezone
        from zoneinfo import ZoneInfo
        zone = ZoneInfo(self.time_zone)
        local = lambda value: value.replace(tzinfo=timezone.utc).astimezone(zone)
        return {**{k: getattr(self, k) for k in ('id', 'revision', 'vehicle_id', 'title', 'shop_name', 'shop_contact', 'notes', 'status', 'time_zone', 'prepare_minutes', 'notify_push', 'notify_email', 'preparation_reminder_id')},
            **{k: isoformat_utc(getattr(self, k)) for k in ('start_at', 'end_at', 'confirmed_at', 'dropoff_at', 'pickup_at', 'created_at', 'updated_at')},
            'start_local': local(self.start_at).strftime('%Y-%m-%dT%H:%M'), 'end_local': local(self.end_at).strftime('%Y-%m-%dT%H:%M'),
            'start_fold': local(self.start_at).fold, 'end_fold': local(self.end_at).fold,
            'tasks': [t.to_dict() for t in self.tasks], 'expenses': [e.to_dict() for e in self.expenses]}


class AppointmentTask(db.Model):
    __tablename__ = 'appointment_tasks'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey('vehicles.id'), nullable=False, index=True)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointments.id', ondelete='CASCADE'), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    done = db.Column(db.Boolean, nullable=False, default=False)
    reminder_id = db.Column(db.Integer, db.ForeignKey('reminders.id', ondelete='SET NULL'))
    todo_id = db.Column(db.Integer, db.ForeignKey('todos.id', ondelete='SET NULL'))
    service_id = db.Column(db.Integer, db.ForeignKey('service_entries.id', ondelete='SET NULL'))
    prediction_id = db.Column(db.Integer, db.ForeignKey('prediction_alerts.id', ondelete='SET NULL'))
    source_signature = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, nullable=False, default=utc_naive_now)

    def to_dict(self):
        return {k: getattr(self, k) for k in ('id', 'title', 'done', 'reminder_id', 'todo_id', 'service_id', 'prediction_id')}


class AppointmentExpense(db.Model):
    __tablename__ = 'appointment_expenses'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey('vehicles.id'), nullable=False, index=True)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointments.id', ondelete='CASCADE'), nullable=False, index=True)
    entry_id = db.Column(db.Integer, db.ForeignKey('entries.id', ondelete='CASCADE'), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_naive_now)
    entry = db.relationship('Entry')

    def to_dict(self):
        return {'id': self.id, 'entry_id': self.entry_id, 'type': self.entry.type,
            'title': self.entry.title, 'amount': float(self.entry.amount) if self.entry.amount is not None else None,
            'currency': self.entry.currency, 'date': self.entry.date.isoformat()}

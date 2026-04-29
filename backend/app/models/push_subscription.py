"""
GearCargo - Push Subscription Model
"""

from datetime import datetime, timezone
from app import db


class PushSubscription(db.Model):
    """Web Push subscription model."""
    
    __tablename__ = 'push_subscriptions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    
    # Subscription data
    endpoint = db.Column(db.Text, nullable=False)
    p256dh_key = db.Column(db.String(255), nullable=False)
    auth_key = db.Column(db.String(255), nullable=False)
    
    # Device info
    device_name = db.Column(db.String(255))
    device_type = db.Column(db.String(50))  # mobile, tablet, desktop
    browser = db.Column(db.String(100))
    os = db.Column(db.String(100))
    
    # Status
    active = db.Column(db.Boolean, default=True)
    last_used_at = db.Column(db.DateTime)
    error_count = db.Column(db.Integer, default=0)
    last_error = db.Column(db.Text)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Unique constraint on endpoint
    __table_args__ = (
        db.UniqueConstraint('endpoint', name='uq_push_endpoint'),
    )
    
    def __repr__(self):
        return f'<PushSubscription {self.id} - {self.device_type}>'
    
    def get_subscription_info(self):
        """Get subscription info for pywebpush."""
        return {
            'endpoint': self.endpoint,
            'keys': {
                'p256dh': self.p256dh_key,
                'auth': self.auth_key,
            }
        }
    
    def mark_used(self):
        """Mark subscription as recently used."""
        self.last_used_at = datetime.now(timezone.utc)
        self.error_count = 0
        self.last_error = None
    
    def mark_error(self, error_message):
        """Record a push error."""
        self.error_count += 1
        self.last_error = error_message
        
        # Deactivate after too many errors
        if self.error_count >= 5:
            self.active = False
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            'id': self.id,
            'device_name': self.device_name,
            'device_type': self.device_type,
            'browser': self.browser,
            'os': self.os,
            'active': self.active,
            'last_used_at': self.last_used_at.isoformat() if self.last_used_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class NotificationLog(db.Model):
    """Log of sent notifications."""
    
    __tablename__ = 'notification_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey('push_subscriptions.id'), index=True)
    
    # Notification content
    notification_type = db.Column(db.String(50), nullable=False)  # reminder, prediction, system
    title = db.Column(db.String(255), nullable=False)
    body = db.Column(db.Text)
    data = db.Column(db.JSON)
    
    # Related objects
    reminder_id = db.Column(db.Integer, db.ForeignKey('reminders.id'))
    prediction_id = db.Column(db.Integer, db.ForeignKey('prediction_alerts.id'))
    vehicle_id = db.Column(db.Integer, db.ForeignKey('vehicles.id'))
    
    # Delivery status
    channel = db.Column(db.String(20), nullable=False)  # push, email, sms
    status = db.Column(db.String(20), default='pending')  # pending, sent, delivered, failed, clicked
    error_message = db.Column(db.Text)
    
    # Interaction
    clicked_at = db.Column(db.DateTime)
    action_taken = db.Column(db.String(50))
    
    # Timestamps
    scheduled_at = db.Column(db.DateTime)
    sent_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<NotificationLog {self.id} - {self.notification_type}>'
    
    def mark_sent(self):
        """Mark notification as sent."""
        self.status = 'sent'
        self.sent_at = datetime.now(timezone.utc)
    
    def mark_clicked(self, action=None):
        """Mark notification as clicked."""
        self.status = 'clicked'
        self.clicked_at = datetime.now(timezone.utc)
        if action:
            self.action_taken = action
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            'id': self.id,
            'notification_type': self.notification_type,
            'title': self.title,
            'body': self.body,
            'channel': self.channel,
            'status': self.status,
            'clicked_at': self.clicked_at.isoformat() if self.clicked_at else None,
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

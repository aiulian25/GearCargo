"""
GearCargo - User Model
"""

from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from flask_login import UserMixin
from app import db, bcrypt, login_manager


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class User(UserMixin, db.Model):
    """User model for authentication and profile."""
    
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    
    # Profile
    first_name = db.Column(db.String(50))
    last_name = db.Column(db.String(50))
    avatar = db.Column(db.String(255))
    
    # Preferences
    language = db.Column(db.String(10), default='en')
    timezone = db.Column(db.String(50), default='UTC')
    theme = db.Column(db.String(10), default='dark')
    currency = db.Column(db.String(5), default='GBP')  # Currency code (GBP, EUR, RON, USD)
    distance_unit = db.Column(db.String(10), default='km')  # km or miles
    volume_unit = db.Column(db.String(10), default='liters')  # liters or gallons
    date_format = db.Column(db.String(20), default='DD/MM/YYYY')  # Date display format
    country_preference = db.Column(db.String(3))  # ISO country code
    preferences = db.Column(db.JSON, default=dict)
    
    # 2FA / Security
    two_factor_secret = db.Column(db.Text)  # Encrypted (Fernet) — S06
    two_factor_enabled = db.Column(db.Boolean, default=False)
    two_factor_backup_codes = db.Column(db.JSON)
    email_otp_secret = db.Column(db.Text)  # Encrypted (Fernet) — S15; widened from String(32)
    email_verified = db.Column(db.Boolean, default=False)
    email_verification_token = db.Column(db.String(255))
    email_verification_expires = db.Column(db.DateTime)  # Token expiration
    password_reset_token = db.Column(db.String(255))
    password_reset_expires = db.Column(db.DateTime)
    last_password_change = db.Column(db.DateTime)
    
    # Security Questions for account recovery
    security_questions = db.Column(db.JSON)  # [{question: str, answer_hash: str}, ...]
    security_questions_set_at = db.Column(db.DateTime)
    
    # Status
    is_active = db.Column(db.Boolean, default=True)
    is_admin = db.Column(db.Boolean, default=False)
    is_dummy = db.Column(db.Boolean, default=False)  # Initial admin marker
    must_change_password = db.Column(db.Boolean, default=False)  # Force password change on next login
    
    # Limits
    vehicle_limit = db.Column(db.Integer, default=10)
    max_sessions = db.Column(db.Integer, default=10)  # Max concurrent sessions (1 = single device)
    
    # API Key for external integrations (Gethomepage, etc.)
    api_key = db.Column(db.String(64), nullable=True)  # DEPRECATED — nulled post-migration; use api_key_hash (S07)
    api_key_hash = db.Column(db.String(64), unique=True, index=True, nullable=True)  # SHA-256 hex of raw key (S07)
    api_key_prefix = db.Column(db.String(12), nullable=True)  # First 8 chars for display only (S07)
    
    # Email Notifications
    notifications_enabled = db.Column(db.Boolean, default=True)  # Master switch
    notification_email = db.Column(db.Text)  # Encrypted (Fernet) custom notification email
    notification_email_hash = db.Column(db.String(64), index=True)  # SHA-256 for lookups
    notification_email_verified = db.Column(db.Boolean, default=False)
    notification_email_token = db.Column(db.String(255))  # Verification token
    notification_email_token_exp = db.Column(db.DateTime)  # Token expiry
    notification_email_consented_at = db.Column(db.DateTime)  # GDPR consent timestamp
    notification_email_consent_ip = db.Column(db.String(45))  # IP at consent time
    notification_email_bounce_count = db.Column(db.Integer, default=0)  # Auto-disable after N bounces
    unsubscribe_token = db.Column(db.String(64), unique=True, index=True)  # For one-click unsubscribe
    email_insurance_alerts = db.Column(db.Boolean, default=True)
    email_tax_alerts = db.Column(db.Boolean, default=True)
    email_service_alerts = db.Column(db.Boolean, default=True)
    email_reminder_alerts = db.Column(db.Boolean, default=True)
    email_smart_alerts = db.Column(db.Boolean, default=True)
    login_alerts_enabled = db.Column(db.Boolean, default=True)  # S18: opt-out for suspicious login/device detection
    daily_alerts_enabled = db.Column(db.Boolean, default=True)   # Controls the 8 AM daily alert digest
    weekly_report_enabled = db.Column(db.Boolean, default=False)
    monthly_report_enabled = db.Column(db.Boolean, default=True)
    alert_days_before = db.Column(db.Integer, default=14)  # Days before due date to alert
    last_weekly_report = db.Column(db.DateTime)
    last_monthly_report = db.Column(db.DateTime)
    
    # Location Settings
    location_lat = db.Column(db.Float)  # User's saved latitude
    location_lon = db.Column(db.Float)  # User's saved longitude
    location_name = db.Column(db.String(255))  # Human readable location (e.g., "Brighton, UK")
    location_auto_detect = db.Column(db.Boolean, default=True)  # Auto-detect or use saved
    
    # Calendar Sync
    calendar_enabled = db.Column(db.Boolean, default=False)
    calendar_provider = db.Column(db.String(50))  # google, nextcloud, baikal, radicale, caldav
    calendar_url = db.Column(db.String(500))  # CalDAV URL
    calendar_username = db.Column(db.String(255))
    calendar_password = db.Column(db.Text)  # Encrypted
    calendar_id = db.Column(db.String(255))  # Specific calendar to use
    calendar_last_sync = db.Column(db.DateTime)
    
    # DB-backed lockout fallback (used when Redis is unavailable)
    failed_login_attempts = db.Column(db.Integer, default=0, nullable=False, server_default='0')
    locked_until = db.Column(db.DateTime, nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    # Relationships
    vehicles = db.relationship('Vehicle', backref='owner', lazy='dynamic', cascade='all, delete-orphan')
    reminders = db.relationship('Reminder', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    backups = db.relationship('Backup', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    push_subscriptions = db.relationship('PushSubscription', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<User {self.username}>'
    
    def set_password(self, password):
        """Hash and set the password."""
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
        self.last_password_change = datetime.now(timezone.utc)
    
    def check_password(self, password):
        """Check password against hash."""
        return bcrypt.check_password_hash(self.password_hash, password)
    
    @staticmethod
    def _hash_reset_token(raw_token: str) -> str:
        """Return SHA-256 hex digest of a raw reset token (S08)."""
        return hashlib.sha256(raw_token.encode('utf-8')).hexdigest()

    def generate_reset_token(self, expires_hours=24):
        """Generate a password reset token.

        Stores only the SHA-256 hash in the database (S08).
        Returns the raw token — callers must deliver it to the user and never store it.
        """
        raw_token = secrets.token_urlsafe(32)
        self.password_reset_token = User._hash_reset_token(raw_token)  # store hash only
        self.password_reset_expires = datetime.now(timezone.utc) + timedelta(hours=expires_hours)
        db.session.commit()
        return raw_token  # raw token returned once — never stored
    
    @staticmethod
    def verify_reset_token(token):
        """Verify a password reset token and return the user.

        Hashes the incoming token before DB lookup so the column never holds a
        plaintext value that could be used directly if the DB is read (S08).
        """
        if not token:
            return None
        hashed = User._hash_reset_token(token)
        user = User.query.filter_by(password_reset_token=hashed).first()
        if user is None:
            return None
        if user.password_reset_expires is None or user.password_reset_expires < datetime.now(timezone.utc):
            return None
        return user
    
    def generate_verification_token(self, expires_hours=48):
        """Generate an email verification token."""
        self.email_verification_token = secrets.token_urlsafe(32)
        self.email_verification_expires = datetime.now(timezone.utc) + timedelta(hours=expires_hours)
        db.session.commit()
        return self.email_verification_token
    
    @staticmethod
    def verify_email_token(token):
        """Verify an email verification token and return the user."""
        if not token:
            return None
        user = User.query.filter_by(email_verification_token=token).first()
        if user is None:
            return None
        if user.email_verification_expires is None or user.email_verification_expires < datetime.now(timezone.utc):
            return None
        return user
    
    def mark_email_verified(self):
        """Mark email as verified and clear the token."""
        self.email_verified = True
        self.email_verification_token = None
        self.email_verification_expires = None
        db.session.commit()
    
    def set_security_questions(self, questions_and_answers):
        """
        Set security questions for account recovery.
        
        Args:
            questions_and_answers: List of dicts with 'question' and 'answer' keys
        """
        from werkzeug.security import generate_password_hash
        
        hashed_qs = []
        for qa in questions_and_answers:
            # Normalize the answer: lowercase, strip whitespace
            normalized_answer = qa['answer'].lower().strip()
            hashed_qs.append({
                'question': qa['question'],
                'answer_hash': generate_password_hash(normalized_answer, method='pbkdf2:sha256')
            })
        
        self.security_questions = hashed_qs
        self.security_questions_set_at = datetime.now(timezone.utc)
        db.session.commit()
    
    def verify_security_answers(self, answers):
        """
        Verify security question answers.
        
        Args:
            answers: List of answer strings in the same order as stored questions
        
        Returns:
            True if all answers match, False otherwise
        """
        from werkzeug.security import check_password_hash
        
        if not self.security_questions or len(answers) != len(self.security_questions):
            return False
        
        for i, qa in enumerate(self.security_questions):
            # Normalize the answer
            normalized_answer = answers[i].lower().strip()
            if not check_password_hash(qa['answer_hash'], normalized_answer):
                return False
        
        return True
    
    def has_security_questions(self):
        """Check if user has security questions set up."""
        return bool(self.security_questions and len(self.security_questions) >= 2)
    
    def get_security_questions(self):
        """Get the security questions (without answers) for display during recovery."""
        if not self.security_questions:
            return []
        return [qa['question'] for qa in self.security_questions]
    
    @property
    def display_name(self):
        """Return display name."""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.username

    def get_decrypted_notification_email(self):
        """Decrypt the notification email field. Returns empty string if not set."""
        if not self.notification_email:
            return ''
        try:
            from app.utils.encryption import decrypt_field
            return decrypt_field(self.notification_email)
        except Exception:
            return ''

    def get_effective_notification_email(self):
        """Return the verified notification email, or fall back to account email."""
        if self.notification_email and self.notification_email_verified:
            decrypted = self.get_decrypted_notification_email()
            if decrypted:
                return decrypted
        return self.email

    def set_notification_email_encrypted(self, plaintext_email):
        """Encrypt and store a notification email + its hash."""
        from app.utils.encryption import encrypt_field, hash_email
        if plaintext_email:
            self.notification_email = encrypt_field(plaintext_email.strip().lower())
            self.notification_email_hash = hash_email(plaintext_email)
        else:
            self.notification_email = None
            self.notification_email_hash = None

    def generate_unsubscribe_token(self):
        """Generate a unique unsubscribe token if not already set."""
        if not self.unsubscribe_token:
            self.unsubscribe_token = secrets.token_urlsafe(48)
        return self.unsubscribe_token

    def generate_notification_email_token(self, expires_hours=72):
        """Generate a verification token for the notification email."""
        self.notification_email_token = secrets.token_urlsafe(32)
        self.notification_email_token_exp = datetime.now(timezone.utc) + timedelta(hours=expires_hours)
        return self.notification_email_token

    def _signed_avatar_url(self):
        """Return a signed URL for the user avatar."""
        if not self.avatar:
            return None
        from app.utils import sign_upload_url
        return sign_upload_url(self.avatar)

    def to_dict(self, include_private=False):
        """Convert to dictionary."""
        data = {
            'id': self.id,
            'username': self.username,
            'name': self.display_name,  # Alias for frontend compatibility
            'email': self.email,
            'display_name': self.display_name,
            'avatar': self._signed_avatar_url(),
            # User preferences - always included for frontend sync
            'language': self.language or 'en',
            'timezone': self.timezone or 'UTC',
            'theme': self.theme or 'dark',
            'currency': self.currency or 'GBP',
            'distance_unit': self.distance_unit or 'km',
            'volume_unit': self.volume_unit or 'liters',
            'date_format': self.date_format or 'DD/MM/YYYY',
            'country_preference': self.country_preference,
            # Location settings
            'location_lat': self.location_lat,
            'location_lon': self.location_lon,
            'location_name': self.location_name,
            'location_auto_detect': self.location_auto_detect if self.location_auto_detect is not None else True,
            # Account info
            'is_admin': self.is_admin,
            'is_active': self.is_active if self.is_active is not None else True,
            'must_change_password': self.must_change_password,
            'two_factor_enabled': self.two_factor_enabled,
            'email_verified': self.email_verified,
            'security_questions_configured': self.has_security_questions(),
            'security_questions_status': {
                'configured': self.has_security_questions(),
                'count': len(self.security_questions) if self.security_questions else 0,
                'set_at': self.security_questions_set_at.isoformat() if self.security_questions_set_at else None
            },
            'vehicle_limit': self.vehicle_limit,
            'vehicle_count': self.vehicles.count(),
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
        
        if include_private:
            data['preferences'] = self.preferences
            # Email notification settings
            data['notifications_enabled'] = self.notifications_enabled if self.notifications_enabled is not None else True
            data['notification_email'] = self.get_decrypted_notification_email()
            data['notification_email_verified'] = self.notification_email_verified or False
            data['email_insurance_alerts'] = self.email_insurance_alerts if self.email_insurance_alerts is not None else True
            data['email_tax_alerts'] = self.email_tax_alerts if self.email_tax_alerts is not None else True
            data['email_service_alerts'] = self.email_service_alerts if self.email_service_alerts is not None else True
            data['email_reminder_alerts'] = self.email_reminder_alerts if self.email_reminder_alerts is not None else True
            data['email_smart_alerts'] = self.email_smart_alerts if self.email_smart_alerts is not None else True
            data['login_alerts_enabled'] = self.login_alerts_enabled if self.login_alerts_enabled is not None else True
            data['daily_alerts_enabled'] = self.daily_alerts_enabled if self.daily_alerts_enabled is not None else True
            data['weekly_report_enabled'] = self.weekly_report_enabled if self.weekly_report_enabled is not None else False
            data['monthly_report_enabled'] = self.monthly_report_enabled if self.monthly_report_enabled is not None else True
            data['alert_days_before'] = self.alert_days_before or 14
            # Calendar sync settings
            data['calendar_enabled'] = self.calendar_enabled if self.calendar_enabled is not None else False
            data['calendar_provider'] = self.calendar_provider
            data['calendar_url'] = self.calendar_url
            data['calendar_username'] = self.calendar_username
            data['calendar_id'] = self.calendar_id
            data['calendar_configured'] = bool(self.calendar_provider and self.calendar_url and self.calendar_username)
            data['calendar_last_sync'] = self.calendar_last_sync.isoformat() if self.calendar_last_sync else None
        
        return data

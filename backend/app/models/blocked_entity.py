"""
GearCargo - Blocked IP and Device Models
For security - tracking and blocking malicious IPs and devices
"""

from datetime import datetime
from app import db


class BlockedIP(db.Model):
    """Blocked IP addresses - either auto-blocked or manually blocked by admin."""
    
    __tablename__ = 'blocked_ips'
    
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(45), nullable=False, unique=True, index=True)
    
    # Block reason and type
    reason = db.Column(db.String(500))
    block_type = db.Column(db.String(20), default='auto')  # 'auto' or 'manual'
    
    # Auto-block tracking
    failed_attempts = db.Column(db.Integer, default=0)
    last_failed_attempt = db.Column(db.DateTime)
    
    # Admin who manually blocked (if manual)
    blocked_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    blocked_by = db.relationship('User', foreign_keys=[blocked_by_id], backref='blocked_ips')
    
    # Unblock info
    is_active = db.Column(db.Boolean, default=True)  # False = unblocked
    unblocked_at = db.Column(db.DateTime, nullable=True)
    unblocked_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    unblocked_by = db.relationship('User', foreign_keys=[unblocked_by_id])
    unblock_reason = db.Column(db.String(500))
    
    # Geolocation info
    country = db.Column(db.String(100))
    country_code = db.Column(db.String(5))
    city = db.Column(db.String(100))
    isp = db.Column(db.String(200))
    
    # Associated user (if login attempts were for a specific user)
    target_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    target_user = db.relationship('User', foreign_keys=[target_user_id])
    target_email = db.Column(db.String(255))  # Email they tried to login with
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    expires_at = db.Column(db.DateTime, nullable=True)  # Auto-blocks can expire
    
    def __repr__(self):
        return f'<BlockedIP {self.ip_address}>'
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            'id': self.id,
            'ip_address': self.ip_address,
            'reason': self.reason,
            'block_type': self.block_type,
            'failed_attempts': self.failed_attempts,
            'last_failed_attempt': self.last_failed_attempt.isoformat() if self.last_failed_attempt else None,
            'blocked_by': self.blocked_by.email if self.blocked_by else None,
            'is_active': self.is_active,
            'unblocked_at': self.unblocked_at.isoformat() if self.unblocked_at else None,
            'unblocked_by': self.unblocked_by.email if self.unblocked_by else None,
            'unblock_reason': self.unblock_reason,
            'country': self.country,
            'country_code': self.country_code,
            'city': self.city,
            'isp': self.isp,
            'target_user_id': self.target_user_id,
            'target_email': self.target_email,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
        }
    
    @classmethod
    def is_blocked(cls, ip_address):
        """Check if an IP is currently blocked."""
        blocked = cls.query.filter_by(ip_address=ip_address, is_active=True).first()
        if blocked:
            # Check if block has expired
            if blocked.expires_at and blocked.expires_at < datetime.utcnow():
                blocked.is_active = False
                db.session.commit()
                return False, None
            return True, blocked
        return False, None
    
    @classmethod
    def record_failed_attempt(cls, ip_address, email=None, user_id=None, location_info=None, max_attempts=3):
        """
        Record a failed login attempt from this IP.
        Auto-blocks after max_attempts (default 3).
        Returns (is_blocked, blocked_record, attempt_count)
        """
        existing = cls.query.filter_by(ip_address=ip_address).first()
        
        if existing:
            if existing.is_active:
                # Already blocked
                return True, existing, existing.failed_attempts
            
            # Previously blocked but now unblocked - increment counter
            existing.failed_attempts += 1
            existing.last_failed_attempt = datetime.utcnow()
            if email:
                existing.target_email = email
            if user_id:
                existing.target_user_id = user_id
            
            # Re-block if reached threshold again
            if existing.failed_attempts >= max_attempts:
                existing.is_active = True
                existing.reason = f'Auto-blocked: {existing.failed_attempts} failed login attempts'
                existing.block_type = 'auto'
                existing.unblocked_at = None
                existing.unblocked_by_id = None
                existing.unblock_reason = None
                db.session.commit()
                return True, existing, existing.failed_attempts
            
            db.session.commit()
            return False, existing, existing.failed_attempts
        
        # New IP - create record
        new_record = cls(
            ip_address=ip_address,
            failed_attempts=1,
            last_failed_attempt=datetime.utcnow(),
            target_email=email,
            target_user_id=user_id,
            is_active=False,  # Not blocked yet
        )
        
        # Add location info if available
        if location_info:
            new_record.country = location_info.get('country')
            new_record.country_code = location_info.get('country_code')
            new_record.city = location_info.get('city')
            new_record.isp = location_info.get('isp')
        
        db.session.add(new_record)
        db.session.commit()
        
        return False, new_record, 1
    
    @classmethod
    def clear_attempts(cls, ip_address):
        """Clear failed attempts on successful login (if not blocked)."""
        record = cls.query.filter_by(ip_address=ip_address, is_active=False).first()
        if record:
            record.failed_attempts = 0
            db.session.commit()


class BlockedDevice(db.Model):
    """Blocked devices based on device fingerprint/user agent."""
    
    __tablename__ = 'blocked_devices'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Device identification
    device_fingerprint = db.Column(db.String(64), nullable=False, index=True)  # SHA256 hash
    user_agent = db.Column(db.String(500))
    
    # Parsed device info
    device_type = db.Column(db.String(50))  # desktop, mobile, tablet
    browser = db.Column(db.String(100))
    browser_version = db.Column(db.String(20))
    os = db.Column(db.String(100))
    os_version = db.Column(db.String(20))
    
    # Block reason and type
    reason = db.Column(db.String(500))
    block_type = db.Column(db.String(20), default='auto')  # 'auto' or 'manual'
    
    # Auto-block tracking
    failed_attempts = db.Column(db.Integer, default=0)
    last_failed_attempt = db.Column(db.DateTime)
    associated_ips = db.Column(db.JSON, default=list)  # List of IPs used with this device
    
    # Admin who manually blocked (if manual)
    blocked_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    blocked_by = db.relationship('User', foreign_keys=[blocked_by_id], backref='blocked_devices')
    
    # Unblock info
    is_active = db.Column(db.Boolean, default=True)
    unblocked_at = db.Column(db.DateTime, nullable=True)
    unblocked_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    unblocked_by = db.relationship('User', foreign_keys=[unblocked_by_id])
    unblock_reason = db.Column(db.String(500))
    
    # Associated user
    target_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    target_user = db.relationship('User', foreign_keys=[target_user_id])
    target_email = db.Column(db.String(255))
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    
    def __repr__(self):
        return f'<BlockedDevice {self.device_fingerprint[:8]}...>'
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            'id': self.id,
            'device_fingerprint': self.device_fingerprint,
            'user_agent': self.user_agent,
            'device_type': self.device_type,
            'browser': self.browser,
            'browser_version': self.browser_version,
            'os': self.os,
            'os_version': self.os_version,
            'reason': self.reason,
            'block_type': self.block_type,
            'failed_attempts': self.failed_attempts,
            'last_failed_attempt': self.last_failed_attempt.isoformat() if self.last_failed_attempt else None,
            'associated_ips': self.associated_ips,
            'blocked_by': self.blocked_by.email if self.blocked_by else None,
            'is_active': self.is_active,
            'unblocked_at': self.unblocked_at.isoformat() if self.unblocked_at else None,
            'unblocked_by': self.unblocked_by.email if self.unblocked_by else None,
            'unblock_reason': self.unblock_reason,
            'target_user_id': self.target_user_id,
            'target_email': self.target_email,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
        }
    
    @staticmethod
    def generate_fingerprint(user_agent, ip_address=None):
        """Generate a device fingerprint from user agent (and optionally IP for uniqueness)."""
        import hashlib
        # Use user agent as the primary identifier
        # Can add more signals in the future (canvas fingerprint, etc.)
        data = user_agent or 'unknown'
        return hashlib.sha256(data.encode()).hexdigest()
    
    @classmethod
    def is_blocked(cls, user_agent, ip_address=None):
        """Check if a device is currently blocked."""
        fingerprint = cls.generate_fingerprint(user_agent, ip_address)
        blocked = cls.query.filter_by(device_fingerprint=fingerprint, is_active=True).first()
        if blocked:
            if blocked.expires_at and blocked.expires_at < datetime.utcnow():
                blocked.is_active = False
                db.session.commit()
                return False, None
            return True, blocked
        return False, None
    
    @classmethod
    def record_failed_attempt(cls, user_agent, ip_address, email=None, user_id=None, device_info=None, max_attempts=3):
        """
        Record a failed login attempt from this device.
        Auto-blocks after max_attempts (default 3).
        Returns (is_blocked, blocked_record, attempt_count)
        """
        fingerprint = cls.generate_fingerprint(user_agent, ip_address)
        existing = cls.query.filter_by(device_fingerprint=fingerprint).first()
        
        if existing:
            if existing.is_active:
                # Already blocked - update associated IPs
                if ip_address and (not existing.associated_ips or ip_address not in existing.associated_ips):
                    ips = existing.associated_ips or []
                    if ip_address not in ips:
                        ips.append(ip_address)
                        existing.associated_ips = ips
                        db.session.commit()
                return True, existing, existing.failed_attempts
            
            # Previously blocked but now unblocked - increment counter
            existing.failed_attempts += 1
            existing.last_failed_attempt = datetime.utcnow()
            if email:
                existing.target_email = email
            if user_id:
                existing.target_user_id = user_id
            
            # Update associated IPs
            if ip_address:
                ips = existing.associated_ips or []
                if ip_address not in ips:
                    ips.append(ip_address)
                    existing.associated_ips = ips
            
            # Re-block if reached threshold
            if existing.failed_attempts >= max_attempts:
                existing.is_active = True
                existing.reason = f'Auto-blocked: {existing.failed_attempts} failed login attempts'
                existing.block_type = 'auto'
                existing.unblocked_at = None
                existing.unblocked_by_id = None
                existing.unblock_reason = None
                db.session.commit()
                return True, existing, existing.failed_attempts
            
            db.session.commit()
            return False, existing, existing.failed_attempts
        
        # New device - create record
        new_record = cls(
            device_fingerprint=fingerprint,
            user_agent=user_agent,
            failed_attempts=1,
            last_failed_attempt=datetime.utcnow(),
            target_email=email,
            target_user_id=user_id,
            is_active=False,
            associated_ips=[ip_address] if ip_address else [],
        )
        
        # Add device info if available
        if device_info:
            new_record.device_type = device_info.get('device_type')
            new_record.browser = device_info.get('browser')
            new_record.browser_version = device_info.get('browser_version')
            new_record.os = device_info.get('os')
            new_record.os_version = device_info.get('os_version')
        
        db.session.add(new_record)
        db.session.commit()
        
        return False, new_record, 1
    
    @classmethod
    def clear_attempts(cls, user_agent, ip_address=None):
        """Clear failed attempts on successful login (if not blocked)."""
        fingerprint = cls.generate_fingerprint(user_agent, ip_address)
        record = cls.query.filter_by(device_fingerprint=fingerprint, is_active=False).first()
        if record:
            record.failed_attempts = 0
            db.session.commit()

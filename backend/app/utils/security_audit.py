"""
Security Audit Logger

Provides dedicated logging for security-relevant events with structured JSON output.
Events logged: login attempts, password changes, 2FA changes, account lockouts,
new device logins, suspicious locations, token invalidations, profile changes.
"""
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from flask import request, current_app, has_request_context


class SecurityAuditLogger:
    """Dedicated logger for security audit events."""
    
    # Event types for categorization
    EVENT_LOGIN_SUCCESS = 'LOGIN_SUCCESS'
    EVENT_LOGIN_FAILED = 'LOGIN_FAILED'
    EVENT_LOGIN_LOCKED = 'LOGIN_LOCKED'
    EVENT_LOGIN_NEW_DEVICE = 'LOGIN_NEW_DEVICE'
    EVENT_LOGIN_SUSPICIOUS_LOCATION = 'LOGIN_SUSPICIOUS_LOCATION'
    EVENT_LOGOUT = 'LOGOUT'
    EVENT_PASSWORD_CHANGE = 'PASSWORD_CHANGE'
    EVENT_PASSWORD_RESET_REQUEST = 'PASSWORD_RESET_REQUEST'
    EVENT_PASSWORD_RESET_COMPLETE = 'PASSWORD_RESET_COMPLETE'
    EVENT_2FA_ENABLED = '2FA_ENABLED'
    EVENT_2FA_DISABLED = '2FA_DISABLED'
    EVENT_2FA_FAILED = '2FA_FAILED'
    EVENT_ACCOUNT_CREATED = 'ACCOUNT_CREATED'
    EVENT_ACCOUNT_DELETED = 'ACCOUNT_DELETED'
    EVENT_PROFILE_UPDATED = 'PROFILE_UPDATED'
    EVENT_EMAIL_CHANGED = 'EMAIL_CHANGED'
    EVENT_SESSION_INVALIDATED = 'SESSION_INVALIDATED'
    EVENT_TOKEN_REFRESHED = 'TOKEN_REFRESHED'
    EVENT_API_KEY_CREATED = 'API_KEY_CREATED'
    EVENT_API_KEY_REVOKED = 'API_KEY_REVOKED'
    EVENT_ADMIN_ACTION = 'ADMIN_ACTION'
    EVENT_DATA_EXPORT = 'DATA_EXPORT'
    EVENT_DATA_IMPORT = 'DATA_IMPORT'
    EVENT_RATE_LIMITED = 'RATE_LIMITED'
    
    _instance = None
    _logger = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def init_app(cls, app):
        """Initialize the security audit logger with the Flask app."""
        # Create logs directory
        log_dir = os.path.join(app.config.get('VOLUMES_PATH', '/app/volumes'), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        
        log_file = os.path.join(log_dir, 'security_audit.log')
        
        # Create dedicated logger
        cls._logger = logging.getLogger('security_audit')
        cls._logger.setLevel(logging.INFO)
        cls._logger.propagate = False  # Don't bubble up to root logger
        
        # Remove any existing handlers
        cls._logger.handlers = []
        
        # File handler with rotation
        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=10,  # Keep 10 rotated files
            encoding='utf-8'
        )
        file_handler.setLevel(logging.INFO)
        
        # Use a simple formatter - we'll do JSON in the log method
        formatter = logging.Formatter('%(message)s')
        file_handler.setFormatter(formatter)
        
        cls._logger.addHandler(file_handler)
        
        # Also log to console in development
        if app.config.get('DEBUG'):
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(formatter)
            cls._logger.addHandler(console_handler)
        
        app.logger.info(f"Security audit logging initialized: {log_file}")
    
    @classmethod
    def log(cls, 
            event_type: str,
            user_id: Optional[int] = None,
            user_email: Optional[str] = None,
            success: bool = True,
            details: Optional[Dict[str, Any]] = None,
            severity: str = 'INFO'):
        """
        Log a security audit event.
        
        Args:
            event_type: Type of security event (use EVENT_* constants)
            user_id: ID of the user involved (if applicable)
            user_email: Email of the user (for login attempts before ID is known)
            success: Whether the action was successful
            details: Additional event-specific details
            severity: Log severity (INFO, WARNING, ERROR, CRITICAL)
        """
        if cls._logger is None:
            # Fallback to current_app logger if not initialized
            if has_request_context():
                current_app.logger.warning(f"Security audit logger not initialized, event: {event_type}")
            return
        
        # Build the audit record
        record = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'event_type': event_type,
            'success': success,
            'severity': severity,
        }
        
        # Add user information
        if user_id is not None:
            record['user_id'] = user_id
        if user_email is not None:
            record['user_email'] = user_email
        
        # Add request context if available
        if has_request_context():
            record['ip'] = cls._get_client_ip()
            record['user_agent'] = request.headers.get('User-Agent', 'Unknown')[:200]
            record['endpoint'] = request.endpoint
            record['method'] = request.method
        
        # Add extra details
        if details:
            record['details'] = details
        
        # Log the event
        log_message = json.dumps(record, default=str)
        
        if severity == 'CRITICAL':
            cls._logger.critical(log_message)
        elif severity == 'ERROR':
            cls._logger.error(log_message)
        elif severity == 'WARNING':
            cls._logger.warning(log_message)
        else:
            cls._logger.info(log_message)
    
    @staticmethod
    def _get_client_ip() -> str:
        """Get the real client IP, accounting for proxies."""
        if request.headers.get('X-Forwarded-For'):
            return request.headers.get('X-Forwarded-For').split(',')[0].strip()
        return request.remote_addr or 'Unknown'
    
    # Convenience methods for common events
    @classmethod
    def login_success(cls, user_id: int, user_email: str, is_new_device: bool = False,
                      location: Optional[str] = None):
        """Log a successful login."""
        details = {}
        if is_new_device:
            details['new_device'] = True
        if location:
            details['location'] = location
        
        cls.log(
            cls.EVENT_LOGIN_SUCCESS,
            user_id=user_id,
            user_email=user_email,
            details=details if details else None
        )
        
        if is_new_device:
            cls.log(
                cls.EVENT_LOGIN_NEW_DEVICE,
                user_id=user_id,
                user_email=user_email,
                details={'location': location} if location else None,
                severity='WARNING'
            )
    
    @classmethod
    def login_failed(cls, user_email: str, reason: str = 'Invalid credentials',
                     attempt_count: Optional[int] = None):
        """Log a failed login attempt."""
        details = {'reason': reason}
        if attempt_count is not None:
            details['attempt_count'] = attempt_count
        
        cls.log(
            cls.EVENT_LOGIN_FAILED,
            user_email=user_email,
            success=False,
            details=details,
            severity='WARNING'
        )
    
    @classmethod
    def login_locked(cls, user_email: str, lockout_minutes: int):
        """Log an account lockout."""
        cls.log(
            cls.EVENT_LOGIN_LOCKED,
            user_email=user_email,
            success=False,
            details={'lockout_minutes': lockout_minutes},
            severity='ERROR'
        )
    
    @classmethod
    def suspicious_location(cls, user_id: int, user_email: str,
                            previous_country: str, current_country: str):
        """Log a login from a suspicious location."""
        cls.log(
            cls.EVENT_LOGIN_SUSPICIOUS_LOCATION,
            user_id=user_id,
            user_email=user_email,
            details={
                'previous_country': previous_country,
                'current_country': current_country
            },
            severity='WARNING'
        )
    
    @classmethod
    def password_change(cls, user_id: int, user_email: str, success: bool = True):
        """Log a password change."""
        cls.log(
            cls.EVENT_PASSWORD_CHANGE,
            user_id=user_id,
            user_email=user_email,
            success=success,
            severity='WARNING' if success else 'ERROR'
        )
    
    @classmethod
    def two_factor_change(cls, user_id: int, user_email: str, enabled: bool):
        """Log a 2FA enable/disable."""
        event_type = cls.EVENT_2FA_ENABLED if enabled else cls.EVENT_2FA_DISABLED
        cls.log(
            event_type,
            user_id=user_id,
            user_email=user_email,
            severity='WARNING'
        )
    
    @classmethod
    def two_factor_failed(cls, user_id: int, user_email: str):
        """Log a failed 2FA verification."""
        cls.log(
            cls.EVENT_2FA_FAILED,
            user_id=user_id,
            user_email=user_email,
            success=False,
            severity='WARNING'
        )
    
    @classmethod
    def account_created(cls, user_id: int, user_email: str):
        """Log a new account creation."""
        cls.log(
            cls.EVENT_ACCOUNT_CREATED,
            user_id=user_id,
            user_email=user_email
        )
    
    @classmethod
    def account_deleted(cls, user_id: int, user_email: str):
        """Log an account deletion."""
        cls.log(
            cls.EVENT_ACCOUNT_DELETED,
            user_id=user_id,
            user_email=user_email,
            severity='WARNING'
        )
    
    @classmethod
    def logout(cls, user_id: int, user_email: str, all_sessions: bool = False):
        """Log a logout."""
        cls.log(
            cls.EVENT_LOGOUT,
            user_id=user_id,
            user_email=user_email,
            details={'all_sessions': all_sessions} if all_sessions else None
        )
    
    @classmethod
    def session_invalidated(cls, user_id: int, user_email: str, session_count: int):
        """Log session invalidation."""
        cls.log(
            cls.EVENT_SESSION_INVALIDATED,
            user_id=user_id,
            user_email=user_email,
            details={'sessions_invalidated': session_count},
            severity='WARNING'
        )
    
    @classmethod
    def data_export(cls, user_id: int, user_email: str, export_type: str):
        """Log a data export."""
        cls.log(
            cls.EVENT_DATA_EXPORT,
            user_id=user_id,
            user_email=user_email,
            details={'export_type': export_type}
        )
    
    @classmethod
    def data_import(cls, user_id: int, user_email: str, import_type: str, success: bool = True):
        """Log a data import."""
        cls.log(
            cls.EVENT_DATA_IMPORT,
            user_id=user_id,
            user_email=user_email,
            success=success,
            details={'import_type': import_type},
            severity='INFO' if success else 'ERROR'
        )
    
    @classmethod
    def rate_limited(cls, endpoint: str, user_id: Optional[int] = None):
        """Log a rate limit hit."""
        cls.log(
            cls.EVENT_RATE_LIMITED,
            user_id=user_id,
            success=False,
            details={'endpoint': endpoint},
            severity='WARNING'
        )


# Global instance for easy access
security_audit = SecurityAuditLogger()

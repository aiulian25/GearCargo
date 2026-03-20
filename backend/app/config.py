"""
GearCargo - Application Configuration
"""

import os
from datetime import timedelta


class Config:
    """Base configuration."""
    
    # App info
    APP_NAME = os.environ.get('APP_NAME', 'GearCargo')
    APP_URL = os.environ.get('APP_URL', 'http://localhost:5000')
    ADMIN_DOMAIN = os.environ.get('ADMIN_DOMAIN', '').strip().lower()
    USER_DOMAIN = os.environ.get('USER_DOMAIN', '').strip().lower()
    
    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    DEBUG = os.environ.get('DEBUG', 'false').lower() == 'true'
    
    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        'postgresql://gearcargo:password@localhost:5432/gearcargo'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }
    
    # Redis
    REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    
    # JWT Authentication
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'jwt-secret-change-in-production')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(seconds=int(os.environ.get('JWT_ACCESS_TOKEN_EXPIRES', 3600)))
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(seconds=int(os.environ.get('JWT_REFRESH_TOKEN_EXPIRES', 2592000)))
    JWT_TOKEN_LOCATION = ['headers', 'cookies']
    JWT_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'false').lower() == 'true'
    JWT_COOKIE_SAMESITE = os.environ.get('SESSION_COOKIE_SAMESITE', 'Lax')
    JWT_COOKIE_HTTPONLY = True
    JWT_COOKIE_CSRF_PROTECT = True
    
    # Session
    SESSION_TYPE = 'redis'
    SESSION_PERMANENT = True
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    SESSION_USE_SIGNER = True
    SESSION_KEY_PREFIX = 'gearcargo:'
    SESSION_REDIS = None  # Set in __init__ based on REDIS_URL
    SESSION_COOKIE_HTTPONLY = os.environ.get('SESSION_COOKIE_HTTPONLY', 'true').lower() == 'true'
    SESSION_COOKIE_SAMESITE = os.environ.get('SESSION_COOKIE_SAMESITE', 'Lax')
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'false').lower() == 'true'
    
    # CORS - Security
    CORS_ORIGINS = [origin.strip() for origin in os.environ.get('CORS_ORIGINS', 'http://localhost:5000').split(',')]
    CORS_SUPPORTS_CREDENTIALS = os.environ.get('CORS_SUPPORTS_CREDENTIALS', 'true').lower() == 'true'
    CORS_ALLOW_HEADERS = ['Content-Type', 'Authorization', 'X-CSRF-Token', 'X-Requested-With']
    CORS_EXPOSE_HEADERS = ['Content-Type', 'X-CSRF-Token']
    CORS_MAX_AGE = 600
    
    # CSRF Protection
    WTF_CSRF_ENABLED = os.environ.get('WTF_CSRF_ENABLED', 'true').lower() == 'true'
    WTF_CSRF_SECRET_KEY = os.environ.get('WTF_CSRF_SECRET_KEY', 'csrf-secret-change-in-production')
    WTF_CSRF_TIME_LIMIT = 3600
    WTF_CSRF_SSL_STRICT = os.environ.get('SESSION_COOKIE_SECURE', 'false').lower() == 'true'
    
    # Encryption for sensitive data at rest
    ENCRYPTION_KEY = os.environ.get('ENCRYPTION_KEY', '')
    
    # Theme
    DEFAULT_THEME = os.environ.get('DEFAULT_THEME', 'dark')
    
    # Email
    MAIL_ENABLED = os.environ.get('MAIL_ENABLED', 'false').lower() == 'true'
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'false').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@gearcargo.local')
    
    # Push Notifications (VAPID)
    VAPID_PUBLIC_KEY = os.environ.get('VAPID_PUBLIC_KEY', '')
    VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY', '')
    VAPID_SUBJECT = os.environ.get('VAPID_SUBJECT', 'mailto:admin@gearcargo.local')
    
    # Ollama (External Instance)
    OLLAMA_ENABLED = os.environ.get('OLLAMA_ENABLED', 'true').lower() == 'true'
    OLLAMA_BASE_URL = os.environ.get('OLLAMA_BASE_URL', 'http://host.docker.internal:11434')
    OLLAMA_URL = OLLAMA_BASE_URL  # Alias for backwards compatibility
    OLLAMA_MODEL = os.environ.get('OLLAMA_MODEL', 'llama3.2')
    OLLAMA_TIMEOUT = int(os.environ.get('OLLAMA_TIMEOUT', 30))
    
    # File uploads
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100 MB
    UPLOAD_FOLDER = '/app/volumes/attachments'
    BACKUP_FOLDER = '/app/volumes/backups'
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf', 'bmp', 'tiff'}
    
    # Rate limiting
    RATELIMIT_ENABLED = os.environ.get('RATELIMIT_ENABLED', 'true').lower() == 'true'
    RATELIMIT_STORAGE_URL = os.environ.get('RATELIMIT_STORAGE_URL', os.environ.get('REDIS_URL', 'memory://'))
    RATELIMIT_DEFAULT = os.environ.get('RATELIMIT_DEFAULT', '200 per day')
    RATELIMIT_HEADERS_ENABLED = True
    RATELIMIT_STRATEGY = 'fixed-window'  # Valid strategies: fixed-window, moving-window
    
    # Security Headers (handled by Talisman)
    CONTENT_SECURITY_POLICY = {
        'default-src': "'self'",
        'script-src': "'self' 'unsafe-inline'",
        'style-src': "'self' 'unsafe-inline' https://fonts.googleapis.com",
        'font-src': "'self' https://fonts.gstatic.com",
        'img-src': "'self' data: blob:",
        'connect-src': "'self'",
    }
    
    # Internationalization
    BABEL_DEFAULT_LOCALE = 'en-US'
    BABEL_DEFAULT_TIMEZONE = 'UTC'
    LANGUAGES = {
        'en-US': 'English (US)',
        'en-GB': 'English (UK)',
        'ro': 'Română',
        'es': 'Español',
    }
    
    # Branding
    LOGO_PATH = '/icons/logo.png'
    FAVICON_PATH = '/favicon.ico'


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    SESSION_COOKIE_SECURE = False
    JWT_COOKIE_SECURE = False
    WTF_CSRF_SSL_STRICT = False


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    JWT_COOKIE_SECURE = True
    WTF_CSRF_SSL_STRICT = True
    RATELIMIT_DEFAULT = "100 per hour"


class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False


# Config selector
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}

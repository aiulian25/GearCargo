"""
GearCargo - Flask Application Factory
Vehicle Management PWA Backend
"""

import os
from flask import Flask, send_from_directory, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_mail import Mail
from flask_session import Session
from flask_talisman import Talisman
from flask_compress import Compress
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_cors import CORS
from flask_wtf.csrf import CSRFProtect
import redis

# Initialize extensions
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
bcrypt = Bcrypt()
mail = Mail()
sess = Session()
compress = Compress()
csrf = CSRFProtect()
redis_client = None

def create_app(config_class=None):
    """Application factory pattern."""
    global redis_client
    
    # Static folder is at /app/static (where Vite output is copied)
    static_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static')
    
    app = Flask(__name__, 
                static_folder=static_path, 
                static_url_path='')
    
    # Load configuration
    app.config.from_object(config_class or 'app.config.Config')
    
    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    bcrypt.init_app(app)
    mail.init_app(app)
    
    # Initialize CSRF protection
    # Note: API routes use JWT authentication which is inherently CSRF-safe
    # JWT tokens in Authorization header are not automatically sent by browsers
    # Blueprints are exempted in routes/__init__.py
    if app.config.get('WTF_CSRF_ENABLED', True):
        csrf.init_app(app)
        
        @app.route('/api/csrf-token', methods=['GET'])
        def get_csrf_token():
            """Get CSRF token for frontend (if needed for non-JWT endpoints)."""
            from flask_wtf.csrf import generate_csrf
            token = generate_csrf()
            response = jsonify({'csrf_token': token})
            return response
    
    # Configure session with Redis before initializing
    try:
        redis_url = app.config.get('REDIS_URL', 'redis://localhost:6379/0')
        if redis_url and 'redis://' in redis_url:
            app.config['SESSION_REDIS'] = redis.from_url(redis_url)
    except Exception as e:
        app.logger.warning(f"Redis session setup failed: {e}. Using filesystem sessions.")
        app.config['SESSION_TYPE'] = 'filesystem'
    
    sess.init_app(app)
    compress.init_app(app)
    
    # CORS configuration - Security
    CORS(app, resources={
        r"/api/*": {
            "origins": app.config.get('CORS_ORIGINS', ['http://localhost:5000']),
            "supports_credentials": app.config.get('CORS_SUPPORTS_CREDENTIALS', True),
            "allow_headers": app.config.get('CORS_ALLOW_HEADERS', ['Content-Type', 'Authorization', 'X-CSRF-Token']),
            "expose_headers": app.config.get('CORS_EXPOSE_HEADERS', ['Content-Type', 'X-CSRF-Token']),
            "max_age": app.config.get('CORS_MAX_AGE', 600)
        }
    })
    
    # Rate limiting
    limiter = Limiter(
        key_func=get_remote_address,
        app=app,
        default_limits=[app.config.get('RATELIMIT_DEFAULT', '200 per day')],
        storage_uri=app.config.get('RATELIMIT_STORAGE_URL', app.config.get('REDIS_URL', 'memory://')),
        enabled=app.config.get('RATELIMIT_ENABLED', True)
    )
    
    # Initialize Redis client for token blacklisting
    global redis_client
    try:
        redis_url = app.config.get('REDIS_URL')
        if redis_url and redis_url != 'memory://':
            redis_client = redis.from_url(redis_url)
            redis_client.ping()  # Test connection
            app.logger.info(f"Redis connection successful!")
    except Exception as e:
        app.logger.warning(f"Redis connection failed: {e}. Token blacklisting disabled.")
        redis_client = None
    
    # Initialize security audit logging
    from app.utils.security_audit import SecurityAuditLogger
    SecurityAuditLogger.init_app(app)
    
    # Security headers (CSP, HSTS, etc.)
    if not app.config.get('DEBUG'):
        # Content Security Policy - Restrictive but compatible with React SPA
        # Note: 'unsafe-inline' for styles is needed for CSS-in-JS and Tailwind
        # 'unsafe-eval' removed where possible (may need if using certain libs)
        csp = {
            'default-src': "'self'",
            'script-src': ["'self'", "'unsafe-inline'"],  # Removed unsafe-eval
            'style-src': ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com"],
            'font-src': ["'self'", "https://fonts.gstatic.com", "data:"],
            'img-src': ["'self'", "data:", "blob:", "https:"],
            'connect-src': [
                "'self'", 
                "https://api.open-meteo.com", 
                "https://vpic.nhtsa.dot.gov", 
                "https://nominatim.openstreetmap.org", 
                "https://air-quality-api.open-meteo.com",
                "https://api.pwnedpasswords.com",  # For HIBP password checking
                "https://fonts.googleapis.com", 
                "https://fonts.gstatic.com"
            ],
            'manifest-src': "'self'",
            'worker-src': ["'self'", "blob:"],  # Service worker
            # Additional security directives
            'object-src': ["'none'"],  # Block Flash/plugins
            'base-uri': ["'self'"],  # Prevent base tag injection
            'form-action': ["'self'"],  # Prevent form hijacking
            'frame-ancestors': ["'self'"],  # Prevent clickjacking
        }
        
        Talisman(
            app,
            force_https=False,  # Handle at reverse proxy
            strict_transport_security=True,
            strict_transport_security_max_age=31536000,
            strict_transport_security_include_subdomains=True,
            strict_transport_security_preload=True,
            content_security_policy=csp,
            content_security_policy_report_only=False,
            referrer_policy='strict-origin-when-cross-origin',
            feature_policy={
                'geolocation': "'self'",
                'camera': "'self'",
                'microphone': "'none'",
                'payment': "'none'",
                'usb': "'none'",
            },
            x_content_type_options=True,
            x_xss_protection=True,
        )
    
    # Register blueprints
    from app.routes import register_blueprints
    register_blueprints(app)
    
    # Exempt widget API from rate limiting (uses API key auth, polled frequently by Gethomepage)
    from app.routes.widget import widget_bp
    limiter.exempt(widget_bp)
    
    # Strip security headers from widget API responses using WSGI middleware
    # (runs after all Flask after_request handlers including Talisman)
    _strip_headers = [
        'Content-Security-Policy', 'X-Frame-Options', 'X-XSS-Protection',
        'X-Content-Type-Options', 'Referrer-Policy', 'Feature-Policy',
        'Permissions-Policy', 'Strict-Transport-Security',
    ]
    _original_wsgi = app.wsgi_app
    
    class WidgetHeaderMiddleware:
        def __init__(self, wsgi):
            self.wsgi = wsgi
        def __call__(self, environ, start_response):
            path = environ.get('PATH_INFO', '')
            if path.startswith('/api/widget/v1/'):
                def custom_start_response(status, headers, exc_info=None):
                    headers = [(k, v) for k, v in headers
                               if k not in _strip_headers and k != 'Access-Control-Allow-Origin']
                    headers.append(('Access-Control-Allow-Origin', '*'))
                    headers.append(('Access-Control-Allow-Headers', 'X-API-Key, Content-Type'))
                    headers.append(('Access-Control-Allow-Methods', 'GET, OPTIONS'))
                    return start_response(status, headers, exc_info)
                return self.wsgi(environ, custom_start_response)
            return self.wsgi(environ, start_response)
    
    app.wsgi_app = WidgetHeaderMiddleware(_original_wsgi)
    
    # ================================================================
    # STATIC FILE SERVING (React SPA)
    # ================================================================
    
    @app.route('/health')
    @limiter.exempt
    def health_check():
        """Health check endpoint for Docker/monitoring."""
        return jsonify({
            'status': 'healthy',
            'app': 'GearCargo',
            'version': '1.0.0'
        }), 200
    
    @app.route('/uploads/<path:filename>')
    @limiter.exempt
    def serve_uploads(filename):
        """Serve uploaded files with signed URL verification."""
        from app.utils import verify_upload_signature

        sig = request.args.get('sig', '')
        exp = request.args.get('exp', '')
        original_path = f'/uploads/{filename}'

        if not verify_upload_signature(original_path, exp, sig):
            return jsonify({'error': 'Forbidden'}), 403

        uploads_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads')
        full_path = os.path.join(uploads_path, filename)
        if not os.path.isfile(full_path):
            return jsonify({'error': 'File not found'}), 404
        return send_from_directory(uploads_path, filename)
    
    @app.route('/sw.js')
    @limiter.exempt
    def service_worker():
        """Serve service worker with correct headers."""
        response = send_from_directory(app.static_folder, 'sw.js')
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Service-Worker-Allowed'] = '/'
        return response
    
    @app.route('/manifest.json')
    @limiter.exempt
    def manifest():
        """Serve PWA manifest."""
        response = send_from_directory(app.static_folder, 'manifest.json')
        response.headers['Cache-Control'] = 'public, max-age=3600'
        return response
    
    @app.route('/favicon.ico')
    @limiter.exempt
    def favicon():
        """Serve favicon."""
        return send_from_directory(app.static_folder, 'favicon.ico')
    
    @app.route('/logo.png')
    @limiter.exempt
    def logo():
        """Serve app logo."""
        return send_from_directory(os.path.join(app.static_folder, 'icons'), 'logo.png')
    
    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    @limiter.exempt
    def serve_spa(path):
        """Serve React SPA - all routes fallback to index.html."""
        if path and os.path.exists(os.path.join(app.static_folder, path)):
            return send_from_directory(app.static_folder, path)
        return send_from_directory(app.static_folder, 'index.html')
    
    # Error handlers
    @app.errorhandler(404)
    def not_found(e):
        """Return JSON for API routes, SPA for others."""
        if '/api/' in str(e):
            return jsonify({'error': 'Not found'}), 404
        return send_from_directory(app.static_folder, 'index.html')
    
    @app.errorhandler(500)
    def server_error(e):
        return jsonify({'error': 'Internal server error'}), 500
    
    @app.errorhandler(429)
    def ratelimit_handler(e):
        return jsonify({'error': 'Rate limit exceeded', 'message': str(e.description)}), 429
    
    # Initialize scheduler for background tasks
    if not app.config.get('TESTING'):
        from app.services import init_scheduler
        init_scheduler(app)
    
    # Initialize default admin from environment variables
    with app.app_context():
        init_default_admin(app)
    
    return app


def init_default_admin(app):
    """Create default admin user from environment variables on first startup.
    
    This only creates an admin if:
    - ADMIN_EMAIL and ADMIN_PASSWORD are set
    - No users exist in the database yet
    
    The admin user is created with must_change_password=True for security.
    """
    admin_email = os.environ.get('ADMIN_EMAIL', '').strip()
    admin_password = os.environ.get('ADMIN_PASSWORD', '').strip()
    admin_username = os.environ.get('ADMIN_USERNAME', 'admin').strip()
    
    if not admin_email or not admin_password:
        return  # No default admin configured
    
    try:
        from app.models import User
        
        # Only create if no users exist
        if User.query.count() > 0:
            return
        
        # Check minimum password length
        if len(admin_password) < 8:
            app.logger.warning('ADMIN_PASSWORD must be at least 8 characters. Skipping default admin creation.')
            return
        
        # Create the default admin
        admin = User(
            email=admin_email,
            username=admin_username,
            is_admin=True,
            must_change_password=True,
            calendar_enabled=True  # Enable calendar sync by default
        )
        admin.set_password(admin_password)
        
        db.session.add(admin)
        db.session.commit()
        
        app.logger.info(f'Default admin user created: {admin_email}')
        app.logger.warning('IMPORTANT: Change the admin password immediately and remove ADMIN_PASSWORD from environment!')
        
        # Send email verification if email is enabled
        if app.config.get('MAIL_ENABLED'):
            try:
                from app.services.email_service import EmailVerificationService
                email_verification_service = EmailVerificationService()
                token = admin.generate_verification_token()
                email_verification_service.send_verification_email(admin, token)
                app.logger.info(f'Verification email sent to admin: {admin_email}')
            except Exception as email_error:
                app.logger.warning(f'Could not send verification email to admin: {email_error}')
        
    except Exception as e:
        app.logger.error(f'Failed to create default admin: {e}')
        db.session.rollback()

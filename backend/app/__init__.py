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
# I15: tracks whether Redis is reachable — checked at startup and exposed in /health.
# False means rate-limiting runs in-memory (no cross-worker coordination) and token
# blacklisting is disabled. The app stays up (fail-open) but ops should be alerted.
_redis_available = False

def create_app(config_class=None):
    """Application factory pattern."""
    global redis_client, _redis_available
    
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
    
    # Validate critical secrets are not defaults in production
    _insecure_defaults = {
        'dev-secret-key-change-in-production',
        'jwt-secret-change-in-production',
        'csrf-secret-change-in-production',
    }
    if not app.config.get('DEBUG'):
        for key in ('SECRET_KEY', 'JWT_SECRET_KEY', 'WTF_CSRF_SECRET_KEY'):
            if app.config.get(key) in _insecure_defaults:
                raise RuntimeError(
                    f'{key} is using an insecure default value. '
                    f'Set {key} environment variable to a random secret.'
                )

        # I10: ENCRYPTION_KEY must be explicitly set in production.
        # If it is absent the field-level encryption helper falls back to
        # SECRET_KEY as the key seed, which (a) silently couples encryption
        # material to the session secret — rotating SECRET_KEY would make all
        # encrypted PII unreadable — and (b) gives a false sense of isolation.
        # We refuse to start so the operator is forced to set the key before
        # any user data is encrypted under a wrong/unknown key.
        enc_key = app.config.get('ENCRYPTION_KEY', '')
        if not enc_key:
            raise RuntimeError(
                'ENCRYPTION_KEY is not set. '
                'Generate a key with: python -c "import secrets; print(secrets.token_hex(32))" '
                'and set it as the ENCRYPTION_KEY environment variable.'
            )
    
    # Rate limiting
    limiter = Limiter(
        key_func=get_remote_address,
        app=app,
        default_limits=[app.config.get('RATELIMIT_DEFAULT', '200 per day')],
        storage_uri=app.config.get('RATELIMIT_STORAGE_URL', app.config.get('REDIS_URL', 'memory://')),
        enabled=app.config.get('RATELIMIT_ENABLED', True)
    )
    
    # I15: Initialize Redis client for token blacklisting and check connectivity.
    # The result is stored in _redis_available so the /health endpoint can report
    # degraded status to orchestrators / monitoring tools.
    global redis_client, _redis_available
    try:
        redis_url = app.config.get('REDIS_URL')
        if redis_url and redis_url != 'memory://':
            redis_client = redis.from_url(redis_url)
            redis_client.ping()  # Test connection
            _redis_available = True
            app.logger.info('Redis connection successful')
        else:
            _redis_available = False
            app.logger.warning(
                'I15: REDIS_URL not set or is memory://. '
                'Rate limiting is in-memory only (no cross-worker coordination). '
                'Token blacklisting is disabled.'
            )
    except Exception as e:
        _redis_available = False
        redis_client = None
        if not app.config.get('DEBUG'):
            app.logger.warning(
                f'I15: Redis connection failed: {e}. '
                'Rate limiting will degrade to in-memory (per-worker) mode. '
                'Token blacklisting is disabled. '
                'Check REDIS_URL and that the Redis service is healthy.'
            )
        else:
            app.logger.debug(f'Redis unavailable (dev mode): {e}')
    
    # Initialize security audit logging
    from app.utils.security_audit import SecurityAuditLogger
    SecurityAuditLogger.init_app(app)

    # S10: Initialize local GeoIP2 reader (replaces external ip-api.com HTTP call).
    # The reader is opened once at startup and shared across all requests via the
    # app object (thread-safe reads). When GEOIP_DB_PATH is not set the feature is
    # silently disabled — login still works, suspicious-location emails are not sent.
    geoip_db_path = app.config.get('GEOIP_DB_PATH', '')
    if geoip_db_path and os.path.isfile(geoip_db_path):
        try:
            import geoip2.database
            app.geoip_reader = geoip2.database.Reader(geoip_db_path)
            app.logger.info(f'S10: GeoIP2 database loaded from {geoip_db_path}')
        except Exception as _geo_err:
            app.geoip_reader = None
            app.logger.warning(f'S10: Failed to open GeoIP2 database ({geoip_db_path}): {_geo_err}')
    else:
        app.geoip_reader = None
        if geoip_db_path:
            app.logger.warning(
                f'S10: GEOIP_DB_PATH is set to "{geoip_db_path}" but the file was not found. '
                'Suspicious-login country detection is disabled.'
            )
        else:
            app.logger.info(
                'S10: GEOIP_DB_PATH not set — suspicious-login country detection disabled. '
                'Set GEOIP_DB_PATH to the path of a MaxMind GeoLite2-City MMDB file to enable it. '
                'Download free: https://dev.maxmind.com/geoip/geolite2-free-geolocation-data'
            )
    
    # Security headers (CSP, HSTS, etc.)
    # S19: Talisman is now initialised unconditionally — DEBUG no longer disables
    # security headers entirely. In DEBUG mode we make two targeted relaxations:
    #   1. CSP is applied in report-only mode so violations appear in the browser
    #      console (devs can discover regressions) without breaking the dev workflow.
    #   2. CSP directives are widened to allow Vite HMR websockets (ws:/wss:),
    #      unsafe-inline/eval in script-src, and http: assets on localhost.
    #   3. HSTS is disabled in DEBUG — pinning HTTPS on localhost for a year would
    #      make the browser refuse HTTP connections and break local dev permanently.
    # All other headers (X-Frame-Options, X-Content-Type-Options, X-XSS-Protection,
    # Referrer-Policy, Feature-Policy) are always enforced in both modes.
    _is_debug = app.config.get('DEBUG', False)

    # Content Security Policy — Restrictive and compatible with the React/Vite SPA.
    # I04: 'unsafe-inline' removed from script-src — the Vite build produces no
    #      inline scripts. The only inline script is the I13 FOUC-prevention
    #      theme loader in index.html; its exact SHA-256 hash is allowlisted below
    #      so 'unsafe-inline' is not needed.
    # I05: frame-ancestors set to 'none' and X-Frame-Options set to DENY to
    #      prevent clickjacking across all browsers.
    #
    # I13: SHA-256 of the inline theme-loader script in frontend/index.html:
    #   (function(){var t=localStorage.getItem('theme');if(t==='light'||
    #   (!t&&window.matchMedia('(prefers-color-scheme: light)').matches)){
    #   document.documentElement.classList.add('light')}})()
    # If that script is ever changed, recompute with:
    #   python3 -c "import hashlib,base64; print('sha256-'+base64.b64encode(
    #     hashlib.sha256(open('frontend/index.html').read().split('<script>')[1]
    #     .split('</script>')[0].encode()).digest()).decode())"
    _FOUC_SCRIPT_HASH = "'sha256-5KS/AlEMDSJ/zkwZPRboc7IYkKJj144Vs8I/Mw2e2LY='"

    if _is_debug:
        # S19: DEBUG CSP — widened to allow Vite HMR (websockets, unsafe-eval, http:
        # assets on localhost). Applied in report-only mode so violations surface in
        # the browser console without breaking the dev workflow.
        csp = {
            'default-src': "'self'",
            'script-src': ["'self'", "'unsafe-inline'", "'unsafe-eval'"],
            'style-src': ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com"],
            'font-src': ["'self'", "https://fonts.gstatic.com", "data:"],
            'img-src': ["'self'", "data:", "blob:", "https:", "http:"],
            'connect-src': [
                "'self'", "ws:", "wss:", "http:", "https:",
                "https://api.open-meteo.com",
                "https://vpic.nhtsa.dot.gov",
                "https://nominatim.openstreetmap.org",
                "https://air-quality-api.open-meteo.com",
                "https://api.pwnedpasswords.com",
                "https://fonts.googleapis.com",
                "https://fonts.gstatic.com",
            ],
            'manifest-src': "'self'",
            'worker-src': ["'self'", "blob:"],
            'object-src': ["'none'"],
            'base-uri': ["'self'"],
            'form-action': ["'self'"],
            'frame-ancestors': "'none'",
            'report-uri': '/api/csp-report',  # S27: receive CSP violation reports in DEBUG too
        }
    else:
        # 'unsafe-inline' is required in style-src: third-party JS libraries
        # (recharts, react-hot-toast, react-spring, etc.) inject inline styles via
        # element.style and CSSStyleSheet.insertRule() — both of which ARE gated by
        # style-src in Chrome/Firefox despite being CSSOM calls (not HTML-parser paths).
        csp = {
            'default-src': "'self'",
            'script-src': ["'self'", _FOUC_SCRIPT_HASH],  # Hash allowlists the I13 theme-loader inline script
            'style-src': ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com"],
            'font-src': ["'self'", "https://fonts.gstatic.com", "data:"],
            'img-src': ["'self'", "data:", "blob:", "https:"],
            'connect-src': [
                "'self'",
                "https://api.open-meteo.com",
                "https://vpic.nhtsa.dot.gov",
                "https://nominatim.openstreetmap.org",
                "https://air-quality-api.open-meteo.com",
                "https://api.pwnedpasswords.com",  # HIBP password breach check
                "https://fonts.googleapis.com",
                "https://fonts.gstatic.com"
            ],
            'manifest-src': "'self'",
            'worker-src': ["'self'", "blob:"],  # Service worker + Workbox
            'object-src': ["'none'"],          # Block plugins/Flash
            'base-uri': ["'self'"],             # Prevent base-tag injection
            'form-action': ["'self'"],          # Prevent form hijacking
            'frame-ancestors': "'none'",        # I05: deny all framing (clickjacking)
            'report-uri': '/api/csp-report',  # S27: browser posts violations here for operator visibility
        }

    Talisman(
        app,
        force_https=False,  # Handle at reverse proxy
        # S19: HSTS disabled in DEBUG — pinning HTTPS on localhost for a year would
        # break HTTP-only dev servers permanently. Enabled unconditionally in production.
        strict_transport_security=not _is_debug,
        strict_transport_security_max_age=31536000,
        strict_transport_security_include_subdomains=True,
        strict_transport_security_preload=True,
        content_security_policy=csp,
        # S19: Report-only in DEBUG so CSP violations appear in the browser console
        # without blocking page load. Enforced (report_only=False) in production.
        content_security_policy_report_only=_is_debug,
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
        frame_options='DENY',  # I05: legacy browser clickjacking protection
    )

    # Register blueprints
    from app.routes import register_blueprints
    register_blueprints(app)

    # I11: Apply a tight per-IP rate limit specifically to registration.
    # The global default (200/day) is too permissive — an attacker could create
    # thousands of accounts to exhaust vehicle_limit quotas or flood the DB.
    # Applied post-registration so auth.register exists in app.view_functions.
    # Flask-Limiter's before_request hook enforces this limit before the view
    # function runs; Redis unavailability is handled internally (fail-open + log).
    app.view_functions['auth.register'] = limiter.limit(
        '5 per hour; 20 per day',
        error_message='Too many registration attempts. Please try again later.',
    )(app.view_functions['auth.register'])

    # S16: Apply a dedicated per-IP rate limit to the security-question lookup
    # endpoint. The global default (100/hour) is far too permissive — an attacker
    # can enumerate thousands of email addresses to discover which accounts have
    # security questions configured, a prerequisite for the password-recovery
    # attack chain. 20 requests/hour is more than enough for any legitimate user
    # (a single recovery flow needs 1-2 requests) while making bulk enumeration
    # impractical. Applied after blueprint registration so the view function exists.
    app.view_functions['auth.get_recovery_questions'] = limiter.limit(
        '20 per hour',
        error_message='Too many requests. Please try again later.',
    )(app.view_functions['auth.get_recovery_questions'])

    # S23: Apply a dedicated per-IP rate limit to the public password-check
    # endpoint.  Without this only the global 100/hour default applies, letting
    # unauthenticated callers use the server as a high-volume HIBP API proxy or
    # test common passwords at scale.  30 per hour is generous for genuine use
    # (password-strength feedback during registration fires once per final
    # submission, not on every keystroke) while making bulk API abuse impractical.
    app.view_functions['auth.check_password_public'] = limiter.limit(
        '30 per hour',
        error_message='Too many requests. Please try again later.',
    )(app.view_functions['auth.check_password_public'])

    from app.routes.widget import widget_bp
    limiter.exempt(widget_bp)
    
    # S22: Widget WSGI middleware — only strip headers that genuinely conflict
    # with cross-origin widget embedding.  All other security headers (HSTS,
    # X-Content-Type-Options, Referrer-Policy, Permissions-Policy, etc.) are
    # preserved because they do NOT interfere with Gethomepage / iframe use.
    #
    # Headers removed and why:
    #   Content-Security-Policy  — Talisman sets frame-ancestors:'none' which
    #                              would block any iframe embedding of the widget.
    #   X-Frame-Options          — Talisman sets DENY; same iframe conflict.
    #
    # WIDGET_CORS_ORIGINS (env var, default '*') lets operators restrict which
    # origins may call the widget API.  Use '*' for Gethomepage (server-side
    # fetch) or a space-separated list of allowed origins for browser clients.
    # Widget endpoints use API-key auth (not cookies), so wildcard CORS does
    # NOT introduce CSRF risk — browsers never send cookies for cross-origin
    # requests that use wildcard ACAO.
    _widget_strip_headers = {'Content-Security-Policy', 'X-Frame-Options'}
    _widget_cors_origins = app.config.get('WIDGET_CORS_ORIGINS', '*')
    _original_wsgi = app.wsgi_app

    class WidgetHeaderMiddleware:
        def __init__(self, wsgi):
            self.wsgi = wsgi
        def __call__(self, environ, start_response):
            path = environ.get('PATH_INFO', '')
            if path.startswith('/api/widget/v1/'):
                def custom_start_response(status, headers, exc_info=None):
                    # Remove only embedding-conflicting headers and any
                    # pre-existing ACAO header (we set our own below).
                    headers = [
                        (k, v) for k, v in headers
                        if k not in _widget_strip_headers
                        and k != 'Access-Control-Allow-Origin'
                    ]
                    headers.append(('Access-Control-Allow-Origin', _widget_cors_origins))
                    headers.append(('Access-Control-Allow-Headers', 'X-API-Key, Content-Type'))
                    headers.append(('Access-Control-Allow-Methods', 'GET, OPTIONS'))
                    # Vary: Origin is required for cache-correctness whenever
                    # the allowed origin is not the wildcard '*'.
                    if _widget_cors_origins != '*':
                        headers.append(('Vary', 'Origin'))
                    return start_response(status, headers, exc_info)
                return self.wsgi(environ, custom_start_response)
            return self.wsgi(environ, start_response)
    
    app.wsgi_app = WidgetHeaderMiddleware(_original_wsgi)

    # S11: Apply werkzeug ProxyFix as the outermost WSGI middleware so that
    # request.remote_addr is always the real client IP by the time Flask (and
    # Flask-Limiter's get_remote_address) reads it.
    #
    # TRUSTED_PROXY_COUNT (default 1) tells ProxyFix how many hops to trust:
    #   0 → no proxy at all (dev / direct TCP bind)
    #   1 → one trusted reverse proxy in front (nginx, Traefik, Cloudflare…)
    #   2 → CDN + reverse proxy in front
    #
    # ProxyFix reads ONLY the rightmost N entries of X-Forwarded-For, so a
    # client cannot forge their IP by appending extra addresses to the left of
    # the header — the nth-from-right entry is always written by the Nth
    # trusted proxy and cannot be influenced by the client.
    from werkzeug.middleware.proxy_fix import ProxyFix
    _trusted = app.config.get('TRUSTED_PROXY_COUNT', 1)
    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=_trusted,    # honour X-Forwarded-For (sets remote_addr)
        x_proto=_trusted,  # honour X-Forwarded-Proto (sets request.scheme)
        x_host=_trusted,   # honour X-Forwarded-Host (sets request.host)
        x_prefix=_trusted, # honour X-Forwarded-Prefix (sets SCRIPT_NAME)
    )
    app.logger.info(
        f'S11: ProxyFix applied — trusting {_trusted} reverse-proxy hop(s). '
        'Adjust TRUSTED_PROXY_COUNT in .env if your topology differs.'
    )

    # ================================================================
    # STATIC FILE SERVING (React SPA)
    # ================================================================

    @app.route('/health')
    @limiter.exempt
    def health_check():
        """Health check endpoint for Docker/monitoring.

        I15: Reports Redis connectivity. When redis_ok is False the response
        body still indicates 'healthy' (so the container is not restarted) but
        the redis_ok flag lets external monitors distinguish between full health
        and a degraded state where rate limiting is per-worker only and token
        blacklisting is disabled.
        """
        from app import _redis_available
        return jsonify({
            'status': 'healthy',
            'app': 'GearCargo',
            'version': '1.0.0',
            'redis_ok': _redis_available,
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

    @app.route('/robots.txt')
    @limiter.exempt
    def robots_txt():
        """I19: Serve robots.txt with correct content-type and cache headers.
        Disallows all crawlers — GearCargo is a private PWA with no public pages.
        1-day cache: short enough that policy changes propagate within 24 h.
        """
        response = send_from_directory(app.static_folder, 'robots.txt',
                                       mimetype='text/plain')
        response.headers['Cache-Control'] = 'public, max-age=86400'
        return response

    @app.route('/api/csp-report', methods=['POST'])
    @limiter.limit('20 per minute')
    def csp_report():
        """S27: Receive Content-Security-Policy violation reports from browsers.

        Browsers POST a JSON body with Content-Type: application/csp-report
        whenever a resource load or inline script is blocked by CSP. This
        endpoint:
          - Accepts the report without authentication (browsers send it directly,
            not through user JS code — no auth cookie is available at this point).
          - Rate-limits to 20/min per IP to prevent DoS flooding.
          - Logs violations at WARNING level with structured fields so operators
            can distinguish XSS attempts from browser-extension noise.
          - Returns 204 No Content (the browser ignores the response body).
        """
        # Browsers send Content-Type: application/csp-report with a JSON body.
        # request.get_json() rejects non-application/json content-types by default,
        # so we read raw bytes and parse manually with force=True.
        try:
            data = request.get_json(force=True, silent=True) or {}
        except Exception:
            data = {}

        report = data.get('csp-report', data)  # Chrome wraps under 'csp-report' key

        blocked_uri        = report.get('blocked-uri', 'unknown')
        violated_directive = report.get('violated-directive', 'unknown')
        document_uri       = report.get('document-uri', 'unknown')
        source_file        = report.get('source-file', '')
        line_number        = report.get('line-number', '')
        column_number      = report.get('column-number', '')
        effective_directive = report.get('effective-directive', violated_directive)

        # Suppress noisy browser-extension injections (chrome-extension:, moz-extension:, etc.)
        # These are false positives that obscure real violation signals.
        if blocked_uri.startswith(('chrome-extension:', 'moz-extension:', 'safari-extension:', 'ms-browser-extension:')):
            return '', 204

        app.logger.warning(
            '[CSP] Violation reported | '
            f'blocked-uri={blocked_uri!r} | '
            f'directive={effective_directive!r} | '
            f'document={document_uri!r} | '
            f'source={source_file!r}:{line_number}:{column_number} | '
            f'ip={request.remote_addr}'
        )

        return '', 204

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

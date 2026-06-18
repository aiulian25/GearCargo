"""
GearCargo - Application Configuration
"""

import os
from datetime import timedelta


def _read_docker_secret(name: str) -> str:
    """Read a value from a Docker secret file at /run/secrets/<name>.

    Docker secrets are bind-mounted into the container at /run/secrets/ and
    are NOT exposed via `docker inspect`, unlike environment variables.
    Returns an empty string if the file does not exist or cannot be read
    (e.g. in development where no secrets directory is mounted).
    """
    try:
        with open(f'/run/secrets/{name}') as fh:
            return fh.read().strip()
    except OSError:
        return ''


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
    # Connection-pool hardening (STARTUP_SLOWNESS_INVESTIGATION.md §4.6):
    #   * pool_pre_ping — validate a pooled connection before use; transparently
    #     replaces ones dropped by a Postgres restart. KEEP True.
    #   * pool_recycle (300s) — recycle connections older than 5 min. Do NOT
    #     change this to "fix" the post-restart outage: that was caused by
    #     workers SHARING the master's connections (preload + a no-op post_fork
    #     dispose — fixed in §4.1), not by the recycle value. With §4.1 in place
    #     the 5-minute recycle is harmless.
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
    JWT_COOKIE_SAMESITE = os.environ.get('SESSION_COOKIE_SAMESITE', 'Strict')  # S26: Strict prevents top-level cross-site GET leakage for this private PWA
    JWT_COOKIE_HTTPONLY = True
    JWT_COOKIE_CSRF_PROTECT = True
    
    # Session
    SESSION_TYPE = 'redis'
    SESSION_PERMANENT = True
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    SESSION_USE_SIGNER = True
    SESSION_KEY_PREFIX = 'gearcargo:'
    SESSION_REDIS = None  # Set in __init__ based on REDIS_URL
    # Explicitly point the filesystem-fallback to /tmp so it stays within the
    # container's tmpfs mount when read_only: true is set (e.g. Synology deploy).
    # Flask-Session's default is tempfile.gettempdir() which is /tmp on Linux,
    # but being explicit avoids subtle breakage if CWD changes or TMPDIR is unset.
    SESSION_FILE_DIR = '/tmp/flask_session'
    SESSION_COOKIE_HTTPONLY = os.environ.get('SESSION_COOKIE_HTTPONLY', 'true').lower() == 'true'
    SESSION_COOKIE_SAMESITE = os.environ.get('SESSION_COOKIE_SAMESITE', 'Strict')  # S26: Strict removes residual CSRF risk; no legitimate cross-site form submissions in a private PWA
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
    # S06: comma-separated list of PREVIOUS encryption keys, kept only for the
    # duration of a key rotation. New data is always encrypted with ENCRYPTION_KEY;
    # any key listed here can still DECRYPT old ciphertext, enabling zero-downtime
    # rotation. After running scripts/reencrypt_pii.py to migrate all rows to the
    # new key, remove this variable. Prefer a Docker secret over an env var.
    ENCRYPTION_KEYS_OLD = (
        _read_docker_secret('encryption_keys_old')
        or os.environ.get('ENCRYPTION_KEYS_OLD', '')
    )
    
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
    # VAPID_PUBLIC_KEY and VAPID_SUBJECT are non-sensitive and kept as env vars.
    # VAPID_PRIVATE_KEY is a secret — prefer a Docker secret file over an env var
    # so it is not exposed in `docker inspect` or /proc/<pid>/environ.
    VAPID_PUBLIC_KEY = os.environ.get('VAPID_PUBLIC_KEY', '')
    VAPID_PRIVATE_KEY = (
        _read_docker_secret('vapid_private_key')
        or os.environ.get('VAPID_PRIVATE_KEY', '')  # fallback for dev / legacy setups
    )
    VAPID_SUBJECT = os.environ.get('VAPID_SUBJECT', 'mailto:admin@gearcargo.local')
    
    # Ollama (External Instance)
    OLLAMA_ENABLED = os.environ.get('OLLAMA_ENABLED', 'true').lower() == 'true'
    # §14.1 — the backend is the SINGLE egress to Ollama (the browser never talks
    # to it; every call passes validate_ollama_url()). For a DISTRIBUTED setup
    # (Ollama on a SEPARATE machine/container) point this at the remote host's
    # LAN IP / DNS / URL, e.g. http://10.0.0.5:11434 or https://ollama.internal —
    # and use https + a private network/firewall (§14.2). The default
    # 'host.docker.internal' only resolves the BACKEND's own host, so it is NOT
    # correct for a different machine; override OLLAMA_BASE_URL in that topology.
    OLLAMA_BASE_URL = os.environ.get('OLLAMA_BASE_URL', 'http://host.docker.internal:11434')
    OLLAMA_URL = OLLAMA_BASE_URL  # Alias for backwards compatibility
    # OLLAMA_MODEL: set this to the model name you have installed in Ollama.
    # Run `ollama list` to see available models.  No default is set here —
    # the admin must configure a model via the Admin > AI Settings panel or
    # the OLLAMA_MODEL environment variable before AI features can be used.
    OLLAMA_MODEL = os.environ.get('OLLAMA_MODEL', '')
    OLLAMA_TIMEOUT = int(os.environ.get('OLLAMA_TIMEOUT', 30))
    # Distributed deployment (§14): Ollama runs on a separate machine/container.
    # Short connect timeout so a dead/unrouteable remote fails in seconds rather
    # than holding a sync gunicorn worker for the whole read window.
    OLLAMA_CONNECT_TIMEOUT = int(os.environ.get('OLLAMA_CONNECT_TIMEOUT', 5))
    # Per-task model overrides — env-var defaults; also settable via admin UI.
    # Empty string means "fall back to the global model".
    OLLAMA_MODEL_PREDICT  = os.environ.get('OLLAMA_MODEL_PREDICT', '')
    OLLAMA_MODEL_OCR      = os.environ.get('OLLAMA_MODEL_OCR', '')
    OLLAMA_MODEL_ANOMALY  = os.environ.get('OLLAMA_MODEL_ANOMALY', '')
    OLLAMA_MODEL_REMINDER = os.environ.get('OLLAMA_MODEL_REMINDER', '')
    # Chat Layer 2 input classifier — a small/fast model (e.g. llama3.2:1b,
    # phi3:mini, qwen2.5:0.5b). Falls back to the global model if unset
    # (resolve_model). Empty = use global.
    OLLAMA_MODEL_CLASSIFIER = os.environ.get('OLLAMA_MODEL_CLASSIFIER', '')

    # Vehicle chat rate limit (per user). Generous enough for a natural
    # back-and-forth about the user's car/app, while the per-minute burst still
    # bounds abuse (each chat = up to two remote model calls — see §14.3 pool
    # starvation). Flask-Limiter syntax; multiple limits separated by ';'.
    CHAT_RATE_LIMIT = os.environ.get('CHAT_RATE_LIMIT', '15 per minute; 100 per hour')

    # Vehicle chat assistant (CHAT_HARDENING_PLAN §13.2 / Layer 1).
    # Persona name — defaults to the app name for brand consistency and is
    # white-label-safe. Fed into the system prompt's identity block.
    CHAT_ASSISTANT_NAME = os.environ.get('CHAT_ASSISTANT_NAME') or os.environ.get('APP_NAME', 'GearCargo')
    # Low temperature makes the model less likely to "creatively" break the
    # guardrails / persona-lockdown in the hardened system prompt. Accepts the
    # plan's CHAT_MAIN_TEMPERATURE env name, falling back to CHAT_TEMPERATURE.
    CHAT_TEMPERATURE = float(
        os.environ.get('CHAT_MAIN_TEMPERATURE')
        or os.environ.get('CHAT_TEMPERATURE')
        or '0.3'
    )
    # Layer 2 input pre-classifier (ALLOW/BLOCK gate before the main model).
    # Fail-open (default true): if the classifier errors/times out, fall through
    # to the main model (which still has L1 + L3) rather than block real users.
    CHAT_CLASSIFIER_FAIL_OPEN = os.environ.get('CHAT_CLASSIFIER_FAIL_OPEN', 'true').lower() == 'true'
    # Read timeouts (§14.3): dedicated budgets per hop instead of inheriting
    # OLLAMA_TIMEOUT. Invariant: connect + classifier + connect + main <
    # GUNICORN_TIMEOUT, with margin (defaults: 5+15+5+90 = 115 < 360).
    #
    # Sync gunicorn workers (GUNICORN_WORKERS, default min(2·cpu+1, 4)) each block
    # for the whole remote call, so pool starvation is defended by: the short
    # OLLAMA_CONNECT_TIMEOUT (dead remote fails in ~5s), the §14.4 circuit breaker
    # (one failure short-circuits the rest), and the per-user 5/h chat rate limit.
    # For higher AI concurrency, raise GUNICORN_WORKERS (needs RAM). NOTE: chat is
    # a synchronous request/response, so the fire-and-forget task queue (§1.5/Q03,
    # TASK_QUEUE_BACKEND=rq) does NOT apply to it — it's for background work.
    CHAT_CLASSIFIER_TIMEOUT = int(os.environ.get('CHAT_CLASSIFIER_TIMEOUT', 15))
    CHAT_MAIN_TIMEOUT = int(os.environ.get('CHAT_MAIN_TIMEOUT', 90))
    # Tight output cap for the classifier — it only emits a short JSON decision
    # ({"decision":"ALLOW"|"BLOCK"}), so a small num_predict keeps it fast.
    CHAT_CLASSIFIER_NUM_PREDICT = int(os.environ.get('CHAT_CLASSIFIER_NUM_PREDICT', 16))
    # Master enable for the Layer 2 gate (env default; admin can override at
    # runtime via the AppSetting 'chat_classifier_enabled').
    CHAT_CLASSIFIER_ENABLED = os.environ.get('CHAT_CLASSIFIER_ENABLED', 'true').lower() == 'true'
    # Optional Layer 3 phase-2: a second tiny-model ALLOW/BLOCK pass over the
    # ANSWER (stronger than regex). OFF by default — it adds one small model call
    # per answer; enable only where the extra robustness is worth the latency.
    CHAT_OUTPUT_CLASSIFIER_ENABLED = os.environ.get('CHAT_OUTPUT_CLASSIFIER_ENABLED', 'false').lower() == 'true'
    
    # Writable data root (logs, attachments, backups). Defaults to the container
    # path; overridable via env so non-container hosts and CI can point it at a
    # writable location without privileged setup. Defaults are unchanged.
    VOLUMES_PATH = os.environ.get('VOLUMES_PATH', '/app/volumes')

    # Logging (IMPROVEMENTS §5) — general app log hygiene.
    # LOG_REDACT_PII scrubs emails/IPs/tokens from the general logs (the
    # dedicated security_audit log is unaffected). LOG_FORMAT=json emits
    # one JSON object per line for ingestion.
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FORMAT = os.environ.get('LOG_FORMAT', 'text')
    LOG_REDACT_PII = os.environ.get('LOG_REDACT_PII', 'true').lower() == 'true'

    # Background task queue (IMPROVEMENTS §5 / §1.5 S12).
    # 'thread' (default) preserves the historical in-process daemon-thread
    # behaviour — no extra process required. Set 'rq' to offload heavy work
    # (e.g. OCR) to a separate `python rq_worker.py` process on the same Redis.
    TASK_QUEUE_BACKEND = os.environ.get('TASK_QUEUE_BACKEND', 'thread')
    TASK_QUEUE_NAME = os.environ.get('TASK_QUEUE_NAME', 'gearcargo')
    TASK_QUEUE_DEFAULT_TIMEOUT = int(os.environ.get('TASK_QUEUE_TIMEOUT', 600))

    # File uploads
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_UPLOAD_SIZE_MB', 200)) * 1024 * 1024
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', '/app/volumes/attachments')
    BACKUP_FOLDER = os.environ.get('BACKUP_FOLDER', '/app/volumes/backups')
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf', 'bmp', 'tiff'}
    
    # Rate limiting
    RATELIMIT_ENABLED = os.environ.get('RATELIMIT_ENABLED', 'true').lower() == 'true'
    RATELIMIT_STORAGE_URL = os.environ.get('RATELIMIT_STORAGE_URL', os.environ.get('REDIS_URL', 'memory://'))
    RATELIMIT_DEFAULT = os.environ.get('RATELIMIT_DEFAULT', '200 per day')
    RATELIMIT_HEADERS_ENABLED = True
    RATELIMIT_STRATEGY = 'fixed-window'  # Valid strategies: fixed-window, moving-window

    # S11: Reverse-proxy trust depth for X-Forwarded-For processing via werkzeug ProxyFix.
    # Set to the number of trusted reverse proxies in front of the app:
    #   0 — no proxy; use request.remote_addr directly (dev / direct-bind)
    #   1 — one proxy (nginx, Traefik, Cloudflare, etc.) — default for production
    #   2 — proxy behind a CDN (e.g. Cloudflare in front of nginx)
    # ProxyFix rewrites request.remote_addr to the nth-from-right hop in
    # X-Forwarded-For, so Flask-Limiter and all IP-reading code always see the
    # real client IP regardless of how many trusted hops strip/add headers.
    # A client can never forge their IP by injecting extra XFF entries because
    # ProxyFix only peels exactly TRUSTED_PROXY_COUNT hops from the RIGHT of the list.
    TRUSTED_PROXY_COUNT = int(os.environ.get('TRUSTED_PROXY_COUNT', '1'))

    # S22: Widget CORS origin allowlist.
    # Default '*' maintains backward-compatibility with Gethomepage (server-side
    # fetches that never send cookies).  Set to a space-separated list of origins
    # (e.g. 'https://homepage.example.com') to restrict browser-based callers.
    # Widget endpoints use API-key auth, so '*' does not introduce CSRF risk.
    WIDGET_CORS_ORIGINS = os.environ.get('WIDGET_CORS_ORIGINS', '*')
    
    # Security Headers (reference only — actual CSP is configured via Talisman in __init__.py)
    CONTENT_SECURITY_POLICY = {
        'default-src': "'self'",
        'script-src': "'self'",  # No 'unsafe-inline'; Vite output has no inline scripts
        'style-src': "'self' 'unsafe-inline' https://fonts.googleapis.com",
        'font-src': "'self' https://fonts.gstatic.com data:",
        'img-src': "'self' data: blob: https:",
        'connect-src': "'self'",
        'frame-ancestors': "'none'",
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

    # GeoIP2 local database (S10 — replaces external ip-api.com HTTP lookup).
    # Point to a MaxMind GeoLite2-City MMDB file on the host.
    # When unset (default) suspicious-login country detection is disabled but
    # login still works normally. No external network call is ever made.
    # Download free at: https://dev.maxmind.com/geoip/geolite2-free-geolocation-data
    GEOIP_DB_PATH = os.environ.get('GEOIP_DB_PATH', '')


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    SESSION_COOKIE_SECURE = False
    JWT_COOKIE_SECURE = False
    WTF_CSRF_SSL_STRICT = False
    # Keep full, readable logs locally unless explicitly overridden.
    LOG_REDACT_PII = os.environ.get('LOG_REDACT_PII', 'false').lower() == 'true'


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

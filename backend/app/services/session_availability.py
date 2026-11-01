"""Controlled failures for durable authentication and browser session storage."""
import json
from flask import request
from flask.sessions import SessionInterface
from werkzeug.exceptions import ServiceUnavailable


class SessionStoreUnavailable(ServiceUnavailable):
    description = 'Sign-in verification is temporarily unavailable. Please retry shortly.'

    def get_body(self, environ=None, scope=None):
        return json.dumps({'error': self.description, 'code': 'AUTH_UNAVAILABLE'})

    def get_headers(self, environ=None, scope=None):
        return [('Content-Type', 'application/json'), ('Cache-Control', 'no-store'), ('Retry-After', '5')]


class GuardedRedisSessionInterface(SessionInterface):
    """No anonymous/empty-session fallback when the CSRF store cannot be read.

    Flask opens sessions before dispatch and saves them after the view returns.
    Handle those boundaries explicitly so storage errors cannot become a 500 or
    deliver new auth cookies alongside an unpersisted browser proof.
    """
    def __init__(self, delegate):
        self.delegate = delegate

    def __getattr__(self, name):
        return getattr(self.delegate, name)

    def open_session(self, app, req):
        try:
            return self.delegate.open_session(app, req)
        except Exception as exc:
            app.logger.warning('Browser session read unavailable (%s)', type(exc).__name__)
            req.environ['gearcargo.session_unavailable'] = True
            return self.make_null_session(app)

    def save_session(self, app, session, response):
        try:
            self.delegate.save_session(app, session, response)
        except Exception as exc:
            app.logger.warning('Browser session write unavailable (%s)', type(exc).__name__)
            error = SessionStoreUnavailable()
            response.status_code = error.code
            response.set_data(error.get_body())
            response.headers.pop('Set-Cookie', None)
            for name, value in error.get_headers():
                response.headers[name] = value


def guard_redis_sessions(app):
    from redis.exceptions import RedisError
    from limits.errors import StorageError
    from flask_session.redis import RedisSessionInterface

    def cache_unavailable(exc):
        # A failed Redis-backed rate limiter must not be silently bypassed.
        app.logger.warning('Request cache dependency unavailable (%s)', type(exc).__name__)
        return SessionStoreUnavailable().get_response()
    app.register_error_handler(RedisError, cache_unavailable)
    app.register_error_handler(StorageError, cache_unavailable)

    if not isinstance(app.session_interface, RedisSessionInterface):
        return
    app.session_interface = GuardedRedisSessionInterface(app.session_interface)

    def require_browser_session_store():
        if request.environ.get('gearcargo.session_unavailable'):
            return SessionStoreUnavailable().get_response()
    # Before CSRF/authentication: the original cookie is retained for recovery.
    app.before_request_funcs.setdefault(None, []).insert(0, require_browser_session_store)

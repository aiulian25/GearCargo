"""CSRF boundary for browser credentials, independent of proxy request headers."""
from urllib.parse import urlsplit

from flask import current_app, jsonify, request, session
from flask_wtf.csrf import generate_csrf, validate_csrf
from wtforms.validators import ValidationError

SAFE_METHODS = {'GET', 'HEAD', 'OPTIONS'}


def _origin(value, *, referer=False):
    if not value or any(c.isspace() or c in '\\,*' for c in value):
        raise ValueError('Invalid origin')
    parts = urlsplit(value)
    if (parts.scheme not in {'http', 'https'} or not parts.hostname
            or parts.username is not None or parts.password is not None
            or (not referer and (parts.path not in {'', '/'} or parts.query or parts.fragment))):
        raise ValueError('Expected an HTTP(S) origin without credentials or a path')
    port = parts.port if parts.port is not None else (443 if parts.scheme == 'https' else 80)
    return parts.scheme, parts.hostname.lower(), port


def rotate_csrf_token():
    """Invalidate browser proof when credentials change; never store JWTs here."""
    session.pop(current_app.config.get('WTF_CSRF_FIELD_NAME', 'csrf_token'), None)


def _reject(code):
    response = jsonify(code=code, error='Request verification failed. Reload the page and try again.')
    response.status_code = 403
    response.headers['Cache-Control'] = 'no-store'
    return response


def init_cookie_csrf(app, csrf):
    configured = app.config.get('CSRF_TRUSTED_ORIGINS') or [app.config['APP_URL']]
    if isinstance(configured, str):
        configured = [value.strip() for value in configured.split(',') if value.strip()]
    try:
        trusted = frozenset(_origin(value) for value in configured)
        if not trusted:
            raise ValueError('Empty origin allowlist')
    except (ValueError, TypeError) as exc:
        raise ValueError('CSRF_TRUSTED_ORIGINS (or APP_URL) must contain exact HTTP(S) origins') from exc

    # Flask-WTF supplies the signed, expiring synchronizer token. The boundary
    # below selects credential sources and uses configured public origins,
    # instead of Flask-WTF's request.host / HTTPS Referer comparison.
    app.config['WTF_CSRF_CHECK_DEFAULT'] = False
    csrf.init_app(app)

    def browser_origin_error():
        origin = request.headers.get('Origin')
        referer = request.headers.get('Referer')
        site = request.headers.get('Sec-Fetch-Site', '').lower()
        if site == 'cross-site':
            return _reject('CSRF_ORIGIN_REJECTED')
        source = origin if origin is not None else referer
        if source is not None:
            try:
                if _origin(source, referer=origin is None) not in trusted:
                    return _reject('CSRF_ORIGIN_REJECTED')
            except ValueError:
                return _reject('CSRF_ORIGIN_REJECTED')
        elif site == 'same-site':
            # Metadata says a sibling initiated this request, but supplies no
            # verifiable origin. Older clients without metadata still need proof.
            return _reject('CSRF_ORIGIN_REJECTED')
        return None

    @app.before_request
    def protect_cookie_mutations():
        if (not app.config.get('WTF_CSRF_ENABLED', True)
                or request.method in SAFE_METHODS or not request.path.startswith('/api/')):
            return None
        # Browser-generated CSP reports cannot carry an application header.
        # This anonymous, rate-limited log sink never uses cookies to authorize
        # user-data changes. Keep this exception limited to its exact endpoint.
        if request.endpoint == 'csp_report':
            return None
        view = app.view_functions.get(request.endpoint)
        auth_kind = getattr(view, '_csrf_auth', None)
        auth = request.headers.get('Authorization', '').split()
        has_auth_cookie = bool(request.cookies.get('access_token') or request.cookies.get('refresh_token'))
        # Only an endpoint that actually authenticates the explicit credential
        # may bypass browser proof. An extra header cannot override cookie auth.
        if auth_kind == 'api-key' and request.headers.get('X-API-Key'):
            return None
        if (auth_kind == 'bearer-or-cookie' and not has_auth_cookie
                and len(auth) == 2 and auth[0].lower() == 'bearer'):
            return None
        if request.endpoint == 'auth.refresh_token' and not has_auth_cookie and request.is_json:
            body = request.get_json(silent=True)
            if isinstance(body, dict) and body.get('refresh_token'):
                return None  # Explicit refresh credential is validated by the route.
        error = browser_origin_error()
        if error is not None:
            return error
        try:
            validate_csrf(request.headers.get('X-CSRF-Token'))
        except ValidationError:
            return _reject('CSRF_INVALID')
        return None

    @app.get('/api/csrf-token')
    @app.get('/api/auth/csrf-token')
    def get_csrf_token():
        error = browser_origin_error() if app.config.get('WTF_CSRF_ENABLED', True) else None
        if error is not None:
            return error
        response = jsonify(csrf_token=generate_csrf())
        response.headers['Cache-Control'] = 'no-store'
        return response

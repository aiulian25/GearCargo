"""Gunicorn logging without raw targets, headers or environment values."""
import uuid

from gunicorn.glogging import Logger
from log_sanitization import CapabilitySafeFormatter

_METHODS = frozenset({'GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'CONNECT', 'TRACE'})


class CapabilitySafeLogger(Logger):
    def setup(self, cfg):
        super().setup(cfg)
        for logger in (self.error_log, self.access_log):
            for handler in logger.handlers:
                handler.setFormatter(CapabilitySafeFormatter(handler.formatter))

    def atoms(self, resp, req, environ, request_time):
        # Do not call super().atoms(): it copies every request/response header,
        # the raw URI, referrer and WSGI environment into the logging record.
        method = environ.get('REQUEST_METHOD')
        method = method if method in _METHODS else '[invalid-method]'
        route = environ.get('gearcargo.log_route', '/[unmatched]')
        request_id = environ.get('gearcargo.request_id') or uuid.uuid4().hex
        status = str(resp.status).split(None, 1)[0]
        duration = int(request_time.total_seconds() * 1_000_000)
        return {'t': self.now(), 'm': method, 'U': route, 'r': f'{method} {route}',
                's': status, 'b': getattr(resp, 'sent', None) or 0,
                'D': duration, 'gc_route': route, 'gc_request_id': request_id}

    def debug(self, msg, *args, **kwargs):
        # Gunicorn's worker debug trace otherwise emits req.path before Flask
        # has resolved the route (including malformed/unmatched targets).
        if msg == '%s %s' and len(args) == 2:
            method = args[0] if args[0] in _METHODS else '[invalid-method]'
            return super().debug('%s [request target omitted]', method, **kwargs)
        return super().debug(msg, *args, **kwargs)

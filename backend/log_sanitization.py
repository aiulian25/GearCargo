"""Capability-safe formatting shared by the application and HTTP server.

Kept outside app so Gunicorn can import it before loading the Flask application.
Query strings and fragments are omitted wholesale: an allowlist of secret query
keys would miss aliases, repeated keys and future bearer parameters.
"""
import copy
import logging
import re
from urllib.parse import unquote, urlsplit, urlunsplit

_URL = re.compile(r'(?:[a-z][a-z0-9+.-]*://|/|%(?:25)*[0-9a-f]{2})[^\s\"\'\\]*', re.I)
_CAPABILITY_PATHS = (
    ('/api/reports/shared/', '/api/reports/shared/<token>'),
    ('/shared/report/', '/shared/report/<token>'),
    ('/api/calendar/feed/', '/api/calendar/feed/<token>'),
    ('/uploads/', '/uploads/<path:filename>'),
)
_HEADER = re.compile(r'\b(authorization|proxy-authorization|cookie|set-cookie|referer|referrer|x-api-key)'
                     r'([\"\']?\s*[:=]\s*)(?:\"[^\"\n]*\"|\'[^\'\n]*\'|[^\n]+)', re.I)
_PROTOCOL_ERROR = re.compile(r'Invalid request from ip=[^\n]*')


def sanitized_url(value):
    """Remove known path capabilities and all query/fragment data in log text."""
    decoded = value
    for _ in range(4):
        next_value = unquote(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    else:
        # Deeply escaped/malformed targets cannot be safely classified.
        return '[redacted-url]'
    try:
        # A request target beginning // is still a path, not a URL authority.
        network_credentials = decoded.startswith('//') and '@' in decoded[2:].split('/', 1)[0]
        relative = decoded.startswith('/') and not network_credentials
        parts = urlsplit('http://log.invalid' + decoded if relative else decoded)
    except ValueError:
        return '[redacted-url]'
    path = parts.path
    normalized_path = re.sub('/+', '/', path)
    for prefix, template in _CAPABILITY_PATHS:
        if normalized_path.lower().startswith(prefix):
            suffix = '/pdf' if prefix == '/api/reports/shared/' and normalized_path.lower().endswith('/pdf') else ''
            path = template + suffix
            break
    # Never log credentials embedded in a URL authority, either.
    authority = '' if relative else parts.netloc.rsplit('@', 1)[-1]
    # Preserve the original spelling when no sensitive content was found (e.g.
    # traceback filesystem paths). Decode only for classification, not output.
    if path == parts.path and not (parts.query or parts.fragment or '@' in parts.netloc):
        return value
    if relative:
        return path + ('?REDACTED' if parts.query else '') + ('#REDACTED' if parts.fragment else '')
    return urlunsplit((parts.scheme, authority, path,
                       'REDACTED' if parts.query else '',
                       'REDACTED' if parts.fragment else ''))


def redact_capabilities(text):
    if not text:
        return text
    text = _PROTOCOL_ERROR.sub('Invalid HTTP request [details omitted]', text)
    text = _HEADER.sub(lambda match: match.group(1) + match.group(2) + '[redacted-header]', text)
    return _URL.sub(lambda match: sanitized_url(match.group()), text)


class CapabilitySafeFormatter(logging.Formatter):
    """Sanitize messages and formatted tracebacks before final text/JSON encoding."""
    def __init__(self, wrapped=None, redact=None):
        super().__init__()
        self.wrapped = wrapped or logging.Formatter('%(message)s')
        self.redact = redact or redact_capabilities

    def format(self, record):
        # Formatters cache exc_text. Isolate that cache from other handlers.
        record = copy.copy(record)
        try:
            record.msg = self.redact(record.getMessage())
            record.args = ()
            if record.exc_info and not record.exc_text:
                record.exc_text = self.wrapped.formatException(record.exc_info)
            if record.exc_text:
                record.exc_text = self.redact(record.exc_text)
            # Prevent a wrapped formatter from reconstructing the raw exception.
            record.exc_info = None
            if record.stack_info:
                record.stack_info = self.redact(record.stack_info)
            return self.wrapped.format(record)
        except Exception:
            # Logging failures must neither expose the raw record nor abort a
            # request. Keep a diagnostic without interpolating unsafe arguments.
            return '[log formatting failed; record omitted]'

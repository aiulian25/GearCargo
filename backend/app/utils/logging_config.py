"""
Application log configuration: PII redaction + optional JSON output.

This configures the **general** application logger (Flask `app.logger` and the
root logger that third-party / module loggers propagate to). It deliberately
does NOT touch the dedicated `security_audit` logger, which keeps full PII for
forensic purposes and never propagates (see app/utils/security_audit.py).

Two concerns from IMPROVEMENTS §5:
  1. No PII (full emails, IPs, tokens) in the general logs beyond what's needed —
     handled by RedactionFilter, applied defensively to every emitted record so
     a single call site cannot leak PII regardless of how it formats its message.
  2. JSON logs for ingestion — set LOG_FORMAT=json.

Config knobs (all read from Flask config / env):
  LOG_LEVEL      default INFO
  LOG_FORMAT     'text' (default) | 'json'
  LOG_REDACT_PII default true (set false to keep full logs in development)
"""

import json
import logging
import re
from datetime import datetime, timezone


# ── PII patterns ──────────────────────────────────────────────────────────────

# Email: keep the first local char + domain so logs stay debuggable (a***@host).
_EMAIL_RE = re.compile(r'([A-Za-z0-9._%+\-])[A-Za-z0-9._%+\-]*@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})')
# JWT-ish: three base64url segments separated by dots.
_JWT_RE = re.compile(r'\b[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\b')
# Long hex blobs (session/reset/API tokens, hashes): 32+ hex chars.
_HEX_TOKEN_RE = re.compile(r'\b[0-9a-fA-F]{32,}\b')
# IPv4: keep the first two octets for coarse geo/debug, mask the host part.
_IPV4_RE = re.compile(r'\b(\d{1,3})\.(\d{1,3})\.\d{1,3}\.\d{1,3}\b')
# IPv6: collapse to the first two hextets.
_IPV6_RE = re.compile(r'\b([A-Fa-f0-9]{1,4}:[A-Fa-f0-9]{1,4}):(?:[A-Fa-f0-9]{0,4}:){1,6}[A-Fa-f0-9]{0,4}\b')


def mask_email(email):
    """Mask an email for logging: 'john.doe@example.com' -> 'j***@example.com'.

    Use this at explicit call sites where an email would otherwise be logged.
    """
    if not email or '@' not in str(email):
        return email
    return _EMAIL_RE.sub(lambda m: f'{m.group(1)}***@{m.group(2)}', str(email))


def redact(text: str) -> str:
    """Redact emails, tokens and IPs from a free-text log message."""
    if not text:
        return text
    text = _EMAIL_RE.sub(lambda m: f'{m.group(1)}***@{m.group(2)}', text)
    text = _JWT_RE.sub('[redacted-token]', text)
    text = _HEX_TOKEN_RE.sub('[redacted-token]', text)
    text = _IPV4_RE.sub(lambda m: f'{m.group(1)}.{m.group(2)}.x.x', text)
    text = _IPV6_RE.sub(lambda m: f'{m.group(1)}::redacted', text)
    return text


class RedactionFilter(logging.Filter):
    """Scrubs PII from each record's final message (and any exception text)."""

    def filter(self, record):
        try:
            message = record.getMessage()
        except Exception:
            return True  # never drop a log line because redaction failed
        redacted = redact(message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        # Redact PII that may appear in an attached exception/stack message.
        if record.exc_text:
            record.exc_text = redact(record.exc_text)
        return True


class JsonLogFormatter(logging.Formatter):
    """One JSON object per line, suitable for log ingestion pipelines."""

    def format(self, record):
        payload = {
            'time': datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'module': record.module,
            'message': record.getMessage(),
        }
        if record.exc_info:
            payload['exception'] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


_TEXT_FORMAT = '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'


def configure_logging(app):
    """Apply level, formatter and (optional) PII redaction to the app/root logs.

    Idempotent: safe to call once per app instance (handlers are tagged so a
    re-run in tests does not stack duplicate filters/handlers).
    """
    level_name = str(app.config.get('LOG_LEVEL', 'INFO')).upper()
    level = getattr(logging, level_name, logging.INFO)

    use_json = str(app.config.get('LOG_FORMAT', 'text')).lower() == 'json'
    redact_pii = bool(app.config.get('LOG_REDACT_PII', True))

    formatter = JsonLogFormatter() if use_json else logging.Formatter(_TEXT_FORMAT)
    redaction = RedactionFilter() if redact_pii else None

    def _apply(logger):
        logger.setLevel(level)
        if not logger.handlers:
            logger.addHandler(logging.StreamHandler())
        for handler in logger.handlers:
            handler.setFormatter(formatter)
            if redaction and not getattr(handler, '_gc_redaction_applied', False):
                handler.addFilter(redaction)
                handler._gc_redaction_applied = True

    # Flask's app logger (current_app.logger / app.logger call sites)…
    _apply(app.logger)
    # …and the root logger that module-level loggers propagate to.
    _apply(logging.getLogger())

    app.logger.debug(
        'Logging configured: level=%s format=%s redact_pii=%s',
        level_name, 'json' if use_json else 'text', redact_pii,
    )

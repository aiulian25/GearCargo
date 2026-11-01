"""Unit tests for general-log PII redaction + JSON formatting.

See app/utils/logging_config.py. Pure-function tests — no app context needed.
"""

import json
import logging
import sys

import pytest

from log_sanitization import CapabilitySafeFormatter, redact_capabilities

from app.utils.logging_config import (
    redact,
    mask_email,
    RedactionFilter,
    JsonLogFormatter,
)


# ── redact() ──────────────────────────────────────────────────────────────────

def test_redact_email_keeps_first_char_and_domain():
    out = redact("login for john.doe@example.com failed")
    assert "john.doe@example.com" not in out
    assert "j***@example.com" in out


def test_redact_ipv4_masks_host_part():
    out = redact("request from 203.0.113.45 blocked")
    assert "203.0.113.45" not in out
    assert "203.0.x.x" in out


def test_redact_ipv6():
    out = redact("peer 2001:db8:1234:5678:9abc:def0:1234:5678 seen")
    assert "9abc:def0" not in out
    assert "2001:db8::redacted" in out


def test_redact_jwt_token():
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjoxfQ.abcDEF123456_-xyz"
    out = redact(f"token={jwt}")
    assert jwt not in out
    assert "[redacted-token]" in out


def test_redact_long_hex_token():
    token = "a" * 40
    out = redact(f"reset link token {token}")
    assert token not in out
    assert "[redacted-token]" in out


def test_redact_is_noop_for_clean_text():
    msg = "vehicle 42 service entry created"
    assert redact(msg) == msg


def test_redact_handles_empty():
    assert redact("") == ""
    assert redact(None) is None


# ── mask_email() ───────────────────────────────────────────────────────────────

def test_mask_email():
    assert mask_email("alice@example.com") == "a***@example.com"
    assert mask_email("not-an-email") == "not-an-email"
    assert mask_email("") == ""


# ── RedactionFilter (integration with logging records) ─────────────────────────

def test_filter_redacts_record_message():
    record = logging.LogRecord(
        name="app", level=logging.INFO, pathname=__file__, lineno=1,
        msg="account %s from %s", args=("bob@example.com", "198.51.100.7"),
        exc_info=None,
    )
    assert RedactionFilter().filter(record) is True
    rendered = record.getMessage()
    assert "bob@example.com" not in rendered
    assert "198.51.100.7" not in rendered
    assert "b***@example.com" in rendered
    assert "198.51.x.x" in rendered


# ── JsonLogFormatter ───────────────────────────────────────────────────────────

def test_json_formatter_emits_valid_json_with_redaction():
    record = logging.LogRecord(
        name="app", level=logging.WARNING, pathname=__file__, lineno=1,
        msg="failed login for carol@example.com", args=(), exc_info=None,
    )
    # Filter runs before the formatter in the logging pipeline.
    RedactionFilter().filter(record)
    line = JsonLogFormatter().format(record)
    payload = json.loads(line)
    assert payload["level"] == "WARNING"
    assert payload["logger"] == "app"
    assert "carol@example.com" not in payload["message"]
    assert "c***@example.com" in payload["message"]
    assert "time" in payload


@pytest.mark.parametrize('target', [
    '/api/reports/shared/Short-secret_Q',
    '/api/reports/shared/Short-secret_Q/pdf',
    '/shared/report/Short-secret_Q',
    '/api/calendar/feed/Short-secret_Q',
    '//api//reports/shared/Short-secret_Q',
    '/uploads/Short-secret_Q.jpg',
    '/api/attachments/42/view?sig=Short-secret_Q&sig=Other-secret_R&EXP=123',
    'https://test.invalid/api/reports/shared/Short-secret_Q?x=Other-secret_R',
    '%2Fapi%2Freports%2Fshared%2FShort-secret_Q',
    '%252Fapi%252Fcalendar%252Ffeed%252FShort-secret_Q',
    '/api/other?%73ig=Short-secret_Q#Other-secret_R',
    'https://Short-secret_Q@test.invalid/path#Other-secret_R',
    '//Short-secret_Q@test.invalid/path?sig=Other-secret_R',
    'http://[malformed/Short-secret_Q',
])
def test_capability_urls_are_redacted_and_idempotent(target):
    result = redact_capabilities(f'request failed: {target}')
    assert 'Short-secret_Q' not in result
    assert 'Other-secret_R' not in result
    assert redact_capabilities(result) == result


@pytest.mark.parametrize('header', [
    'Referer', 'Referrer', 'rEfErEr', 'REFERRER', 'Authorization',
    'Proxy-Authorization', 'Cookie', 'Set-Cookie', 'X-API-Key',
])
def test_sensitive_headers_never_log_their_values(header):
    assert 'Short-secret_Q' not in redact_capabilities(f'{header}: Short-secret_Q')


@pytest.mark.parametrize('json_output', [False, True])
@pytest.mark.parametrize('redactor', [redact, redact_capabilities])
def test_formatter_sanitizes_message_traceback_and_stack_before_encoding(json_output, redactor):
    try:
        raise RuntimeError('/api/reports/shared/Short-secret_Q?sig=Other-secret_R')
    except RuntimeError:
        record = logging.LogRecord('app', logging.ERROR, __file__, 1,
                                   'Referer: %s', ('Short-secret_Q',), sys.exc_info())
    record.stack_info = 'stack: /api/calendar/feed/Other-secret_R'
    wrapped = JsonLogFormatter() if json_output else logging.Formatter('%(message)s')
    rendered = CapabilitySafeFormatter(wrapped, redactor).format(record)
    assert 'Short-secret_Q' not in rendered
    assert 'Other-secret_R' not in rendered
    assert 'RuntimeError' in rendered
    assert 'Traceback' in rendered
    assert record.exc_text is None  # No raw exception cache shared across handlers.
    if json_output:
        payload = json.loads(rendered)
        assert 'RuntimeError' in payload['exception']
        assert '<token>' in payload['stack']


def test_invalid_record_has_no_unsafe_fallback():
    record = logging.LogRecord('app', logging.ERROR, __file__, 1,
                               'Short-secret_Q %s %s', ('one',), None)
    assert CapabilitySafeFormatter().format(record) == '[log formatting failed; record omitted]'


def test_invalid_protocol_details_are_omitted_including_ipv6_peer():
    result = redact_capabilities('Invalid request from ip=::1: Invalid header Short-secret_Q')
    assert result == 'Invalid HTTP request [details omitted]'


def test_request_identity_uses_route_template_and_ignores_supplied_id(app):
    from flask import request
    from app.utils.logging_config import configure_logging

    @app.get('/gc032-identity/<secret>')
    def identity(secret):
        return {'route': request.environ['gearcargo.log_route'],
                'request_id': request.environ['gearcargo.request_id']}

    before = len(app.before_request_funcs[None])
    configure_logging(app)
    assert len(app.before_request_funcs[None]) == before
    response = app.test_client().get('/gc032-identity/Short-secret_Q',
                                     headers={'X-Request-ID': 'Other-secret_R'})
    assert response.status_code == 200
    assert response.json['route'] == '/gc032-identity/<secret>'
    request_id = response.headers['X-Request-ID']
    assert len(request_id) == 32 and int(request_id, 16) >= 0
    assert response.json['request_id'] == request_id

"""Unit tests for general-log PII redaction + JSON formatting.

See app/utils/logging_config.py. Pure-function tests — no app context needed.
"""

import json
import logging

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

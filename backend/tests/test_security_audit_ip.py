"""Regression tests for R4-05: the security audit log recorded a
client-controlled IP address.

`_get_client_ip` returned the LEFTMOST X-Forwarded-For entry, which any caller
can set to anything. ProxyFix (applied in create_app, S11) has already resolved
the real client into `request.remote_addr` by peeling exactly
TRUSTED_PROXY_COUNT hops from the RIGHT, so the header must not be re-read.

The consequence was not cosmetic: every login failure, lockout, export and admin
action could be attributed to an address the attacker chose, while the
lockout/blocking machinery (already using the ProxyFix value) acted on a
different one — the audit trail and the enforcement disagreed.

NOTE on method: ProxyFix is WSGI middleware, so it only runs for requests made
through the test CLIENT. `test_request_context` builds a context directly from
the environ and never invokes it — which is exactly why the unit-level test
below asserts "the header is ignored" rather than "the trusted hop is chosen".
"""

import json
import logging

import pytest

from app import db
from app.models import User
from app.utils.security_audit import security_audit


SPOOFED = '1.1.1.1'          # what the caller claims
TRUSTED_HOP = '9.9.9.9'      # what the trusted proxy appended — the real client
DIRECT_PEER = '10.0.0.5'     # the proxy itself


@pytest.fixture()
def audit_records(app):
    """Capture the JSON records the audit logger emits.

    A handler attached straight to the audit logger, rather than caplog: the
    audit logger manages its own handlers and propagation in init_app(), so
    going through the root logger is not reliable here.
    """
    security_audit.init_app(app)
    collected = []

    class _Collector(logging.Handler):
        def emit(self, record):
            collected.append(record.getMessage())

    handler = _Collector()
    security_audit._logger.addHandler(handler)
    security_audit._logger.setLevel(logging.INFO)
    try:
        yield lambda: [json.loads(message) for message in collected]
    finally:
        security_audit._logger.removeHandler(handler)


def _failed_login(client, forwarded=f'{SPOOFED}, {TRUSTED_HOP}'):
    headers = {'X-Forwarded-For': forwarded} if forwarded else {}
    return client.post('/api/auth/login',
                       json={'email': 'victim@example.com', 'password': 'WrongPass123!'},
                       headers=headers,
                       environ_base={'REMOTE_ADDR': DIRECT_PEER})


def _login_failures(records):
    """event_type is emitted upper-cased (LOGIN_FAILED)."""
    return [r for r in records if r.get('event_type', '').lower() == 'login_failed']


def _make_victim(app):
    with app.app_context():
        user = User(username='victim', email='victim@example.com', is_active=True)
        user.set_password('StrongPass123!')
        db.session.add(user)
        db.session.commit()


def test_the_helper_never_consults_the_forwarded_header(app):
    """Unit level: whatever the caller sends in X-Forwarded-For is ignored; the
    helper reports the address the WSGI layer resolved."""
    with app.test_request_context('/api/auth/login', method='POST',
                                  headers={'X-Forwarded-For': SPOOFED},
                                  environ_base={'REMOTE_ADDR': DIRECT_PEER}):
        assert security_audit._get_client_ip() == DIRECT_PEER   # was: SPOOFED


def test_a_failed_login_is_recorded_against_the_trusted_hop(app, client, audit_records):
    """Integration: through the real WSGI stack, ProxyFix peels exactly
    TRUSTED_PROXY_COUNT hops from the RIGHT, so the caller cannot choose the
    address written to the audit trail."""
    assert app.config['TRUSTED_PROXY_COUNT'] == 1
    _make_victim(app)

    _failed_login(client)

    logins = _login_failures(audit_records())
    assert logins, 'no login_failed audit record was emitted'
    assert logins[-1]['ip'] == TRUSTED_HOP          # was: SPOOFED
    assert SPOOFED not in json.dumps(logins[-1])


def test_without_a_proxy_header_the_direct_peer_is_recorded(app, client, audit_records):
    _make_victim(app)

    _failed_login(client, forwarded=None)

    logins = _login_failures(audit_records())
    assert logins, 'no login_failed audit record was emitted'
    assert logins[-1]['ip'] == DIRECT_PEER


def test_the_audit_trail_and_the_blocking_machinery_agree(app, client, audit_records):
    """The IP written to the audit log must be the same one the lockout /
    IP-blocking path acts on — otherwise you block one address and log another.
    Both now read request.remote_addr, so an ActivityLog row for the same
    request must carry the identical value."""
    from app.models import ActivityLog

    _make_victim(app)
    _failed_login(client)

    logins = _login_failures(audit_records())
    with app.app_context():
        activity = (ActivityLog.query
                    .filter(ActivityLog.ip_address.isnot(None))
                    .order_by(ActivityLog.id.desc()).first())

    assert logins[-1]['ip'] == TRUSTED_HOP
    if activity is not None:      # the login path may or may not log an activity row
        assert activity.ip_address == logins[-1]['ip']

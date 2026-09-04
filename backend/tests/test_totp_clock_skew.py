"""Tests for R4-26 — TOTP verification tolerates one adjacent 30 s step.

`totp.verify(code)` with the default `valid_window=0` accepts only the step
that is current at the instant the server evaluates it. A user who reads a code
in the last second of its step, or whose phone clock is a few seconds off the
server's, is told the code is wrong — and on this app that also counts toward
the M7 account lockout.

The same file already used `valid_window=1` on four other gates (password
change, account deletion, disabling 2FA), so login and the 2FA-enable check
were the odd ones out: a user could enable 2FA on a skewed clock and then be
unable to log in with it. These tests pin every path to the same window.
"""

import time

import pyotp
import pytest

import app.routes.auth as auth_module
from app import db
from app.models import User

TIME_STEP_SECONDS = 30
EMAIL = 'skew@example.com'
PASSWORD = 'StrongPass123!'


def _user_with_2fa(email=EMAIL):
    from app.routes.auth import _set_totp_secret

    secret = pyotp.random_base32()
    user = User(username=email.split('@')[0], email=email, is_active=True)
    user.set_password(PASSWORD)
    _set_totp_secret(user, secret)
    user.two_factor_enabled = True
    db.session.add(user)
    db.session.commit()
    return secret


def _login(client, code):
    return client.post('/api/auth/login', json={
        'email': EMAIL, 'password': PASSWORD, 'totp_code': code,
    })


@pytest.fixture(autouse=True)
def _no_redis(monkeypatch):
    """Exercise the DB lockout fallback, as the sibling 2FA tests do."""
    monkeypatch.setattr(auth_module, 'redis_client', None)


@pytest.mark.parametrize('offset_seconds, label', [
    (0, 'current step'),
    (-TIME_STEP_SECONDS, 'previous step — the code just rolled over'),
    (TIME_STEP_SECONDS, 'next step — the phone clock runs fast'),
])
def test_login_accepts_one_adjacent_step(app, client, offset_seconds, label):
    with app.app_context():
        secret = _user_with_2fa()

    code = pyotp.TOTP(secret).at(time.time() + offset_seconds)

    response = _login(client, code)

    assert response.status_code == 200, f'{label}: {response.get_json()}'


@pytest.mark.parametrize('offset_seconds', [
    -2 * TIME_STEP_SECONDS,
    2 * TIME_STEP_SECONDS,
])
def test_login_still_rejects_two_steps_away(app, client, offset_seconds):
    """The window widens by one step, not indefinitely."""
    with app.app_context():
        secret = _user_with_2fa()

    code = pyotp.TOTP(secret).at(time.time() + offset_seconds)

    assert _login(client, code).status_code == 401


def test_login_still_rejects_a_wrong_code(app, client):
    with app.app_context():
        _user_with_2fa()

    assert _login(client, '000000').status_code == 401


@pytest.mark.parametrize('offset_seconds, label', [
    (0, 'current step'),
    (-TIME_STEP_SECONDS, 'previous step'),
    (TIME_STEP_SECONDS, 'next step'),
])
def test_enabling_2fa_accepts_one_adjacent_step(app, client, auth_headers,
                                                offset_seconds, label):
    """The enable check must not be stricter than login — otherwise a user can
    enable 2FA on a skewed clock and then be locked out of the account they
    just secured."""
    from app.routes.auth import _set_totp_secret

    with app.app_context():
        user = User(username='enabler', email='enabler@example.com', is_active=True)
        user.set_password(PASSWORD)
        secret = pyotp.random_base32()
        _set_totp_secret(user, secret)          # staged in the DB (Redis is off)
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    code = pyotp.TOTP(secret).at(time.time() + offset_seconds)

    response = client.post('/api/auth/2fa/verify', headers=auth_headers(user_id),
                           json={'code': code})

    assert response.status_code == 200, f'{label}: {response.get_json()}'
    with app.app_context():
        assert db.session.get(User, user_id).two_factor_enabled is True


def test_enabling_2fa_still_rejects_two_steps_away(app, client, auth_headers):
    from app.routes.auth import _set_totp_secret

    with app.app_context():
        user = User(username='enabler2', email='enabler2@example.com', is_active=True)
        user.set_password(PASSWORD)
        secret = pyotp.random_base32()
        _set_totp_secret(user, secret)
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    code = pyotp.TOTP(secret).at(time.time() - 2 * TIME_STEP_SECONDS)

    response = client.post('/api/auth/2fa/verify', headers=auth_headers(user_id),
                           json={'code': code})

    assert response.status_code == 401
    with app.app_context():
        assert db.session.get(User, user_id).two_factor_enabled is not True


def test_no_totp_gate_is_left_on_the_default_window():
    """The failure this step is about is the gates DISAGREEING with each other,
    so pin every call site rather than only the two that were wrong."""
    import inspect
    import re

    source = inspect.getsource(auth_module)
    # Collapse continuations so a multi-line call is inspected as one string.
    flattened = re.sub(r'\(\s*\n\s*', '(', source)
    bare_calls = [line.strip() for line in flattened.splitlines()
                  if re.search(r'(totp|TOTP\([^)]*\))\.verify\(', line)
                  and 'valid_window' not in line]

    assert not bare_calls, (
        'these TOTP checks still use the default zero-skew window: '
        + '; '.join(bare_calls))

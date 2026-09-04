"""Regression tests for R4-04: POST /auth/password-reset/request had no
per-account cooldown and no dedicated rate limit.

Every call rotated the account's reset token, so an attacker could both
email-bomb a victim AND repeatedly invalidate the very link the victim was about
to click — bounded only by the global default (100/hour/IP in production).

The fix mirrors the sibling resend-verification endpoint exactly: a per-IP limit
registered in create_app() for the volume case, plus a per-ACCOUNT cooldown for
the distributed case a per-IP limit cannot see. The cooldown is derived from the
token's own expiry (no Redis), so it still holds during a Redis outage.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app import db
from app.config import TestingConfig
from app.models import User
from app.models.user import PASSWORD_RESET_TTL_HOURS


RESET_URL = '/api/auth/password-reset/request'


@pytest.fixture()
def mail_app(app):
    app.config['MAIL_ENABLED'] = True
    return app


def _make_user(email='reset@example.com'):
    user = User(username=email.split('@')[0], email=email, is_active=True,
                email_verified=True)
    user.set_password('StrongPass123!')
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture()
def sent(monkeypatch):
    """Count delivery attempts without touching SMTP."""
    calls = []
    from app.services.email_service import PasswordResetEmailService
    monkeypatch.setattr(
        PasswordResetEmailService, 'send_password_reset_email',
        staticmethod(lambda user, token: calls.append((user.email, token)) or True))
    return calls


def test_a_second_request_neither_resends_nor_rotates_the_token(mail_app, client, sent):
    with mail_app.app_context():
        _make_user()

    first = client.post(RESET_URL, json={'email': 'reset@example.com'})
    with mail_app.app_context():
        token_after_first = User.query.filter_by(email='reset@example.com').first().password_reset_token

    second = client.post(RESET_URL, json={'email': 'reset@example.com'})
    with mail_app.app_context():
        token_after_second = User.query.filter_by(email='reset@example.com').first().password_reset_token

    assert len(sent) == 1                              # was: 2
    assert token_after_second == token_after_first      # the victim's link survives
    # No enumeration signal: both responses are byte-identical.
    assert first.status_code == second.status_code == 200
    assert first.get_json() == second.get_json()


def test_an_unknown_address_is_indistinguishable(mail_app, client, sent):
    with mail_app.app_context():
        _make_user()

    known = client.post(RESET_URL, json={'email': 'reset@example.com'})
    unknown = client.post(RESET_URL, json={'email': 'nobody@example.com'})

    assert known.status_code == unknown.status_code == 200
    assert known.get_json() == unknown.get_json()
    assert [address for address, _ in sent] == ['reset@example.com']


def test_a_new_link_is_issued_once_the_cooldown_has_elapsed(mail_app, client, sent):
    with mail_app.app_context():
        _make_user()

    client.post(RESET_URL, json={'email': 'reset@example.com'})

    with mail_app.app_context():
        user = User.query.filter_by(email='reset@example.com').first()
        first_token = user.password_reset_token
        # Backdate the issue time by rewinding the expiry the cooldown reads.
        user.password_reset_expires = (
            datetime.now(timezone.utc)
            + timedelta(hours=PASSWORD_RESET_TTL_HOURS)
            - timedelta(minutes=6)
        )
        db.session.commit()

    client.post(RESET_URL, json={'email': 'reset@example.com'})

    with mail_app.app_context():
        assert User.query.filter_by(email='reset@example.com').first().password_reset_token != first_token
    assert len(sent) == 2


def test_a_completed_reset_clears_the_cooldown(mail_app, client, sent):
    """Using the link nulls the token+expiry, so the user is never locked out of
    asking for another one."""
    with mail_app.app_context():
        _make_user()

    client.post(RESET_URL, json={'email': 'reset@example.com'})

    with mail_app.app_context():
        user = User.query.filter_by(email='reset@example.com').first()
        user.password_reset_token = None
        user.password_reset_expires = None
        db.session.commit()

    client.post(RESET_URL, json={'email': 'reset@example.com'})
    assert len(sent) == 2


def test_the_endpoint_carries_its_own_rate_limit(tmp_path):
    """A typo in the endpoint name would make _rate_limit() a silent no-op, so
    assert the limit is really wired to this view."""
    from app import create_app

    class LimitedConfig(TestingConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path}/limited.sqlite"
        SESSION_TYPE = 'filesystem'
        SESSION_FILE_DIR = str(tmp_path / 'sessions')
        VOLUMES_PATH = UPLOAD_FOLDER = BACKUP_FOLDER = str(tmp_path)
        RATELIMIT_ENABLED = True
        RATELIMIT_STORAGE_URL = 'memory://'
        RATELIMIT_DEFAULT = '1000 per hour'   # so only the endpoint limit can trip
        MAIL_ENABLED = False

    limited_app = create_app(LimitedConfig)
    with limited_app.app_context():
        db.create_all()

    limited_client = limited_app.test_client()
    statuses = [limited_client.post(RESET_URL, json={'email': 'x@example.com'}).status_code
                for _ in range(6)]

    with limited_app.app_context():
        db.session.remove()
        db.drop_all()

    assert statuses[:5] == [200] * 5
    assert statuses[5] == 429

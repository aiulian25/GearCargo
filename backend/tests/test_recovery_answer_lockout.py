"""Regression tests for M8: the security-question recovery endpoint must still
rate-limit answer guesses when Redis is down.

S21's per-email/per-IP counters live only in Redis, all guarded by
`if redis_client:`. With Redis unavailable the endpoint previously accepted
UNLIMITED guesses — security answers are often low-entropy (pet names, cities).
`verify_recovery_answers` now falls back to the shared DB login-lockout
(`_db_is_account_locked` / `_db_record_failed_login`, MAX_LOGIN_ATTEMPTS / 30 min)
when Redis is falsy or a call raises.

We force `redis_client = None` (as the existing lockout tests do) and drive the
real endpoint.
"""

import app.routes.auth as auth_module
from app import db
from app.models import User

URL = "/api/auth/password/recover/verify-answers"
QUESTIONS = [
    {"question": "First pet?", "answer": "fluffy"},
    {"question": "Birth city?", "answer": "paris"},
]
CORRECT = ["fluffy", "paris"]
WRONG = ["nope", "nope"]


def _user_with_questions(email="recover@example.com"):
    u = User(username=email.split("@")[0], email=email, is_active=True)
    u.set_password("StrongPass123!")
    db.session.add(u)
    db.session.commit()
    u.set_security_questions(QUESTIONS)  # commits
    return u


def test_db_fallback_locks_after_five_wrong_answers(app, client, monkeypatch):
    monkeypatch.setattr(auth_module, "redis_client", None)
    with app.app_context():
        _user_with_questions()

    # Attempts 1–5: wrong answers → 401. The 5th failure arms the DB lock.
    for i in range(auth_module.MAX_LOGIN_ATTEMPTS):
        r = client.post(URL, json={"email": "recover@example.com", "answers": WRONG})
        assert r.status_code == 401, (i, r.status_code, r.get_json())

    # Attempt 6: the pre-check sees the lock → 429 (was: unlimited 401s).
    r = client.post(URL, json={"email": "recover@example.com", "answers": WRONG})
    assert r.status_code == 429, r.get_json()
    assert r.get_json().get("locked") is True


def test_db_fallback_blocks_even_correct_answers_once_locked(app, client, monkeypatch):
    """Once locked, the correct answers can't slip through — the guard runs
    before answer verification (this is the actual brute-force protection)."""
    monkeypatch.setattr(auth_module, "redis_client", None)
    with app.app_context():
        _user_with_questions()

    for _ in range(auth_module.MAX_LOGIN_ATTEMPTS):
        client.post(URL, json={"email": "recover@example.com", "answers": WRONG})

    r = client.post(URL, json={"email": "recover@example.com", "answers": CORRECT})
    assert r.status_code == 429, r.get_json()
    assert r.get_json().get("locked") is True


def test_correct_answers_succeed_when_redis_down(app, client, monkeypatch):
    """The fallback must not break the happy path: correct answers on a fresh
    account still issue a reset token."""
    monkeypatch.setattr(auth_module, "redis_client", None)
    with app.app_context():
        _user_with_questions()

    r = client.post(URL, json={"email": "recover@example.com", "answers": CORRECT})
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body.get("success") is True
    assert body.get("reset_token")


def test_correct_answers_before_threshold_still_succeed(app, client, monkeypatch):
    """Four wrong tries (below the threshold) must not lock a legitimate user
    out of completing recovery with the correct answers."""
    monkeypatch.setattr(auth_module, "redis_client", None)
    with app.app_context():
        _user_with_questions()

    for _ in range(auth_module.MAX_LOGIN_ATTEMPTS - 1):  # 4 wrong
        r = client.post(URL, json={"email": "recover@example.com", "answers": WRONG})
        assert r.status_code == 401

    r = client.post(URL, json={"email": "recover@example.com", "answers": CORRECT})
    assert r.status_code == 200, r.get_json()
    assert r.get_json().get("reset_token")

"""Regression tests for the chat data-isolation guardrails (CHAT_HARDENING_PLAN §8).

Locks the testable invariants so they cannot silently regress:
  - Classifier caches are keyed by a hash of the TEXT only (never per-user).
  - The log hash (_qhash) is non-reversible and deterministic (no raw text).
Ownership scoping (#1/#2) and prompt-sanitisation (#5) are enforced structurally
and covered by test_chat_sanitize.py + the route's owned-vehicle filter.
"""

import hashlib

import app.routes.vehicles as v


def _capture_cache_key(monkeypatch):
    """Make the classifier run and record the cache key it uses."""
    seen = {}
    monkeypatch.setattr(v, 'resolve_model', lambda *_a, **_k: 'tiny-model')
    monkeypatch.setattr(v, 'ai_cache_get', lambda key: seen.setdefault('get', key) and None)
    monkeypatch.setattr(v, 'ai_cache_set', lambda key, *_a, **_k: seen.__setitem__('set', key))
    monkeypatch.setattr(v, 'ollama_chat', lambda **_k: {'decision': 'ALLOW'})
    return seen


def test_input_classifier_cache_key_is_question_hash_only(monkeypatch):
    seen = _capture_cache_key(monkeypatch)
    # Ambiguous phrasing so the on-topic pre-filter doesn't bypass the classifier
    # (bypassed questions never touch the cache, which is what this test checks).
    q = 'is it due soon?'
    v._classify_question(q, 'http://x', {})
    expected = 'chatcls:' + hashlib.sha256(q.encode('utf-8')).hexdigest()
    assert seen['get'] == expected
    assert seen['set'] == expected
    # No per-user component in the key.
    assert 'user' not in seen['get'].lower()


def test_output_classifier_cache_key_is_answer_hash_only(monkeypatch):
    seen = _capture_cache_key(monkeypatch)
    a = 'Your next service is due in May 2026.'
    v._classify_answer_on_topic(a, 'http://x', {'CHAT_OUTPUT_CLASSIFIER_ENABLED': True})
    expected = 'chatans:' + hashlib.sha256(a.encode('utf-8')).hexdigest()
    assert seen['get'] == expected
    assert 'user' not in seen['get'].lower()


def test_cache_key_deterministic_and_distinct(monkeypatch):
    seen = _capture_cache_key(monkeypatch)
    v._classify_question('same question', 'http://x', {})
    k1 = seen['get']
    # Same text → same key; different text → different key.
    assert k1 == 'chatcls:' + hashlib.sha256(b'same question').hexdigest()
    assert k1 != 'chatcls:' + hashlib.sha256(b'different question').hexdigest()


def test_qhash_non_reversible_and_deterministic():
    q = 'some private question text'
    h = v._qhash(q)
    assert len(h) == 12 and all(c in '0123456789abcdef' for c in h)
    assert h == v._qhash(q)          # deterministic
    assert q not in h                # never contains the raw text
    assert v._qhash('a') != v._qhash('b')

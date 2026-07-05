"""Unit tests for the Layer 2 input pre-classifier (ALLOW/BLOCK gate).

See app/routes/vehicles.py (_classify_question). The Ollama call and model
resolution are monkeypatched so we test the decision + fail-open logic without
a network/Redis dependency.
"""

import app.routes.vehicles as v


def _no_cache(monkeypatch):
    # Bypass Redis cache so the decision path is exercised every time.
    monkeypatch.setattr(v, 'ai_cache_get', lambda *_a, **_k: None)
    monkeypatch.setattr(v, 'ai_cache_set', lambda *_a, **_k: None)


def test_allow_decision(monkeypatch):
    _no_cache(monkeypatch)
    monkeypatch.setattr(v, 'resolve_model', lambda *_a, **_k: 'tiny-model')
    monkeypatch.setattr(v, 'ollama_chat', lambda **_k: {'decision': 'ALLOW'})
    # Ambiguous phrasing (no obvious keyword) so the pre-filter doesn't bypass it.
    assert v._classify_question('is it due soon?', 'http://x', {}) == 'ALLOW'


def test_block_decision(monkeypatch):
    _no_cache(monkeypatch)
    monkeypatch.setattr(v, 'resolve_model', lambda *_a, **_k: 'tiny-model')
    monkeypatch.setattr(v, 'ollama_chat', lambda **_k: {'decision': 'BLOCK'})
    assert v._classify_question('write me a pasta recipe', 'http://x', {}) == 'BLOCK'


def test_no_model_configured_fails_open(monkeypatch):
    _no_cache(monkeypatch)
    monkeypatch.setattr(v, 'resolve_model', lambda *_a, **_k: '')
    # Should not even call the model.
    monkeypatch.setattr(v, 'ollama_chat', lambda **_k: (_ for _ in ()).throw(AssertionError('called')))
    assert v._classify_question('anything', 'http://x', {}) is None


def test_unexpected_output_fails_open(monkeypatch):
    _no_cache(monkeypatch)
    monkeypatch.setattr(v, 'resolve_model', lambda *_a, **_k: 'tiny-model')
    monkeypatch.setattr(v, 'ollama_chat', lambda **_k: {'decision': 'MAYBE'})
    assert v._classify_question('hello', 'http://x', {}) is None


def test_error_fail_open_true(app, monkeypatch):
    _no_cache(monkeypatch)
    monkeypatch.setattr(v, 'resolve_model', lambda *_a, **_k: 'tiny-model')

    def _boom(**_k):
        raise RuntimeError('timeout')
    monkeypatch.setattr(v, 'ollama_chat', _boom)
    with app.app_context():
        assert v._classify_question('x', 'http://x', {'CHAT_CLASSIFIER_FAIL_OPEN': True}) is None


def test_error_fail_closed(app, monkeypatch):
    _no_cache(monkeypatch)
    monkeypatch.setattr(v, 'resolve_model', lambda *_a, **_k: 'tiny-model')

    def _boom(**_k):
        raise RuntimeError('timeout')
    monkeypatch.setattr(v, 'ollama_chat', _boom)
    with app.app_context():
        assert v._classify_question('x', 'http://x', {'CHAT_CLASSIFIER_FAIL_OPEN': False}) == 'BLOCK'


def test_disabled_gate_skips_classifier(monkeypatch):
    _no_cache(monkeypatch)
    monkeypatch.setattr(v, 'resolve_model', lambda *_a, **_k: 'tiny-model')
    # Must not call the model when the gate is disabled via config.
    monkeypatch.setattr(v, 'ollama_chat', lambda **_k: (_ for _ in ()).throw(AssertionError('called')))
    assert v._classify_question('anything', 'http://x', {'CHAT_CLASSIFIER_ENABLED': False}) is None


def test_classifier_passes_tight_options(monkeypatch):
    _no_cache(monkeypatch)
    monkeypatch.setattr(v, 'resolve_model', lambda *_a, **_k: 'tiny-model')
    captured = {}

    def _capture(**kwargs):
        captured.update(kwargs)
        return {'decision': 'ALLOW'}
    monkeypatch.setattr(v, 'ollama_chat', _capture)

    v._classify_question('is it due soon?', 'http://x', {})
    opts = captured.get('options', {})
    assert opts.get('temperature') == 0       # deterministic
    assert opts.get('num_predict') == 16      # tight output cap (perf)
    assert captured.get('timeout') == 15      # CHAT_CLASSIFIER_TIMEOUT default (timeout invariant)


def test_cache_hit_short_circuits(monkeypatch):
    monkeypatch.setattr(v, 'resolve_model', lambda *_a, **_k: 'tiny-model')
    monkeypatch.setattr(v, 'ai_cache_get', lambda *_a, **_k: {'decision': 'BLOCK'})
    # Model must NOT be called on a cache hit.
    monkeypatch.setattr(v, 'ollama_chat', lambda **_k: (_ for _ in ()).throw(AssertionError('called')))
    assert v._classify_question('cached question', 'http://x', {}) == 'BLOCK'


def test_on_topic_question_bypasses_classifier(monkeypatch):
    """Clearly on-topic questions skip the classifier entirely (fail open to the
    main model) so a small classifier can never wrongly refuse them."""
    _no_cache(monkeypatch)
    monkeypatch.setattr(v, 'resolve_model', lambda *_a, **_k: 'tiny-model')
    # If the classifier were consulted it would BLOCK — the bypass must win.
    monkeypatch.setattr(v, 'ollama_chat', lambda **_k: {'decision': 'BLOCK'})
    for q in ('what engine is my car?', 'what year was my car built?',
              'what fuel do I use?', 'ce motor are mașina mea?',
              '¿qué motor tiene mi coche?'):
        assert v._classify_question(q, 'http://x', {}) is None


def test_on_topic_matches_vehicle_make_model(monkeypatch):
    """The vehicle's own make/model (passed as extra_terms) counts as on-topic."""
    _no_cache(monkeypatch)
    monkeypatch.setattr(v, 'resolve_model', lambda *_a, **_k: 'tiny-model')
    monkeypatch.setattr(v, 'ollama_chat', lambda **_k: {'decision': 'BLOCK'})
    assert v._classify_question('tell me about the Golf', 'http://x', {},
                                extra_terms=('Volkswagen', 'Golf', 'Daily')) is None


def test_looks_on_topic_helper():
    assert v._looks_on_topic('what engine is my car?')
    assert v._looks_on_topic('how do I log a fill-up?')
    assert not v._looks_on_topic('write me a pasta recipe')
    assert not v._looks_on_topic('')
    # Short extra terms (<3 chars) are ignored to avoid spurious matches.
    assert not v._looks_on_topic('ab cd', extra_terms=('a', 'b'))

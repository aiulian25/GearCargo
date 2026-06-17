"""Unit tests for the Layer 1 chat guardrail refusal detection.

See app/routes/vehicles.py (_normalize_refusal / _is_refusal / _CHAT_REFUSAL).
Pure functions — no app context needed.
"""

from app.routes.vehicles import _is_refusal, _normalize_refusal, _CHAT_REFUSAL

EN = _CHAT_REFUSAL['English']


def test_exact_refusal_detected():
    assert _is_refusal(EN, EN) is True


def test_quoted_or_padded_refusal_detected():
    assert _is_refusal(f'"{EN}"', EN) is True
    assert _is_refusal(EN + '  ', EN) is True


def test_prefix_refusal_detected():
    # Model may stop slightly early; the distinctive opening still counts.
    assert _is_refusal('Sorry, I can only help with your vehicles and their maintenance.', EN) is True


def test_normal_answer_not_flagged():
    assert _is_refusal('Your next service is due in May 2026.', EN) is False


def test_empty_inputs_not_flagged():
    assert _is_refusal('', EN) is False
    assert _is_refusal(EN, '') is False


def test_all_languages_have_a_refusal_string():
    for lang in ('English', 'Romanian', 'Spanish'):
        assert _CHAT_REFUSAL.get(lang)
        # Each detects itself.
        assert _is_refusal(_CHAT_REFUSAL[lang], _CHAT_REFUSAL[lang]) is True


def test_normalize_strips_punctuation_and_case():
    assert _normalize_refusal('Hello, WORLD!') == 'hello world'

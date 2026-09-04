"""Tests for R4-20 — the outbound probe budget of the owner's-manual lookup.

`get_manual_url` ran up to three OEM probes plus an aggregator probe, and each
probe was a HEAD *followed by a GET* on a 5 s timeout. On a cache miss with an
unresponsive OEM host that is ~40 s of wall clock held inside the request — on
a sync gunicorn worker (`gunicorn.conf.py:14`), that is one worker blocked for
the whole chain.

The ceiling is now two single-HEAD probes on a 2 s timeout: ~4 s worst case.
"""

import pytest
import requests

import app.services.manual_service as manual_service


class _Response:
    def __init__(self, status_code):
        self.status_code = status_code

    def close(self):
        pass


@pytest.fixture(autouse=True)
def _no_redis(monkeypatch):
    """Keep the lookup entirely in-process — no cache hits, no cache writes."""
    monkeypatch.setattr(manual_service, '_get_redis', lambda: None)


@pytest.fixture
def head_calls(monkeypatch):
    """Record every HEAD, and fail loudly if the code ever falls back to GET."""
    calls = []

    def _head(url, **kwargs):
        calls.append({'url': url, **kwargs})
        return _Response(404)

    def _get(url, **kwargs):
        raise AssertionError(f'GET fallback should have been dropped: {url}')

    monkeypatch.setattr(requests, 'head', _head)
    monkeypatch.setattr(requests, 'get', _get)
    return calls


def test_lookup_makes_at_most_two_probes_and_returns_the_search_fallback(head_calls):
    result = manual_service.get_manual_url('nissan', 'qashqai', 2019, 'en')

    assert len(head_calls) <= 2, [call['url'] for call in head_calls]
    assert result['manual_url'] is None
    assert result['source'] is None
    assert result['fallback_search']
    assert 'qashqai' in result['fallback_search'].lower()


def test_every_probe_uses_the_two_second_timeout(head_calls):
    manual_service.get_manual_url('nissan', 'qashqai', 2019, 'en')

    assert head_calls, 'expected at least one probe'
    for call in head_calls:
        assert call['timeout'] == manual_service._PROBE_TIMEOUT == 2


def test_the_first_probe_is_the_most_specific_oem_template(head_calls):
    manual_service.get_manual_url('nissan', 'qashqai', 2019, 'en')

    # The year-specific template, not the generic manuals landing page.
    assert '2019' in head_calls[0]['url']
    assert 'qashqai' in head_calls[0]['url']


def test_a_reachable_oem_url_stops_after_one_probe(monkeypatch):
    calls = []
    monkeypatch.setattr(requests, 'head',
                        lambda url, **kwargs: calls.append(url) or _Response(200))

    result = manual_service.get_manual_url('nissan', 'qashqai', 2019, 'en')

    assert len(calls) == 1
    assert result['source'] == 'oem'
    assert result['manual_url'] == calls[0]
    assert result['fallback_search']          # always offered alongside


def test_head_not_allowed_counts_as_reachable(monkeypatch):
    """405 means the server refuses HEAD, not that the page is missing."""
    monkeypatch.setattr(requests, 'head', lambda url, **kwargs: _Response(405))

    assert manual_service._url_reachable('https://example.test/manual') is True


@pytest.mark.parametrize('status_code, reachable', [
    (200, True),
    (301, True),
    (404, False),
    (410, False),
    (500, False),
])
def test_reachability_by_status_code(monkeypatch, status_code, reachable):
    monkeypatch.setattr(requests, 'head', lambda url, **kwargs: _Response(status_code))

    assert manual_service._url_reachable('https://example.test/manual') is reachable


def test_a_network_failure_is_not_reachable_and_never_raises(monkeypatch):
    def _boom(url, **kwargs):
        raise requests.ConnectionError('host unreachable')

    monkeypatch.setattr(requests, 'head', _boom)

    assert manual_service._url_reachable('https://example.test/manual') is False


def test_an_unknown_make_probes_only_the_aggregator(head_calls):
    """No OEM templates for this make — the budget is not spent guessing."""
    result = manual_service.get_manual_url('wuling', 'hongguang', 2019, 'en')

    assert len(head_calls) == len(manual_service.AGGREGATOR_TEMPLATES)
    assert result['manual_url'] is None
    assert result['fallback_search']


def test_the_aggregator_is_probed_when_the_oem_url_is_dead(head_calls):
    manual_service.get_manual_url('nissan', 'qashqai', 2019, 'en')

    probed = ' '.join(call['url'] for call in head_calls)
    assert 'nissan' in probed
    assert 'carmans.net' in probed

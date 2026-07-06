"""The public /api/config endpoint exposes ai_enabled so the SPA can gate the
AI assistant entry points on whether an Ollama integration exists."""


def _get_ai_enabled(client):
    return client.get('/api/config').get_json().get('ai_enabled')


def test_ai_disabled_when_flag_off(app, client):
    # Ollama turned off → assistant hidden regardless of a URL being present.
    app.config['OLLAMA_ENABLED'] = False
    assert _get_ai_enabled(client) is False


def test_ai_enabled_requires_both_flag_and_url(app, client):
    # Flag on but no URL → still not usable, so still False.
    app.config['OLLAMA_ENABLED'] = True
    app.config['OLLAMA_URL'] = None
    app.config['OLLAMA_BASE_URL'] = None
    assert _get_ai_enabled(client) is False

    # Flag on AND a URL → enabled.
    app.config['OLLAMA_URL'] = 'http://host.docker.internal:11434'
    assert _get_ai_enabled(client) is True

    # Flag off with a URL present → disabled.
    app.config['OLLAMA_ENABLED'] = False
    assert _get_ai_enabled(client) is False

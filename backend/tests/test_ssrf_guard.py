"""Unit tests for the Ollama SSRF guard (the single authoritative URL validator).

See app/services/ollama.validate_ollama_url. These are pure-function tests — no
app context, DB or network required.
"""

import pytest

from app.services.ollama import validate_ollama_url


@pytest.mark.parametrize("url", [
    "http://localhost:11434",
    "http://127.0.0.1:11434",
    "https://ollama.example.com",
    "http://192.168.1.50:11434",   # RFC-1918 LAN
    "http://10.0.0.5:11434",       # RFC-1918 LAN
    "http://172.16.5.5:11434",     # RFC-1918 LAN
    "http://host.docker.internal:11434",  # hostname — resolved at request time
])
def test_allows_safe_urls(url):
    assert validate_ollama_url(url) == url


@pytest.mark.parametrize("url", [
    "",                                         # not configured
    "ftp://localhost:11434",                    # non-http(s) scheme
    "ollama.example.com",                       # missing scheme
    "http://",                                  # missing host
    "http://user:pass@ollama.example.com",      # embedded credentials
    "http://169.254.169.254/latest/meta-data/", # link-local cloud metadata
    "http://100.64.0.1:11434",                  # CGNAT / cloud shared space
])
def test_blocks_dangerous_urls(url):
    with pytest.raises(ValueError):
        validate_ollama_url(url)


def test_metadata_endpoint_is_blocked_specifically():
    # The canonical cloud metadata IP must never be reachable.
    with pytest.raises(ValueError) as exc:
        validate_ollama_url("http://169.254.169.254")
    assert "blocked IP range" in str(exc.value) or "host" in str(exc.value).lower()

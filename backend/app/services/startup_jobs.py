"""Maintenance formerly launched by every application factory.

The scheduler probes providers; OCR recovery only admits bounded durable work.
"""
from app.services.restore_transaction import guarded_app_context


def probe_ollama(app):
    with guarded_app_context(app):
        try:
            from app.services.ollama import (
                validate_ollama_url,
                ollama_record_success,
                ollama_record_failure,
            )
            import requests as _req
            base_url = app.config.get('OLLAMA_BASE_URL', '')
            validated = validate_ollama_url(base_url)
            # §14.2 — the prompt carries user vehicle data. Warn (once, at
            # startup) if it would cross the network in cleartext to a
            # PUBLIC IP. http to loopback/LAN/private DNS is fine; a public
            # IP over http is a real data-in-transit exposure.
            try:
                from urllib.parse import urlparse as _urlparse
                import ipaddress as _ipaddr
                _p = _urlparse(validated)
                if _p.scheme == 'http' and _p.hostname:
                    try:
                        if _ipaddr.ip_address(_p.hostname).is_global:
                            app.logger.warning(
                                '§14.2: OLLAMA_BASE_URL uses plain http to a public IP (%s) — '
                                'user data crosses the network in cleartext. Use https + a '
                                'private network/VPN, or firewall Ollama to the backend only.',
                                _p.hostname,
                            )
                    except ValueError:
                        pass  # hostname (not an IP literal) — can't classify; rely on operator + docs
            except Exception:
                pass
            resp = _req.get(f'{validated.rstrip("/")}/api/tags', timeout=5)
            if resp.status_code == 200:
                ollama_record_success()
                app.logger.info('Startup Ollama probe: reachable — offline marker cleared.')
            else:
                ollama_record_failure()
                app.logger.warning(
                    f'Startup Ollama probe: HTTP {resp.status_code} — marked offline.'
                )
        except Exception as exc:
            try:
                ollama_record_failure()
            except Exception:
                pass
            app.logger.warning(f'Startup Ollama probe: unreachable — {exc}')


def backfill_ocr(app):
    """Admit a bounded page of legacy image/PDF work; workers own execution."""
    from app.services.ocr_queue import backfill
    with guarded_app_context(app):
        backfill()

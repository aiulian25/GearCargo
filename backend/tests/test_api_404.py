"""Regression tests for M3: API 404s must be JSON, not the SPA shell with 200.

The 404 handler branched on `'/api/' in str(e)`, but str(e) is Werkzeug's
description ("404 Not Found: The requested URL…") which never contains '/api/'.
So a `get_or_404` miss on a REAL API route (e.g. admin users) returned
index.html with HTTP 200 — an invisible error for API consumers. The handler now
branches on request.path.
"""

from app import db
from app.models import User


def _admin(email="adm404@example.com"):
    u = User(username=email.split("@")[0], email=email, is_active=True, is_admin=True)
    u.set_password("StrongPass123!")
    db.session.add(u)
    db.session.commit()
    return u


def test_api_get_or_404_returns_json_not_html(app, client, auth_headers):
    """An admin get_or_404 miss returns a JSON 404 (was HTML 200)."""
    with app.app_context():
        aid = _admin().id

    resp = client.get("/api/admin/users/999999", headers=auth_headers(aid, is_admin=True))
    assert resp.status_code == 404, (resp.status_code, resp.data[:120])
    assert resp.is_json, resp.content_type
    assert resp.get_json() == {"error": "Not found"}
    # Must NOT be the SPA shell.
    assert b"<!doctype html" not in resp.data.lower()


def test_unknown_non_api_route_still_serves_spa_shell(app, client):
    """Client-side routes still get index.html — the SPA fallback is intact."""
    resp = client.get("/some/client/side/route")
    assert resp.status_code == 200
    assert b"<!doctype html" in resp.data.lower() or b"<html" in resp.data.lower()

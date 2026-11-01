# Browser mutation protection (GC-012)

Cookie-authenticated API mutations require both a trusted browser source and a signed, expiring CSRF token bound to the Flask session. This includes login, registration, logout, refresh, record changes and uploads. HttpOnly and SameSite=Strict auth cookies remain enabled. Same-site sibling hosts are different origins and are not automatically trusted.

## Deployment origins

`CSRF_TRUSTED_ORIGINS` is a comma-separated list of exact browser origins (scheme, hostname and port). When empty, only `APP_URL` is trusted. An explicitly configured list replaces that default. Origins have no paths, credentials or wildcards; invalid configuration fails startup. Default HTTP/HTTPS ports are normalized. Examples:

```dotenv
# Single public HTTPS origin; leave the extra setting empty.
APP_URL=https://cars.example.com
CSRF_TRUSTED_ORIGINS=

# Alternatively, list every deliberately trusted entry point.
CSRF_TRUSTED_ORIGINS=https://cars.example.com,https://admin.example.com

# Local Vite development: the browser is on port 3000, even though the
# development proxy forwards API requests to port 5000.
CSRF_TRUSTED_ORIGINS=http://localhost:3000,http://localhost:5000

# LAN example: include the actual public port, not the container port.
CSRF_TRUSTED_ORIGINS=http://192.168.1.10:8080
```

Set `APP_URL` to the actual external origin for a single-origin LAN installation. Keep the existing HTTP development cookie override only for HTTP installations; production HTTPS should retain Secure cookies. Keep `WTF_CSRF_ENABLED=true` outside isolated tests. A working shared Flask session store (Redis in the default deployment), consistent `SECRET_KEY` / `WTF_CSRF_SECRET_KEY` across workers, and session cookies are required. Losing the session store invalidates proof and fails closed.

The allowlist is independent of `CORS_ORIGINS`. CORS response-read permission does not authorize a mutation. Preserve browser `Origin`, `Referer` and `Sec-Fetch-Site` through your proxy; never replace them with the application's trusted origin. `Host`, `Forwarded` and `X-Forwarded-*` do not determine CSRF trust. `TRUSTED_PROXY_COUNT` continues to serve its existing purpose. This custom boundary uses configured origins instead of Flask-WTF's request-host-based SSL Referer check, so `WTF_CSRF_SSL_STRICT` is not an override for API origin enforcement.

## Request contract

1. Fetch `GET /api/auth/csrf-token` with same-origin credentials and `cache: no-store`. `/api/csrf-token` remains an alias. Both return `{ "csrf_token": "..." }` with `Cache-Control: no-store`. They work before authentication and reject untrusted browser sources.
2. Send the value in `X-CSRF-Token` on unsafe API requests. The session cookie must accompany it. A token from another session, an expired token, a missing token, and a forged token fail with HTTP 403 / `CSRF_INVALID` before the mutation executes.
3. A supplied `Origin` must match the configured allowlist. `Origin: null` fails. If Origin is absent, a supplied Referer must match. If both are absent, valid session proof is still mandatory; `Sec-Fetch-Site: same-site` without a verifiable source is rejected. `cross-site` is rejected even with a trusted Origin header. Untrusted-source failures return HTTP 403 / `CSRF_ORIGIN_REJECTED` and are not retried automatically.
4. GET, HEAD and OPTIONS remain safe/preflight methods. A successful OPTIONS response does not exempt the later mutation. Simple forms cannot supply the required custom proof header. The exact `/api/csp-report` endpoint remains an anonymous, rate-limited log sink: browser-generated reports cannot attach custom headers, and this route never uses cookie authentication to change user data.

The existing Talisman middleware sets the separate Flask session cookie to SameSite=Lax; auth cookies remain hardcoded Strict. The session token and source checks do not rely on either cookie policy alone. This task does not change that existing middleware setting.

Successful credential issuance (login, registration and refresh) and logout invalidate previous proof. The application obtains fresh proof before each mutation; concurrent token reads within one client share an in-flight request. One explicit `CSRF_INVALID` response may trigger a fresh-token retry. Origin failures do not trigger retries or sign-out. Request bodies, operation IDs, record revisions and captured offline ownership remain unchanged across retries.

Non-browser clients using `Authorization: Bearer ...` remain supported without Origin, Fetch Metadata or CSRF headers on routes that authenticate that credential. Send no auth cookies: cookie authentication takes precedence, so adding a Bearer header to a cookie request cannot bypass proof. API-key-only routes authenticate `X-API-Key` independently. Adding that header to a cookie-protected route, such as API-key generation/revocation, does not exempt it. The explicit JSON `refresh_token` fallback remains supported when auth cookies are absent. Password-login automation using cookies should first obtain CSRF proof and retain its session cookie.

## Offline writes and updates

Tokens never enter durable request headers, IndexedDB, localStorage or worker caches. Eligible record writes still reach the durable queue if token bootstrap fails because the network is unavailable. The worker obtains fresh proof before replaying records, receipt uploads/links and push subscription updates. A failed proof fetch leaves the queued work available for retry. Existing owner checks and idempotency remain in force.

Deploy the application, worker and backend together and reload open tabs online. The auth-path bootstrap alias bypasses the older worker's private-data guard. Older clients that never send proof fail closed; older queued work must be resumed through the updated worker. Do not clear browser storage to update, since it may contain unsent records and receipt files. For a staged deployment, first expose token bootstrap and distribute the updated client/worker before enabling the enforcing backend; never leave protection disabled as the final deployment. Rolling back the enforcing backend restores the original vulnerability.

## Validation

From `backend`, run `python -m pytest -q tests/test_cookie_csrf.py tests/test_offline_identity.py tests/test_mutation_retries.py`; run the complete suite on SQLite and PostgreSQL as in CI. The focused tests explicitly enable CSRF even though the general test configuration disables it. They cover forged, expired, session-mismatched and rotated tokens; trusted, sibling and cross-site origins; absent headers; malformed allowlists; proxy-header spoofing; login/logout/refresh; Bearer and API-key compatibility; and preflight/form behavior.

From `frontend`, run `npm test`, `npm run lint` and `npm run build`. `csrf.test.js`, `mutationTransport.test.js` and `apiInterceptor.test.js` cover fresh proof, bounded retries, unchanged operation identity, bootstrap outages, account changes during token acquisition, cache exclusions and refresh errors.

`frontend/browser-tests/cookieCsrf.mjs` runs eight acceptance scenarios using real Chromium cookies, Fetch Metadata, the built service worker and the real authentication client. Start the disposable `backend/tests/browser_queue_fixture.py` with `GC_BROWSER_QUEUE_TEST=1`, `GC_BROWSER_CSRF_TEST=1` and `CSRF_TRUSTED_ORIGINS=http://cars.gearcargo.test:51912`. Bind its Gunicorn listener to a Unix socket. Set `GC_FRONTEND` to the built frontend, `GC_BACKEND_SOCKET` to the socket, and optionally `GC_BROWSER_OUTPUT`, `PLAYWRIGHT_MODULE` and `GC_CHROMIUM`; run `node frontend/browser-tests/cookieCsrf.mjs` from the repository root. The runner binds loopback port 51912 and resolves only test hosts locally. Its secure-context flag is solely for testing the worker over local HTTP; it does not disable SameSite or CORS. Observations record cookie/proof presence, never credential values. Never load this fixture in production.

The design uses Flask-WTF's synchronizer token with explicit credential and origin checks, following the [Flask-WTF CSRF documentation](https://flask-wtf.readthedocs.io/en/1.2.x/csrf/) and [OWASP CSRF guidance](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).

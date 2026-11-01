# Authentication token purposes (GC-013)

GearCargo issues two JWT credentials for each sign-in session. Both must have a valid HS256 signature and satisfy the existing expiry, user and server-side session checks. Their payload `type` claim determines where they may be used:

| Credential | Required payload claim | Accepted use |
|---|---|---|
| Access token | `"type": "access"` | Ordinary authenticated API routes, admin routes and authenticated attachment views/downloads. Accepted through the `access_token` cookie or the existing Bearer-header fallback. |
| Refresh token | `"type": "refresh"` | `/api/auth/refresh`, through its scoped cookie or existing explicit JSON-body fallback. It cannot authenticate a data or media API. |
| Calendar feed token | `"type": "calendar_feed"` | The dedicated calendar-feed endpoint, with its existing feed-secret and revocation checks. It cannot authenticate ordinary APIs or refresh a session. |

Missing, null, unknown and incorrectly typed purpose claims are rejected; neither the cookie name nor a valid signature establishes a token's purpose. Wrong-purpose ordinary API credentials return HTTP 401 with the existing generic `Invalid token` error. The refresh endpoint retains its explicit `Invalid token type` error. Credential precedence, domain policy, permissions, session revocation and the absolute session deadline are unchanged. The AI request limiter uses the same access-token decoder when choosing a user bucket; non-access credentials fall back to the IP bucket and still fail API authentication.

Signed attachment and upload URLs remain separate HMAC capabilities bound to their existing resource/expiry rules. The application does not reintroduce JWT query-string authentication. `/uploads/<path>` already requires a valid upload signature; passing an access or refresh JWT does not replace it. Authenticated attachment views apply the access-purpose check before reading a file. Logout's internal decode runs only after the ordinary access decorator has authenticated the request.

## Upgrade behavior

Access JWTs issued before GC-013 have no `type` claim. They are rejected immediately after the enforcing backend is deployed; there is no compatibility period that accepts ambiguous credentials. Existing refresh JWTs already carry `type=refresh`, so a valid, unrevoked session may renew through `/api/auth/refresh` and receive a typed access token. A browser that reaches a normal API 401 can use its existing silent-refresh flow. If renewal is unavailable, or the user is on a sign-in page where automatic refresh is intentionally suppressed, sign in again. Non-browser clients should explicitly refresh or reauthenticate on 401.

Refresh still generates a new session identifier, revokes the old pair, preserves the original absolute expiry and preserves the offline identity generation. Old access/refresh credentials remain invalid after rotation. No database migration, key rotation, client-side token storage or frontend change is required.

Update backend instances together: an older instance would continue accepting untyped or wrong-purpose credentials. Rolling back the enforcing code restores the original vulnerability.

## Validation

From `backend`:

```bash
python -m pytest -q tests/test_token_purpose.py tests/test_token_refresh.py tests/test_signed_urls.py tests/test_cookie_csrf.py tests/test_offline_identity.py tests/test_calendar_feed.py tests/test_calendar_feed_revocation.py
```

`test_token_purpose.py` uses real signed tokens, live database sessions and real temporary media files. It covers Cookie and Bearer access to ordinary/admin/media routes; refresh, missing, unknown and malformed purposes; valid access; expired and revoked sessions; signature rejection; refresh rotation and legacy-session renewal; and signed media compatibility. The shared API test fixture now explicitly mints access-purpose credentials instead of relying on the legacy ambiguity. CI also runs the complete backend suite on SQLite and PostgreSQL.

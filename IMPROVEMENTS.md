# GearCargo — Improvements & Recommendations

> Based on a full read of the codebase (Flask backend + React/Vite PWA frontend).
> The project is **already very well hardened** — there is an extensive trail of
> prior security work (the `S##` and `I##` annotations throughout the code), field
> encryption, CSP via Talisman, rate limiting, ProxyFix, signed media URLs, 2FA,
> account/IP/device lockout, SSRF guards on Ollama, and httpOnly-cookie JWTs.
>
> This document lists what remains: residual security concerns, UI/UX improvements,
> and feature ideas. Items are grouped and tagged with a rough priority:
> **[High] / [Med] / [Low]**.

---

## 1. Security Concerns

### 1.1 Authentication & Sessions

- **[High] ✅ RESOLVED (S01) — Session validation no longer fails *open* when Redis is down.**
  ~~`validate_session()` returned `True` when Redis was unreachable, silently
  disabling single-device enforcement, the 48h wall, and logout revocation.~~

  **Fix:** added a durable **DB-backed session mirror** (`user_sessions` table /
  `UserSession` model), mirroring the existing DB account-lockout fallback
  pattern. Redis stays the fast path; when it is unavailable the auth layer now
  validates against the DB and **fails CLOSED** (a missing/revoked/expired row is
  rejected) instead of open. Specifically:
    - `create_session()` dual-writes to Redis **and** the DB on every login/refresh.
    - `validate_session()` / `get_session_data()` fall back to the DB on Redis
      error or absence, enforcing the 48h absolute-expiry wall durably.
    - `logout` and `invalidate_user_sessions()` revoke the DB row regardless of
      Redis, so revocation/single-device hold across a Redis outage.
    - A throttled WARNING (max 1/5 min) surfaces the degraded state in logs;
      `/health` still reports `redis_ok`.
    - Expired/revoked rows are pruned opportunistically on write and by the daily
      `cleanup_old_data` job, keeping the table bounded.
    - **Usability preserved:** no spurious logouts on a Redis blip (the durable
      mirror keeps valid sessions valid); no new user-facing strings, so no i18n
      changes were required. Migration: `k9l0m1n2o3p4_add_user_sessions_table`.

- **[Med] ✅ RESOLVED (S03) — Account enumeration on registration hardened.**
  ~~`POST /register` returned `409 "Email already registered"`.~~
  **Fix:** password-strength validation now runs **before** any account-existence
  lookup (so feedback never depends on whether the email exists), and the
  "already exists" branch burns an equivalent bcrypt cost to **equalise response
  timing** with the create path. Note: in production this branch is already
  unreachable — public signup is closed once an admin exists (returns a generic
  403), so registration is only open during first-run bootstrap when there are no
  accounts to enumerate. The timing/ordering hardening covers the bootstrap window
  and the admin-demotion edge case. No user-facing string change.

- **[Med] ✅ RESOLVED (S02) — bcrypt 72-byte truncation handled.**
  ~~Flask-Bcrypt silently truncated passwords beyond 72 bytes.~~
  **Fix:** `User.set_password`/`check_password` now SHA-256 pre-hash the password
  (base64 → fixed 44-char ASCII, NUL-free) before bcrypt — the `bcrypt_sha256`
  construction. `check_password` verifies the new scheme first and **transparently
  upgrades** legacy (pre-S02) raw-bcrypt hashes on the next successful login, so
  existing users are unaffected. Verified: two passwords differing only past byte
  72 now hash differently and don't cross-validate.

- **[Low] ✅ RESOLVED (S03) — Password policy strengthened & enforced everywhere.**
  ~~Only `< 8 chars` / common / HIBP `>100` were enforced.~~
  **Fix:** minimum length raised to **12** (`MIN_PASSWORD_LENGTH`, single source of
  truth) and the **full policy is now enforced server-side on every password-setting
  path** — register (previously length-only), both reset flows, change-password,
  admin user-create (length), and the admin bootstrap. Common-list and HIBP-breach
  blocking are retained. Frontend validators + i18n (en/ro/es) updated to 12;
  existing users keep their current password until they next change it.

- **[Low] ✅ RESOLVED (S04) — Device fingerprint stabilised.**
  ~~`get_device_fingerprint()` hashed only the raw UA, firing false "new device"
  alerts on every browser update.~~
  **Fix:** it now hashes a **normalised signature** (browser family + OS family +
  device type + primary `Accept-Language`), excluding version numbers, so updates
  no longer churn the fingerprint. Documented explicitly as an alert-signal
  heuristic, **not** an auth factor. (One-time consequence: existing stored
  fingerprints differ from the new scheme, so each user may see a single
  "new device" alert after deploy.)

### 1.2 Secrets & Configuration

- **[High] ✅ RESOLVED (S05) — Secret validation now fails SAFE, independent of `DEBUG`.**
  ~~The guard only ran when `DEBUG` was false, so `DEBUG=true` in production could
  start with default secrets.~~
  **Fix:** enforcement is now gated on an explicit `FLASK_ENV` signal and defaults
  to ON — anything that is **not** `FLASK_ENV=development`/`dev`/`local` (and not
  the testing config) is treated as production and must supply real secrets, so a
  stray `DEBUG=true` can no longer bypass it. Detection was also broadened from the
  3 hardcoded defaults to a `_is_weak_secret()` check that rejects **empty, default,
  or placeholder** values (catches the `CHANGE_ME_*` / `change-this-*` markers from
  the `.env` templates) for all four keys including `ENCRYPTION_KEY`; distinct-key
  reuse and short secrets produce warnings. Verified: prod+placeholders refuses to
  start, dev bypasses, prod+real-secrets starts (200 random hex secrets, 0 false
  positives). Documented loudly in README + `.env*`.

- **[Med] ✅ RESOLVED (S06) — `ENCRYPTION_KEY` now uses HKDF, is versioned, and is rotatable.**
  ~~`base64(sha256(key_seed))` with no versioning made rotation impossible.~~
  **Fix:** `encryption.py` now derives keys via **HKDF-SHA256**, tags new ciphertext
  with a `v2:` prefix, and decrypts via **`MultiFernet`** across the primary key plus
  any `ENCRYPTION_KEYS_OLD` (decrypt-only) — enabling **zero-downtime rotation**.
  Legacy pre-S06 ciphertext (unprefixed SHA-256) still decrypts, so the upgrade
  needs **no migration**. The duplicate SHA-256 derivation in `calendar_service.py`
  (CalDAV creds) was removed and now delegates to the shared module, so all PII
  shares one scheme. Added `scripts/reencrypt_pii.py` (dry-run by default) for bulk
  re-encryption / rotation, documented in README. Verified: v2 round-trip, legacy
  decrypt, full rotation (old→new with old-key removal isolation), and CalDAV
  round-trip incl. plaintext fallback.

- **[Low] ✅ VERIFIED — tracked `.env*` files contain no real secrets.**
  `.env.example` / `.env.production` / `.env.simple` hold only `CHANGE_ME_*` /
  `change-this-*` placeholders. Added explicit guidance in each (generate distinct
  values; `FLASK_ENV=development` to bypass locally; `ENCRYPTION_KEYS_OLD` rotation
  note) and the startup guard now actively rejects those placeholders in production.

### 1.3 SSRF / External Requests

- **[Med] ✅ ADDRESSED (S08) — Ollama URL is env-only; admin AI changes are audit-logged.**
  Investigation confirmed the Ollama **URL is not runtime-settable** — it comes
  only from the `OLLAMA_BASE_URL` environment variable (operator-controlled), and
  every outbound call already passes through `validate_ollama_url()` (the single
  SSRF guard). The admin `/settings` PUT only changes validated model *names*
  (regex-checked), so there is no API surface to point Ollama at an arbitrary host.
  **Fix:** the admin AI-config mutations (`/settings` PUT model changes and the AI
  cache flush) are now **audit-logged** via `ActivityLog` (`ai_settings_updated`
  with from→to diffs, and `ai_cache_flushed`), recording the admin who made the
  change; both are surfaced in the admin System Logs UI. Endpoints remain
  `@admin_required`. Documented the env-only URL constraint in the endpoint docstring.

- **[Low] ✅ RESOLVED (S07) — `detect_country_from_coords()` no longer f-strings the URL.**
  **Fix:** the Nominatim reverse-geocode call now passes `params={'lat','lon','format'}`
  to `requests.get` instead of interpolating the URL, so query encoding is
  correct-by-construction and no caller can ever inject into the URL. Verified the
  call sends a bare base URL + params dict and still parses the country code.

### 1.4 CORS / Headers

- **[Low] ✅ RESOLVED (S09) — Widget CORS now supports a proper allowlist + warns on `*`.**
  ~~`WIDGET_CORS_ORIGINS` was set verbatim as the ACAO header (which is invalid for
  multi-origin values) and defaulted to `*` silently.~~
  **Fix:** the widget WSGI middleware now treats `WIDGET_CORS_ORIGINS` as a real
  allowlist — comma/space-separated origins are parsed, and for each request the
  middleware **echoes back the request `Origin` only if it is in the allowlist**
  (with `Vary: Origin`), emitting no ACAO header otherwise. `*` still works
  (backward-compatible) but now logs a **startup warning**. Server-side callers
  (Gethomepage) send no `Origin` and don't enforce CORS, so they keep working in
  either mode. The sample `.env*` now lead with an explicit allowlist and mark `*`
  as a warned fallback. Verified end-to-end: allowed origin echoed, disallowed
  origin blocked, no-Origin server-side call still returns data, CSP/X-Frame
  stripping preserved.

- **[Low] ⏸️ ACCEPTED / DEFERRED — `style-src 'unsafe-inline'` cannot be dropped without breaking the UI.**
  recharts, react-hot-toast and react-spring inject inline styles at runtime via
  the CSSOM (`element.style`, `CSSStyleSheet.insertRule()`), which **cannot** be
  nonce- or hash-tagged (and adding a nonce would make CSP3 browsers *ignore*
  `'unsafe-inline'`, breaking them). Removing it would break charts, toasts and
  animations, so it stays — a documented, accepted trade-off, **not** a regression.
  **Containment already in place:** `'unsafe-inline'` applies only to `style-src`
  (style injection, a low-severity vector) — `script-src` remains strict
  (no `unsafe-inline`, hash-pinned, I04) and CSP violations are reported to
  `/api/csp-report` (S27). Genuinely dropping it requires upstream library changes
  and is tracked as a future item.

### 1.5 Resource & DoS

- **[Med] ✅ RESOLVED (S10) — `external.py` cache is now bounded + cross-worker.**
  ~~A plain module-level dict keyed by rounded lat/lon grew without eviction
  (memory leak) and was per-worker (inconsistent).~~
  **Fix:** `get_cached` is now backed by **Redis** (shared across workers, evicted
  by TTL) with a **bounded in-process LRU+TTL fallback** (`OrderedDict`, hard cap
  256 entries) used only when Redis is unavailable. Values are retained up to 24 h
  so the original stale-on-error resilience is preserved, while freshness is judged
  against the caller's `cache_duration` via an embedded timestamp. Verified:
  bounded eviction (50 distinct keys → stays at cap), stale-on-error, miss→None,
  and Redis round-trip.

- **[Med] ✅ RESOLVED (S11) — per-route upload ceilings reject oversized bodies early.**
  ~~The 200 MB global cap let attachment/avatar/photo routes (2–10 MB) buffer up to
  200 MB before the in-view size check.~~
  **Fix:** a `before_request` hook enforces per-endpoint limits
  (attachment/photo 10 MB, avatar 2 MB, +1 MB multipart overhead) using the
  `Content-Length` header and returns **413 before the body is buffered**. The
  global `MAX_CONTENT_LENGTH` is intentionally kept high — it is the ceiling for
  `/api/backup/import` (a full backup ZIP can legitimately be large), which is why
  a blanket lower cap was rejected. Verified: 12 MB→413, 5 MB→passes to auth,
  avatar 4 MB→413. Normal users get a localized client-side check (`receipt.tooLarge`,
  translated en/ro/es) before upload; the 413 is a defense-in-depth backstop.

- **[Low] ✅ RESOLVED (S12 → Q03) — OCR concurrency configurable; opt-in RQ queue now available.**
  ~~Introducing RQ/Celery means a new worker process + dependency + changes across
  all six compose files — disproportionate and deployment-risky for a [Low] item,
  so it is deferred.~~ **Now delivered as an opt-in abstraction (see §5 "Move heavy
  background work to a real queue", Q03):** `enqueue_task()` with a `thread`
  default (unchanged behaviour) and an `rq` backend on the existing Redis, run by
  `rq_worker.py`. No compose file was modified; operators add a worker service
  only when they set `TASK_QUEUE_BACKEND=rq`.
  **Also (low-risk, since S12):** the OCR concurrency cap is configurable via
  `OCR_MAX_CONCURRENCY` (default 2); the single shared semaphore still bounds all
  OCR code paths in both backends.

### 1.6 Dependencies

- **[Med] ✅ RESOLVED (S13) — Source-dependency scanning + Dependabot added, and the surfaced CVEs remediated where non-breaking.**
  ~~No lockfile/SBOM and no automated CVE scan for source deps.~~
  **Scanning infrastructure added:**
    - `.github/workflows/dependency-audit.yml` — runs `pip-audit` (backend) and
      `npm audit --audit-level=high` (frontend) on dependency-manifest changes,
      on a **weekly cron** (catches CVEs disclosed after code freezes), and on
      manual dispatch.
    - `.github/dependabot.yml` — weekly update PRs for pip, npm, Docker and
      GitHub-Actions ecosystems (minor/patch grouped; majors individual).
    - `Makefile` targets `make audit` / `audit-py` / `audit-js` for local parity
      (the CI workflow installs `pip-audit` itself; `requirements-dev.txt` is
      gitignored, so the targets/workflow are self-contained). Complements the
      existing image-level Trivy/Grype/Syft targets.
  **Remediation done now (non-breaking, build verified):** `npm audit fix` took
  the frontend from **26 vulns (1 critical, 13 high)** → **3** — resolving the
  critical `jspdf` and all `axios` highs (axios 1.13→1.18, jspdf 4.0→4.2.1,
  dompurify→3.4.11), all within existing semver ranges (only `package-lock.json`
  changed). `npm run build` passes and the PWA service worker still generates.
  **On "pinning":** the backend's `~=MAJOR.MINOR` ranges are an intentional,
  documented choice (auto-absorb security patches); the frontend is already
  lockfile-pinned (`package-lock.json`). Rather than freeze the backend (which
  would defeat auto-patching and risks the Docker build), we keep ranges + add
  scanning. SBOM is already covered by `make sbom` (Syft).
  **Flagged for deliberate (major) upgrade — now tracked by Dependabot/CI, not
  blind-bumped here:**
    - Frontend `esbuild`/`vite`/`vite-plugin-pwa` (3 remaining advisories) — needs
      breaking **vite 8**; these are **dev/build-time only** (e.g. the esbuild dev-server
      advisory) and are not shipped to users.
    - Backend `Flask-Cors 5→6` (CVE-2024-6839/6844/6866, CORS path matching) and
      `cryptography 46→48` (GHSA-537c-gmf6-5ccf, bundled OpenSSL). Both are
      **major** bumps outside the current ranges that require a container rebuild +
      the S06 encryption test pass to validate, so they are left for a reviewed
      Dependabot PR. Practical exposure is limited: app CORS uses an explicit
      `CORS_ORIGINS` allowlist with httpOnly+SameSite=Strict cookies and CSRF.

---

## 2. UI / UX Improvements

- **[High] ✅ RESOLVED (S14) — Route-level code splitting added.**
  ~~`App.jsx` eagerly imported all ~50 pages into one ~1.7 MB bundle.~~
  **Fix:** every page is now loaded via `React.lazy()` + `import()`, so each ships
  as its own on-demand chunk; layouts/PWA/contexts stay eager (app shell). Two
  `<Suspense>` boundaries: a fullscreen one around `<Routes>` (auth/standalone
  pages) and one **inside `AppLayout` around `<Outlet>`** so the header + bottom
  nav stay visible while an in-app page chunk loads. Fallback is a new accessible
  `PageLoader` (spinner with `role="status"` + translated `aria-label`
  `common.loading`, already in en/ro/es — no new strings).
  **Result (verified `npm run build`):** the monolithic 1.7 MB entry is gone —
  now 50+ per-route chunks (Login 8.5 kB, Dashboard 50 kB), the heavy
  `TwoFactorSetup`/qrcode (409 kB) and `Settings` (245 kB) are lazy, **no chunk
  exceeds 500 kB** (prior warning gone), and the login screen no longer downloads
  the whole app. The Dockerfile rebuilds the frontend (`npm run build` →
  `/app/static`), so this takes effect on the next image build.

- **[Med] ✅ DONE (U01) — Loading & skeleton states.**
  Most data views already used the `.skeleton` class; this change (a) adds a
  reusable, **accessible** primitive set `components/ui/Skeleton.jsx`
  (`Skeleton`/`SkeletonScreen`/`SkeletonList` — built on the existing `.skeleton`
  CSS, wrapping placeholders in `role="status"` + `aria-busy` + a visually-hidden
  localized "Loading…" that the old inline skeletons lacked), and (b) converts the
  remaining spinner-based **data views** to layout-matching skeletons:
  `VehicleExpenses` (header + tab bar + summary + rows), `Calendar` (42-cell grid),
  and `VehicleConsumables` (list). Reduces layout shift on flaky mobile links.
  No new strings (reuses `common.loading`); no deps; clean build.
  _Form-submit/inline spinners and PWA-status spinners are intentionally left as-is.
  Optional follow-up: GlobalSearch results, the public SharedReport, and admin
  panels could adopt skeletons too (lower traffic / mostly action spinners)._

- **[Med] ✅ DONE (U02) — Empty states with guidance.**
  The list views already had empty states **with CTAs but hardcoded in English**.
  This change adds a reusable, accessible `components/ui/EmptyState.jsx` (icon +
  localized title + guidance + primary CTA, `role="status"`, design-system `card`
  styling, copy passed in already-localized) and applies it to the first-run data
  views — **Vehicles** ("Add your first vehicle"), **Fuel**, **Services**,
  **Repairs** — replacing the hardcoded markup. Added a localized `empty.*`
  namespace (en/ro/es). Reminders already had a fully-localized, filter-aware
  empty state and was left as-is. Clean build; no deps; layout wraps long
  translations (`max-w-xs`).
  _Follow-up (optional): apply EmptyState to remaining surfaces with bespoke empty
  states (Calendar, VehicleExpenses tabs, Documents) and localize the surrounding
  page headers still hardcoded in those list pages._

- **[Med] ✅ DONE (U03) — Error surfaces & retry.**
  Root cause: the Dashboard fetched weather + fuel-price + air-quality in one
  `Promise.all`, so a single 503 silently blanked **all** widgets (stuck on
  "Loading…"/"--"). Fix: new reusable `components/ui/ServiceUnavailable.jsx`
  (accessible `role="status"` inline card with localized message, **Retry**, and
  dismiss); Dashboard switched to **`Promise.allSettled`** with independent
  per-service error/dismiss/retry state, plus `retryWeather`/`retryFuel` handlers
  (reuse the resolved location, so retry works even if the first load fully
  failed). The Weather and Fuel widgets now render the affordance in place of an
  empty widget when their service errors and has no data. Localized `serviceError.*`
  (en/ro/es); reused existing `common.dismiss`. Clean build; no deps.
  _Note: the AI/Ollama path already has its own offline banner, so it was left as-is.
  Follow-up (optional): apply the same affordance to other optional-service
  surfaces (currency rates, weather-alerts) if desired._

- **[Med] ◑ PARTIAL (U04) — Form UX consistency.**
  The forms were **already** react-hook-form based with inline field errors, so a
  full "shared form component" rewrite of 15 working forms = high regression risk
  for low marginal value (conflicts with "don't break/overcomplicate"). Delivered
  the genuinely-missing, named mechanics instead:
    - **Numeric keyboards:** added `inputMode="decimal"` to **all 48** `type="number"`
      inputs across the 14 add/edit forms (amounts, odometer, etc.) — the explicit
      mobile ask. (Consumable form already had `inputMode`.)
    - **Unsaved-changes guard:** new `hooks/useUnsavedChanges.js` (`beforeunload`,
      browser-native prompt → no new strings) applied to **12 entry add forms**
      (8 vehicle-scoped: fuel/service/repair/tax/parking/insurance/reminder/todo,
      + 4 global add routes). Covers accidental refresh / tab-close / app-dismiss
      on mobile.
    - **Foundation:** reusable accessible `components/ui/FormField.jsx`
      (label + hint + `role="alert"` inline error, `aria-describedby`) for gradual
      consolidation without a risky big-bang rewrite.
  Clean build; no deps; no new translatable strings.
  _Deferred (separate careful pass): migrating all forms onto FormField, and
  in-app (client-side) navigation blocking — the latter needs a react-router
  data-router migration (createBrowserRouter + useBlocker)._

- **[Low] ✅ DONE (U05) — Toast consolidation.**
  Added a **global visible-toast limit** in `App.jsx` (`useToastLimit` via
  `useToasterStore`, keeps the newest 3 and dismisses the rest) so a burst of
  notifications can't stack up and drown each other — applies to **all 129** toast
  call sites with zero per-site churn. Also tuned the `<Toaster>` config: errors
  now linger longer (5 s vs 2.5 s for success) and carry `role="alert"` /
  `aria-live="assertive"` so they're announced and not missed; `maxWidth: 92vw` +
  `gutter` so long translated messages wrap cleanly. The existing `{ id }` dedupe
  pattern (e.g. `session-expired`) remains the convention for high-frequency
  toasts and is now backstopped by the limit. No new strings; no deps; clean build.

- **[Low] ✅ DONE (U06) — Confirmations for destructive actions.**
  Added a reusable, accessible, promise-based `components/ui/ConfirmDialog.jsx`
  (`ConfirmProvider` + `useConfirm()`) — a themed modal replacing native
  `window.confirm`: `role="dialog"`/`aria-modal`, Escape + backdrop cancel, focus
  moves to the **safe (Cancel)** button for destructive actions and is restored
  on close, minimal Tab focus-trap, red destructive vs accent primary buttons,
  responsive (stacked buttons on mobile, width-capped/wrapping text). Migrated the
  **vehicle archive / delete** flows to it with the **entity name echoed**:
  `VehicleDetail` (delete + archive/restore), `Dashboard` (delete — previously a
  hardcoded-English native confirm, now localized), and Settings → archived
  vehicle delete. New localized `confirm.*` namespace (en/ro/es). Clean build.
  _Notes: "attachment delete" has **no UI** today (only an unused `attachmentApi.delete`),
  so nothing to migrate; admin maintenance/cleanup already uses a deliberate
  two-step confirm with a removal preview. Other `window.confirm` sites (backup
  import/restore, API-key revoke, entry delete) can adopt `useConfirm` incrementally._

---

## 3. Feature Suggestions

### 3.1 Vehicle / data
- **✅ DONE (F01) — CSV import & export** of fuel/service/repair/tax/parking history.
  New `app/services/csv_io.py` (curated per-type columns, round-trippable) +
  `GET /api/backup/export/csv?type=&vehicle_id=` and `POST /api/backup/import/csv`
  (token-auth). UI: an "Export / Import CSV" card in Settings → Backup with a
  type selector and export/import buttons; strings translated en/ro/es.
  **Security/robustness:** user-scoped export; import enforces `vehicle_id`
  ownership, validates each row independently with a per-row error report,
  skips duplicates (vehicle+date+amount) in merge mode, and is non-destructive.
  **CSV-injection (CWE-1236) hardened:** formula-leading text cells are
  apostrophe-escaped on export and un-escaped on import (round-trip-verified).
  utf-8-sig BOM for Excel. Verified end-to-end (export, dedup, bad-row isolation,
  cross-user block, injection round-trip).
- **✅ DONE (F02) — Recurring expenses** (monthly parking, annual road tax) auto-generating entries.
  Tax recurrence was already shipped (model + form toggle + `process_recurring_tax_entries`
  daily job with backfill/dedup/self-heal). This change adds the missing
  **parking** half: `process_recurring_parking_entries` in
  `backend/app/services/__init__.py` (mirrors the tax job — heals NULL
  `next_due_date`, backfills missed periods, dedups by
  `(vehicle_id, parking_type, date)`, supports daily→annual) plus a daily 06:00
  scheduler job and a startup catch-up. A shared `_recurrence_step()` helper and a
  per-series backfill cap (`_MAX_RECURRING_BACKFILL=120`) protect against a
  `daily` permit with a long gap generating runaway rows. The parking/tax forms
  already expose the recurrence UI; the note copy was corrected (en/ro/es) to
  state that future entries are logged automatically (the old copy claimed only a
  reminder). Verified: monthly/annual backfill, self-heal, idempotent re-run, and
  the daily cap.
- **✅ DONE (F03) — Tire / battery / consumables tracking** as a first-class entry type
  with mileage- and time-based wear estimates.
  Implemented as **one** consolidated `consumable` entry type with a category
  (`tire`, `battery`, `wipers`, `brake_pads`, filters, `coolant`, `spark_plugs`,
  `belt`, …) — cleaner than three near-identical types, consistent with
  `service.service_type`. Backend: `ConsumableEntry` model (joined-table
  inheritance) with `install_date`/`install_odometer`/`expected_lifespan_km`/
  `expected_lifespan_months`, a `wear_estimate()` (max of mileage- and time-based
  progress → `good`/`monitor`/`replace`/`unknown` + remaining km/months), a full
  CRUD blueprint at `/api/consumables` (user-scoped, ownership-enforced),
  migration, and CSV import/export support (extends F01). Frontend: lazy-routed
  **Consumables** list page with accessible wear-bars + empty/loading states, an
  add/edit form (mobile `inputmode`, keyboard-accessible), and entry points from
  `VehicleDetail`. All strings localized (en/ro/es). Verified: wear math
  (mileage & time), CRUD, blueprint/table registration, CSV round-trip, and a
  clean production build.
  _Follow-up (optional): surface a consumables tab inside the richer
  `VehicleExpenses` page; add due-soon reminders from wear status._


### 3.2 Analytics
- **✅ DONE (F04) — Cost-per-km/mile trend over time** and **predicted next-12-months cost**.
  Deliberately **deterministic (no AI dependency)** for speed and offline-consistency:
  new `GET /api/vehicles/<id>/cost-analytics` aggregates the owner's entries
  (one query over the base `Entry` table — fuel stores `amount=total_price`),
  derives per-month distance from monotonic (running-max) odometer deltas →
  cost-per-distance series, lifetime cost-per-distance, and a **least-squares
  linear-regression forecast** over complete months (≥3 required) →
  `{avg_monthly, projected_next_12_total, trend, monthly[12]}`. Frontend extends
  the existing **Vehicle Charts** page with a lightweight SVG line chart (no new
  dep) for the trend + a forecast card with a trend badge; fetched independently
  so a failure degrades gracefully. User-scoped/ownership-enforced; strings
  localized (en/ro/es). Verified: trend math, distance deltas, forecast,
  insufficient-data hiding, cross-user 404, and a clean build.

- **Year-over-year comparison** view.
- **Year-over-year comparison** view.
- **✅ DONE (F05) — Shareable read-only report links** (signed, expiring, **revocable**).
  Note: the existing `Share` page is the PWA *share-target* handler, not a report
  share — so this was built fresh rather than repurposing it. New `ReportShare`
  model stores only the **SHA-256 hash** of a 256-bit `token_urlsafe` token (raw
  shown once); authed `POST/GET /reports/shares` + `DELETE /reports/shares/<id>`
  manage links; **public** (no-auth, rate-limited) `GET /reports/shared/<token>`
  (aggregate JSON) and `/pdf` serve them, rejecting revoked/expired (410) and
  unknown (404). Frontend: a public `/shared/report/:token` viewer page (outside
  the auth guard, its own lazy chunk) + a share manager in Settings → Reports
  (create with 1/7/30/90-day expiry, copy-once link, list with status + revoke).
  Public payload exposes only aggregate totals + vehicle make/model/name — never
  email, VIN, plate, addresses or attachments. Create/revoke are audit-logged.
  All strings localized (en/ro/es). Verified end-to-end: hash-at-rest,
  create→view→revoke(410)→expire(410), unknown→404, cross-user revoke blocked,
  no-PII payload, and a clean build.

### 3.3 AI (Ollama is already wired)
- **✅ DONE (F06) — Natural-language vehicle chat.**
  Implemented the missing `vehicles.vehicle_chat` endpoint (`POST /api/vehicles/<id>/chat`)
  that the pre-existing rate-limit hook (5/hour/user) now binds to. Single-turn,
  stateless Q&A **grounded only in the user's own vehicle data** (spend by
  category/year, last service, upcoming reminders, consumable wear) assembled
  server-side and passed to Ollama via the existing `chat()` helper with an
  `{answer}` schema and `resolve_model('chat')`. Frontend: a lazy-loaded
  `VehicleChat` page (transcript, suggested-question chips, accessible
  `role="log"` + labelled input, typing indicator, offline + AI-unavailable
  states) reachable from a new "Assistant" action on VehicleDetail.
  **Security:** ownership-enforced; context contains only the owner's data and the
  model has no tools/DB access, so prompt injection can't exfiltrate anything;
  the question is capped (500 chars) and wrapped in `---USER DATA---` /
  `---QUESTION---` "treat-as-data" delimiters; output capped + rendered as plain
  text (React-escaped, no XSS); stateless (no new PII at rest); per-user
  rate-limited; errors return a generic `code` localized client-side.
  All strings localized (en/ro/es). Verified: grounding, injection containment,
  ownership 404, empty→400, AI-disabled→503, 500-char cap; clean build.
  _Follow-up (optional): multi-turn history (kept single-turn for safety/perf);
  hide the entry point when AI is disabled server-side (currently degrades
  gracefully with a localized message)._
- **OCR auto-categorization** — use the parsed vendor/line-items to suggest the
  expense category, not just pre-fill amount/date.

### 3.4 Integrations
- **OBD-II / mileage auto-import** (manual entry is the main friction point).
- **Apple/Google Wallet pass** for insurance/registration cards.
- **Webhook / Home Assistant integration** alongside the existing widget API.

---

## 4. PWA-Specific Improvements

- **[High] Cache the app shell with a sensible runtime strategy.** ✅ DONE (P01)
  `vite.config.js` precaches static assets (`globPatterns`) but there's no
  `runtimeCaching` for API GETs. Add a `NetworkFirst` (with short timeout +
  fallback to IndexedDB/last-good) strategy for read endpoints so the app is
  genuinely useful offline, not just installable. You already have Dexie + an
  offline queue + conflict manager — wire the SW to it explicitly.
  > **Resolution:** The custom `src/sw.js` already had a `NetworkFirst` route for
  > `/api/*` GETs (cache `api-cache`, 10s network timeout, 24h/100-entry
  > expiration, last-good fallback offline) plus background-sync for mutations.
  > The real gaps were **security**, not missing caching: authenticated per-user
  > responses were cached too broadly and never purged on identity change.
  > - Added `API_CACHE_DENYLIST` + `isCacheableApiGet()` to **exclude sensitive
  >   endpoints** from disk cache: `/api/auth/`, `/api/admin/`, `/api/csrf-token`,
  >   `/api/backup/`, `/api/push/` (identity/session, admin, CSRF, large/sensitive
  >   blobs, subscription info). These pass through to network and fail-when-offline,
  >   which is correct for those surfaces.
  > - Added `clearApiCache()` (`src/utils/swCache.js`) that deletes the
  >   `api-cache` CacheStorage entry **and** posts a new `CLEAR_API_CACHE` message
  >   to the SW. Called on **login, register, and logout** in `AuthContext.jsx`, so
  >   one account's cached data can never be served to another user (or after
  >   sign-out) on a shared device.
  > - Kept the existing last-good offline fallback + background-sync queue intact;
  >   no behavioural regression for offline reads/writes.
  > - Deeper SW↔Dexie synthesis (SW reading repositories to build responses) was
  >   deliberately **deferred** as over-engineering vs. the existing Dexie-backed
  >   pages; the NetworkFirst last-good copy already covers the offline-read need.
  > - No new user-facing strings (pure plumbing). `npm run build` passes; built
  >   `dist/sw.js` contains the denylist literals + `CLEAR_API_CACHE`.

- **[Med] Offline write UX.** ✅ DONE (P02)
  You have `offlineQueue.js`, `syncService.js`, and `SyncConflictModal` — make the
  offline/queued state highly visible (the `SyncIndicator` exists; ensure it shows
  pending-write counts and last-sync time, and surfaces failures).
  > **Resolution:** Found a real bug — the app has two offline queues: the **Dexie
  > `offlineQueue`** (the one every repository write actually uses, with
  > pending/processing/**failed** status + error/retryCount) and the **Workbox**
  > background-sync queue. `useBackgroundSync` was reading only the Workbox queue,
  > so the indicator showed ~0 pending and never surfaced failures.
  > - `useBackgroundSync.js` now reads the **Dexie queue** as the source of truth
  >   (pending+processing count, failed count, failed-item detail), restores a
  >   **persistent** last-sync time from `syncMeta` (survives reload), and refreshes
  >   on the `gearcargo:sync-complete` event and SW `QUEUE_UPDATED` message — not
  >   just the 30s poll. "Sync now" calls `processOfflineQueue()` to drain Dexie,
  >   then nudges the Workbox queue.
  > - `SyncIndicator.jsx` gained a distinct **failed-writes** badge + retry, a card
  >   section with failure detail + error text, an offline-safe notice, an
  >   "all changes saved" state, and locale-formatted last-sync. Migrated off its
  >   inline translations object to the global i18n (`pwa.sync.*`); the previously
  >   un-localized "Sync Status" string is now translated.
  > - Surfaced the richer **`card` variant** in Settings → after *Data & Backup*
  >   (header still shows the compact `badge`).
  > - Buttons are real `<button>`s with focus rings + `aria-label`s; badge row
  >   wraps and counts use `shrink-0`/`break-words` so long translations don't
  >   break layout.
  > - New `pwa.sync.*` strings added in **en/ro/es**. `npm run build` passes.

- **[Med] Background Sync & Periodic Sync.** ✅ DONE (P03)
  Use the Background Sync API (`useBackgroundSync` hook is present) to flush the
  offline queue when connectivity returns even if the app is closed; consider
  Periodic Background Sync for reminder refresh.
  > **Resolution (Option A — trigger + reads, chosen with the user):** The real
  > offline write queue is the **Dexie `offlineQueue`**, whose replay engine
  > (conflict detection + temp-id remap + endpoint mapping) lives in the page
  > (`syncService.js`). The Background Sync `sync` event runs in the SW, which
  > can't run page code — so doing a full *write* replay in the SW would mean
  > duplicating that engine and weakening conflict handling. We deliberately
  > avoided that.
  > - **Background Sync = reliable trigger.** New `src/utils/syncTags.js`
  >   (shared tag constants) + `src/utils/pwaSync.js` (`registerBackgroundSync`,
  >   feature-detected/best-effort). `offlineQueue.queueOperation()` registers the
  >   `gearcargo-flush-queue` tag on every queued write. The SW `sync` handler
  >   wakes live clients with a `SYNC_NOW` message; `useBackgroundSync` handles it
  >   by running the authoritative `processOfflineQueue()` in the page. Fully-closed
  >   write flush is deferred to next open (existing `online` listener) — no SW
  >   write engine, no data-integrity risk.
  > - **Periodic Background Sync = reminder refresh (read-only).** SW
  >   `periodicsync` handler (`gearcargo-reminder-refresh`, 12h floor) warms
  >   `/api/reminders` into `api-cache` so reminders are fresh on next (offline)
  >   open. Registered via `registerPeriodicReminderSync()` only for an installed
  >   PWA with the permission already granted (never prompts). The api-cache entry
  >   is still purged on logout/identity change (P01), so no cross-user leak.
  > - Graceful no-op on Safari/Firefox (no SyncManager / periodicSync). No new
  >   user-facing strings (silent flush reuses the existing localized sync UI).
  >   `npm run build` passes; SW bundle contains the new tags + handlers.
  > - *Follow-up (optional):* unregister periodic sync on logout (currently
  >   harmless — fetch no-ops when logged out and cache is purged).

- **[Med] Push notification lifecycle.** ✅ DONE (P04)
  A recent fix touched push (422/500 handling, VAPID). Add a clear in-app
  permission-priming UI (explain value before the browser prompt), a settings
  toggle to re-subscribe, and handling for expired subscriptions (re-subscribe on
  `pushsubscriptionchange`).
  > **Resolution:**
  > - **Permission priming:** new `PushPrimingModal` (value bullets: reminders,
  >   expiry alerts, security alerts) shown the first time the user enables push
  >   *only when OS permission is still `default`*. The real browser prompt fires
  >   only on "Enable", so we never burn the one-shot permission on an undecided
  >   user. Already-granted → subscribe directly; denied → existing blocked toast.
  > - **Re-subscribe:** `usePushNotifications` gained `resubscribe()` (tears down
  >   the old browser + server subscription, then subscribes fresh). Surfaced as a
  >   subtle "Re-subscribe" link in Settings → Notifications (shown when
  >   subscribed + granted) to recover a stale endpoint without toggling off.
  > - **Expired subscriptions:** SW now handles `pushsubscriptionchange` —
  >   re-fetches the VAPID key, re-subscribes via `pushManager.subscribe`, and
  >   re-registers with `/api/push/subscribe` (httpOnly cookie rides along; no-ops
  >   if logged out). Reuses the server's existing upsert/anti-hijack logic.
  > - Modal is keyboard-accessible (Esc, auto-focused primary, focus rings),
  >   responsive (stacked buttons on mobile), uses design tokens. New `settings.*`
  >   strings added in **en/ro/es**; cancel reuses `pwa.notNow`. `npm run build`
  >   passes; SW bundle contains the new handler + endpoints.

- **[Med] Update prompt clarity.** ✅ DONE (P05)
  `UpdatePrompt` exists — ensure the "new version available, reload" flow is
  reliable after `sw.js` changes (it's served `no-store`, good) and doesn't strand
  users on a stale shell.
  > **Resolution:** The genuine stranding risk is code-split chunks — every route
  > is `React.lazy()`, so after a deploy an old shell importing a now-removed
  > hashed chunk hits a blank route.
  > - **Stale-chunk auto-recovery** (`main.jsx`): listen for Vite's
  >   `vite:preloadError` and reload once to pick up the fresh shell, guarded by a
  >   10s `sessionStorage` cooldown so an unrecoverable chunk can't cause a reload
  >   loop.
  > - **Update-accept safety net** (`UpdatePrompt.jsx`): `handleUpdate` now awaits
  >   `updateServiceWorker(true)` then schedules a fallback `location.reload()`
  >   (~2.5s) — cancelled by the normal controllerchange reload, but fires if there
  >   is no waiting worker, so accepting the prompt can never silently no-op.
  > - **Robust polling:** the 60-min `r.update()` and the on-focus
  >   `getRegistration().update()` are now `.catch()`-guarded (no unhandled
  >   rejections when offline).
  > - Verified `injectRegister: 'auto'` does **not** double-register the SW
  >   (handled by `useRegisterSW`). No new user-facing strings (recovery is a
  >   transparent reload). `npm run build` passes.

- **[Low] iOS PWA polish.** ✅ DONE (P06)
  Apple touch icons/splash screens were recently added (commit `bc7271a`). Verify
  `apple-mobile-web-app-status-bar-style`, safe-area insets (`env(safe-area-inset-*)`)
  on the bottom nav, and that the install prompt copy is iOS-aware (no
  `beforeinstallprompt` on iOS).
  > **Resolution:**
  > - **Verified (no change needed):** `apple-mobile-web-app-status-bar-style`
  >   = `black-translucent` + `viewport-fit=cover` in `index.html`; the header
  >   uses `.safe-top` (`env(safe-area-inset-top)`, `max(...,20px)` in standalone)
  >   and the bottom nav uses `.bottom-nav`
  >   (`calc(env(safe-area-inset-bottom) + 0.5rem)`). All correct.
  > - **Fixed the real gap — iOS-aware install copy:** `InstallPrompt` relied
  >   solely on `beforeinstallprompt`, which iOS Safari never fires, so iOS users
  >   got *no* install guidance. Added `isIosDevice()` (incl. iPadOS-as-Mac touch
  >   detection) + `isInStandalone()` (`navigator.standalone`). On iOS it now shows
  >   a manual **Share → "Add to Home Screen"** instruction card (numbered steps
  >   with Share + add-to-home glyphs, a "Got it" dismiss; no non-functional
  >   Install button), reusing the same 7-day dismissal + already-installed guards.
  >   Buttons are keyboard-focusable with focus rings.
  > - New `pwa.*` strings (`iosInstallDescription`, `iosInstallShare`,
  >   `iosInstallAddToHome`, `gotIt`) added in **en/ro/es**. `npm run build` passes.
  > - *Trade-off noted:* `black-translucent` always renders white status-bar text;
  >   in light theme over a light header this is slightly low-contrast. Left as-is
  >   to preserve the immersive full-bleed splash design (predominant theme is
  >   dark); a theme-reactive status bar would need JS meta-swapping — optional
  >   follow-up if desired.

- **[Low] App shortcuts & share target.** ✅ DONE (P07)
  Add manifest `shortcuts` ("Add fuel", "Add expense") and a `share_target` so users
  can share a receipt photo directly into the OCR upload flow from the OS share sheet.
  > **Resolution:**
  > - **Shortcuts:** manifest now has **Add Fuel** (`/fuel/add`), **Add Expense**
  >   (`/services/add` — closest real cost-entry route; the app has no distinct
  >   "expense" route), and the existing **My Vehicles**.
  > - **Share target:** manifest `share_target` (POST/multipart, `files: receipt
  >   image/*`, action `/share-target`). The SW intercepts the POST, stashes the
  >   image in a dedicated CacheStorage entry and 303-redirects into the SPA.
  > - **Landing flow:** new auth-gated `/share-target` page reads the shared image
  >   (then **deletes it from cache** for privacy), lets the user pick a vehicle
  >   (auto-selected when only one), and reuses `ScanReceiptBanner` (without
  >   `onPrefill`, so no orphan "pre-fill form" button) to upload to that vehicle +
  >   run OCR — landing the photo straight in the OCR upload flow. Shows extracted
  >   fields + a "view documents" link on completion. **Zero add-page edits.**
  > - New `shareTarget.*` strings in **en/ro/es**; reuses `common.vehicle`,
  >   `common.selectVehicle`, `validation.addVehicleFirst`. `npm run build` passes;
  >   verified the built manifest + sw.js contain the new entries.
  > - *Trade-offs:* (1) Manifest shortcut/share labels aren't runtime-localizable
  >   (static manifest) — kept in English like the rest of the manifest; a future
  >   per-locale manifest could localize them. (2) Sharing while offline lands the
  >   page but the upload needs connectivity (the OCR upload is inherently online).
  >   (3) Wiring extracted data into a specific entry form (fuel/service/…) is a
  >   possible follow-up; today the receipt is saved as a vehicle document + OCR'd.

---

## 5. Code Quality / Operability

- **[Med] Add automated tests + CI.** ✅ DONE (Q01)
  No test suite is evident. Given the security surface (auth, encryption, signed
  URLs, lockout, SSRF guard), add unit tests for those helpers plus a smoke-test
  CI that runs migrations and boots the app. Wire in `pip-audit`/`npm audit`.
  > **Resolution:**
  > - **Unit tests for the security-critical helpers** (extend the existing
  >   `backend/tests/` + `conftest.py`):
  >   - `test_encryption.py` — Fernet/HKDF round-trip, `v2:` prefix, empty
  >     passthrough, non-deterministic ciphertext, garbage→`''` (no raise),
  >     re-encrypt, deterministic/normalised `hash_email`.
  >   - `test_signed_urls.py` — upload + S20 attachment HMAC: valid verify,
  >     expiry, tamper rejection, and **identity binding** (a token for one
  >     attachment/user must not verify for another).
  >   - `test_ssrf_guard.py` — `validate_ollama_url`: allows loopback/RFC-1918/
  >     hostname, blocks bad scheme, missing host, embedded creds, link-local
  >     cloud-metadata (169.254.169.254) and CGNAT (100.64/10).
  >   - `test_password_security.py` — set/check, empty-hash rejection, and the
  >     S02 >72-byte-not-truncated property.
  >   - `test_account_lockout.py` — the **DB-backed lockout fallback** (Redis
  >     forced to `None`): locks after `MAX_LOGIN_ATTEMPTS`, reports remaining,
  >     stays unlocked below threshold, no crash on unknown email.
  > - **Smoke-test CI** (`.github/workflows/ci.yml`): runs `flask db upgrade`
  >   (migrations), boots the app (asserts blueprints register + a request
  >   succeeds), runs `pytest`, and builds the frontend (`npm ci && npm run
  >   build`). Uses SQLite + writable dirs under `$RUNNER_TEMP` and **runtime-
  >   generated ephemeral secrets** — no `/app`, no privileged setup, no
  >   world-writable permissions.
  > - **`pip-audit` / `npm audit`** were already wired in
  >   `dependency-audit.yml` (+ dependabot) — left as-is, referenced from the new
  >   workflow rather than duplicated.
  > - Tiny enabling change: `VOLUMES_PATH` / `UPLOAD_FOLDER` / `BACKUP_FOLDER`
  >   are now env-overridable in `config.py` (**defaults unchanged**) so CI/non-
  >   container hosts can use a writable path without privilege hacks.
  > - Local note: the dev `.venv` lacks some heavy deps (`pywebpush`, …), so the
  >   full suite runs in CI; the pure helpers (SSRF, encryption, signed URLs)
  >   were validated locally before commit.

- **[Med] Structured logging & log hygiene.** ✅ DONE (Q02)
  Security events go through `ActivityLog` and `security_audit` (good). Ensure no
  PII (full emails, IPs) is logged at INFO in production beyond what's needed, and
  consider JSON logs for ingestion.
  > **Resolution:** Scoped to the **general** app logger; the dedicated
  > `security_audit` log keeps full PII for forensics (it's access-controlled and
  > `propagate=False`, so it is untouched).
  > - New `app/utils/logging_config.py`:
  >   - **`RedactionFilter`** — attached to the app + root log handlers, scrubs
  >     PII from every emitted record (defense-in-depth across all ~259 call
  >     sites): emails → `j***@domain`, IPv4 → `1.2.x.x`, IPv6 → `prefix::redacted`,
  >     JWTs and 32+ hex tokens → `[redacted-token]`; also redacts attached
  >     exception text.
  >   - **`JsonLogFormatter`** — one JSON object per line (`time/level/logger/
  >     module/message[/exception]`) when `LOG_FORMAT=json`, for ingestion.
  >   - **`mask_email()`** helper for explicit call sites.
  > - `configure_logging(app)` wired early in `create_app` (idempotent); knobs in
  >   `config.py`: `LOG_LEVEL`, `LOG_FORMAT` (text|json), `LOG_REDACT_PII`
  >   (default **on**; DevelopmentConfig defaults it **off** so local logs stay
  >   readable — secure-by-default in prod, convenient in dev).
  > - Masked the two explicit `admin_email`-at-INFO leaks in `create_app`.
  > - Unit tests: `tests/test_log_redaction.py` (email/IPv4/IPv6/JWT/hex
  >   redaction, no-op on clean text, `RedactionFilter` on real `LogRecord`s,
  >   valid redacted JSON). Validated locally (stdlib-only module).
  > - No user-facing strings (server logs). No change to the security_audit
  >   schema or the `ActivityLog` model.

- **[Low] Move heavy background work to a real queue** (see 1.5) — RQ on the
  existing Redis is the lowest-friction option. ✅ DONE (Q03 — opt-in)
  > **Resolution (opt-in, non-breaking — chosen with the user):** A full
  > mandatory `rq worker` across all 6 compose files was rejected (it contradicts
  > the S12 rationale and risks breaking deployments). Instead:
  > - New `app/services/task_queue.py` with a single **`enqueue_task(func, …)`**
  >   entry point and two interchangeable backends selected by
  >   `TASK_QUEUE_BACKEND`:
  >     - `thread` (**default**) — daemon thread inside the web worker, i.e.
  >       *exactly today's behaviour*; nothing changes for existing deployments.
  >     - `rq` — enqueue onto **RQ on the existing Redis**, run by a separate
  >       `rq_worker.py` (`SimpleWorker`, app context pushed for its lifetime).
  >   Both run the task inside an app context; if `rq` is requested but
  >   unavailable it logs once and falls back to threads (work is never dropped).
  > - Consolidated the scattered OCR thread-spawns: both OCR call sites
  >   (upload + retry) now call `enqueue_task(run_ocr_task, …)`. The global
  >   `_OCR_SEMAPHORE` still bounds CPU in both backends. Other thread spawns
  >   (fuel price, admin, calendar, startup probes) can adopt `enqueue_task`
  >   incrementally — the abstraction is in place.
  > - `rq~=1.16` added to `requirements.txt` (bundled so enabling RQ needs no
  >   rebuild; not imported unless the `rq` backend is used). Config: `TASK_QUEUE_
  >   BACKEND` / `TASK_QUEUE_NAME` / `TASK_QUEUE_TIMEOUT`. Optional worker compose
  >   snippet documented in `rq_worker.py` (no compose file edited → zero
  >   deployment risk).
  > - Tests: `tests/test_task_queue.py` (pure `resolve_backend` selection +
  >   thread-backend executes the task inside an app context). No user-facing
  >   strings. This supersedes the S12 deferral below (queue now available).

- **[Low] `serve_uploads` vs `UPLOAD_FOLDER` path mismatch.** ✅ DONE (Q04 — kept + hardened)
  `serve_uploads()` reads from a sibling `uploads/` dir while `UPLOAD_FOLDER` is
  `/app/volumes/attachments`. Confirm this route is still used (attachments are
  served via the signed `/api/attachments/<id>/view` path); if dead, remove it to
  shrink attack surface.
  > **Finding: the route is NOT dead — the premise was wrong, so removal was
  > rejected** (it would break every avatar and vehicle photo). The two paths are
  > *intentionally separate stores*:
  >   - `<app_root>/../uploads` (= `/app/uploads`) — **avatars + vehicle photos**,
  >     written by `auth.py`/`vehicles.py`, served by `serve_uploads` behind
  >     **HMAC-signed URLs** (`User.avatar_url` / `Vehicle.photo_url` →
  >     `sign_upload_url`). The read path matches the write path.
  >   - `UPLOAD_FOLDER` (`/app/volumes/attachments`) — **document attachments**,
  >     served by `/api/attachments/<id>/view` (S20 signed media tokens).
  > **Since it must stay, I hardened it instead of removing (shrinks attack
  > surface, behaviour-preserving):**
  >   - **Image-extension allowlist** — only `png/jpg/jpeg/webp/gif/bmp/tiff` are
  >     served (both upload paths only ever produce jpg/png/gif/webp), so no
  >     non-image file could ever be served from this store.
  >   - Response headers `X-Content-Type-Options: nosniff` +
  >     `Content-Security-Policy: default-src 'none'; sandbox` so served media can
  >     never be MIME-sniffed or executed as active content (stored-XSS defence).
  >   - `Cache-Control: private, max-age=3600` (≤ signed-URL expiry) — small perf
  >     win, keeps private media out of shared caches.
  >   - Docstring now documents the two-store design so the "mismatch" isn't
  >     mistakenly "fixed" by repointing at `UPLOAD_FOLDER`.
  > No user-facing strings; no frontend change.

---

## Summary of Top Priorities

1. **Fail closed (or degrade safely) on Redis outage** for session validation &
   token revocation. *(security)*
2. **Route-level code splitting** with `React.lazy`. *(PWA/perf — biggest UX win)*
3. **Runtime API caching in the service worker** to make the PWA genuinely offline. *(PWA)*
4. **Bound the `external.py` in-memory cache** and **align upload size limits**. *(DoS)*
5. **Finish the AI vehicle-chat endpoint** (already half-wired). *(feature)*
6. **Add CI with dependency scanning + tests** for the security-critical helpers. *(operability)*

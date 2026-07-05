# GearCargo

A comprehensive vehicle management Progressive Web App (PWA) for tracking fuel consumption, services, repairs, insurance, taxes, and all vehicle-related expenses.

## Screenshots

<table>
  <tr>
    <td width="50%" valign="top"><img src="docs/screenshots/dashboard.png" alt="Dashboard — weather, live fuel prices and your garage"><br><sub><b>Dashboard</b> — weather, live fuel prices &amp; your garage</sub></td>
    <td width="50%" valign="top"><img src="docs/screenshots/vehicle-detail.png" alt="Vehicle overview"><br><sub><b>Vehicle overview</b></sub></td>
  </tr>
  <tr>
    <td width="50%" valign="top"><img src="docs/screenshots/expenses.png" alt="Expenses — breakdown and charts"><br><sub><b>Expenses</b> — category breakdown &amp; charts</sub></td>
    <td width="50%" valign="top"><img src="docs/screenshots/assistant.png" alt="AI vehicle assistant chat"><br><sub><b>AI vehicle assistant</b></sub></td>
  </tr>
  <tr>
    <td width="50%" valign="top"><img src="docs/screenshots/recommendations.png" alt="Smart recommendations"><br><sub><b>Smart recommendations</b></sub></td>
    <td width="50%" valign="top"><img src="docs/screenshots/vehicle-health.png" alt="Vehicle health"><br><sub><b>Vehicle health</b></sub></td>
  </tr>
  <tr>
    <td width="50%" valign="top"><img src="docs/screenshots/consumables.png" alt="Consumables tracking"><br><sub><b>Consumables tracking</b></sub></td>
    <td width="50%" valign="top"><img src="docs/screenshots/reminders.png" alt="Reminders"><br><sub><b>Reminders</b></sub></td>
  </tr>
  <tr>
    <td width="50%" valign="top"><img src="docs/screenshots/calendar.png" alt="Calendar"><br><sub><b>Calendar</b></sub></td>
    <td width="50%" valign="top"><img src="docs/screenshots/fuel-add.png" alt="Log a fuel entry"><br><sub><b>Log fuel</b></sub></td>
  </tr>
  <tr>
    <td width="50%" valign="top"><img src="docs/screenshots/vehicle-add.png" alt="Add a vehicle"><br><sub><b>Add a vehicle</b></sub></td>
    <td width="50%" valign="top"><img src="docs/screenshots/settings.png" alt="Settings"><br><sub><b>Settings</b></sub></td>
  </tr>
  <tr>
    <td width="50%" valign="top"><img src="docs/screenshots/profile.png" alt="Profile"><br><sub><b>Profile</b></sub></td>
    <td width="50%" valign="top"><img src="docs/screenshots/login.png" alt="Sign in"><br><sub><b>Sign in</b></sub></td>
  </tr>
  <tr>
    <td width="50%" valign="top"><img src="docs/screenshots/register.png" alt="Create account"><br><sub><b>Create account</b></sub></td>
    <td width="50%" valign="top"><img src="docs/screenshots/change-password.png" alt="Change password"><br><sub><b>Change password</b></sub></td>
  </tr>
  <tr>
    <td width="50%" valign="top"><img src="docs/screenshots/security-questions.png" alt="Security questions"><br><sub><b>Security questions</b></sub></td>
    <td width="50%" valign="top"></td>
  </tr>
</table>

> Screens shown with demo data on the dark theme. A matching light theme is built in.

---

## Quick Start (Recommended Method)

- [Features](#features)
- [Screenshots](#screenshots)
- [Quick Start](#quick-start)
- [Deployment Options](#deployment-options)
- [Credential Generation](#credential-generation)
- [Admin User Setup](#admin-user-setup)
- [Configuration Reference](#configuration-reference)
- [Backup & Restore](#backup--restore)
- [Tech Stack](#tech-stack)
- [API Documentation](#api-documentation)
- [Contributing](#contributing)

---

## Features

### Vehicle Management
- Multiple vehicle profiles with photos and detailed specs
- Track mileage, fuel type, engine size, transmission
- Vehicle timeline with all activities
- Archive/restore vehicles
- Drag-and-drop vehicle reordering on dashboard
- **Clickable stat cards** — tap any dashboard card (fuel cost, service, tax, insurance, parking, reminders) to navigate directly to the relevant expense tab
- **YTD expense cards** — Parking, Tax, and Insurance stat cards show year-to-date totals at a glance
- **Interactive expense charts** — click any month bar in the Expenses bar chart to instantly filter the donut chart to that month's category breakdown; click again or tap "Full Year" to reset

### Fuel Tracking
- Log fuel entries with automatic consumption calculation
- Track fuel costs and efficiency (L/100km or MPG)
- **Unit-aware fuel economy** — economy displayed in L/100km or MPG automatically based on per-vehicle distance/volume unit settings
- **Fuel price auto-refresh** — price field pre-fills with the latest recorded price per unit on new entries
- Price comparison by station
- Full tank vs partial fill tracking
- Station location and address storage

### Service & Repair Logs
- Scheduled service tracking (oil changes, filters, etc.)
- Repair history with warranty tracking
- **Warranty date tracking** — record warranty expiry dates for services and repairs
- Parts and labor cost breakdown
- Service provider/shop information
- Mileage-based service intervals
- **Consumables tracking** — log wear items (tyres, brake pads, battery, filters, wipers) with brand, install date/odometer, cost and quantity; mileage-based wear estimates and "due" alerts

### Insurance Management
- Track multiple insurance policies per vehicle
- Policy expiration alerts
- Coverage details and premium tracking
- Document attachment support

### Tax & Registration
- Vehicle tax payment tracking
- Registration renewal reminders
- Road tax calculations
- MOT/inspection tracking

### Parking & Tolls
- Parking expense logging
- Toll payment tracking
- Location-based entries

### Smart Reminders
- Date-based reminders (insurance renewal, tax due)
- Mileage-based reminders (service intervals)
- Push notifications (browser & mobile)
- Email notifications
- Calendar integration (CalDAV - Google, Nextcloud, Baikal, Radicale)
- Multi-language reminder translations

### Calendar & Navigation
- Interactive calendar with all vehicle events
- **Clickable calendar entries** — click any day entry to navigate directly to expense details
- Color-coded entries by type (fuel, service, repair, insurance, tax, parking)
- CalDAV sync support (Google, Nextcloud, Baikal, Radicale)

### Analytics & Reports
- Cost breakdown by category (fuel, service, repairs, insurance, tax)
- Monthly/yearly expense reports
- PDF report generation with charts
- Interactive expense chart with drill-down
- Fuel efficiency trends
- Cost per kilometer/mile analysis
- **Shareable report links** — generate a read-only report link to share with a garage or family member; links are signed, expiring, and revocable (no account required to view)

### AI-Powered Features (Optional, via Ollama)
- **Vehicle Assistant (chat)** — a per-vehicle conversational assistant that answers grounded questions about *your* data: spending totals, fuel/service/repair history ("when did I last change the brake pads, what did it cost, where?"), upcoming reminders, and cross-vehicle comparisons ("which car costs most"). Strictly scoped to vehicles and maintenance with a layered safety design — input/output guardrails and an on-topic classifier — and **fully data-isolated** (answers only ever use the signed-in owner's own data; no tools, no retrieval, no stored history). Gracefully reports when the AI service is unavailable
- **Automatic nightly maintenance predictions** — nightly scheduler analyses each vehicle's fuel, service, and repair history and generates multilingual prediction alerts (EN/RO/ES)
- **Manual prediction trigger** — request an immediate AI analysis for any vehicle via the API
- **OCR receipt scanning** — photos of receipts are automatically scanned (pytesseract) using an 11-step quality pipeline (local illumination normalisation, adaptive binarisation, confidence-filtered word extraction) and parsed by Ollama into structured data (date, amount, vendor, line items) to pre-fill expense forms; max 2 concurrent scans to protect server CPU
- **Fuel anomaly detection** — after each fuel entry, Ollama checks the last 20 entries for suspicious consumption spikes or data-entry errors
- **AI reminder suggestions** — request 3 AI-generated service reminder suggestions per vehicle based on its history
- **Per-task model configuration** — assign different Ollama models to different tasks (`OLLAMA_MODEL_PREDICT`, `OLLAMA_MODEL_OCR`, `OLLAMA_MODEL_ANOMALY`, `OLLAMA_MODEL_REMINDER`) for optimal speed/quality trade-offs
- **Smart Recommendations page** — rule-based alerts for upcoming service, insurance, and tax deadlines
- Powered by any Ollama-compatible model (local or external); recommended: `qwen2.5` for structured JSON and multilingual output

### Attachments & Documents
- Attach receipts, invoices, documents to any entry
- Image preview and gallery view
- PDF document support
- Organized by vehicle and entry type
- **OCR text extraction** — images are automatically scanned in the background; click the scan icon in the viewer to review extracted text
- **AI data extraction** — send OCR text to Ollama to parse structured fields and pre-fill the parent expense form with one tap
- **OCR badge on thumbnails** — attachment cards display a badge when text has been successfully extracted
- **Re-scan button** — retry OCR for blurry or rotated images via the attachment viewer
- **OCR concurrency limit** — at most 2 OCR scans run simultaneously (upload, retry, startup backfill, and admin backfill all share one global semaphore); additional scans queue and run automatically when a slot frees up

### To-Do Lists
- Vehicle-specific task lists
- Priority levels and due dates
- Completion tracking

### Security Features
- **Two-Factor Authentication (2FA)** - TOTP with backup codes
- **Signed Upload URLs** - HMAC-SHA256 signed URLs for all uploaded files (photos, avatars)
- **Account Lockout Protection** - Auto-locks after 5 failed attempts
- **IP Blocking** - Auto-blocks IPs after 3 failed attempts
- **Device Blocking** - Auto-blocks suspicious devices
- **Session Management** - Single device enforcement option
- **New Device/Location Alerts** - Email notifications
- **Have I Been Pwned Integration** - Rejects breached passwords
- **bcrypt Password Hashing** - Industry-standard security
- **JWT with Blacklisting** - Secure token management
- **Rate Limiting** - API abuse prevention
- **CSRF Protection** - Cross-site request forgery prevention
- **Security Headers** - HSTS, CSP, X-Frame-Options via Flask-Talisman
- **Encrypted Backups** - AES encryption for backup files
- **Activity Logging** - Comprehensive audit trail
- **SSRF Protection** - Private/internal IP blocking on CalDAV and Ollama URLs
- **AI Chat Guardrails** - Layered prompt hardening, input/output validation, an on-topic classifier, and strict per-user data isolation for the Vehicle Assistant
- **Absolute Session Expiry** - Sessions expire 48h after sign-in regardless of activity
- **Signed, Expiring Share Links** - Shareable report links use signed, time-limited, revocable tokens
- **Startup Secret Validation** - Refuses to start in production with default/insecure secrets
- **Calendar Feed Token Expiry** - 90-day expiration on CalDAV feed tokens
- **Read-only Root Filesystem** - Container runs with read-only rootfs
- **GDPR Notification Email** - Separate notification email with full GDPR compliance:
  - AES-256 field-level encryption (Fernet) for PII at rest
  - SHA-256 hashing for duplicate lookups without decryption
  - Double opt-in verification with expiring tokens
  - Explicit consent capture with IP and timestamp
  - Immutable consent audit ledger (append-only log)
  - RFC 8058 one-click unsubscribe (no auth required)
  - Automatic bounce tracking — disables email after 5 failures
  - Rate limiting on verification emails (3/hour)

### Data Management
- Automatic scheduled backups
- Manual backup/restore
- Export to external servers (HTTPS)
- JSON and ZIP backup formats
- Import from backup files
- **LubeLogger import** — migrate from LubeLogger with full data conversion
- Distance unit conversion on import (km ↔ miles)
- Attachment import linked to corresponding entries
- **Import deduplication** — prevents duplicate entries on re-import
- **Backup deduplication** — eliminates duplicate attachment files in ZIP exports
- **Configurable upload limit** — up to 200 MB by default (adjustable via `MAX_UPLOAD_SIZE_MB`)

### Integrations
- **Gethomepage widget** — customapi widget with vehicle stats, service records, reminders
- API key authentication for external services
- Widget API endpoints for third-party dashboards
- CalDAV calendar sync (Google, Nextcloud, Baikal, Radicale)

### Mobile-First PWA
- Installable on any device (iOS, Android, Desktop), with iOS install guidance and opaque touch icons + splash screens
- Works offline with service workers — offline write queue with **background sync** that replays entries when connectivity returns, plus a sync status indicator
- In-app **update prompt** when a new version is available
- App shortcuts and **Share Target** — share a receipt photo straight into a new expense
- Push notifications (browser & mobile) with a permission-priming flow
- Touch-optimized compact UI
- Dark and light themes

### Internationalization
- Multi-language support (English, Romanian, Spanish)
- Customizable date formats
- Multiple currency support (EUR, GBP, USD, RON, etc.)
- Per-vehicle distance units (km/miles)
- Volume units (liters/gallons)

---

## Quick Start (Recommended Method)

### Prerequisites
- Docker & Docker Compose v2+
- Git
- 2GB RAM recommended (the single container runs the app + PostgreSQL + Redis)

GearCargo ships as **one** container — `ghcr.io/aiulian25/gearcargo:latest` —
bundling the app, PostgreSQL 16, Redis 7 and scheduled backups. Nothing to build.

### Install in 3 steps

```bash
mkdir -p ~/gearcargo && cd ~/gearcargo

# 1. Get the install files straight from the image (no repo access needed)
docker run --rm ghcr.io/aiulian25/gearcargo:latest install > gearcargo-install.sh
sh gearcargo-install.sh          # writes docker-compose.yml, .env.example, setup.sh

# 2. One guided step: generates every secret, creates ./volumes, starts the app
./setup.sh

# 3. Open the printed URL and create your admin account.
```

`setup.sh` asks only for your URL (and whether a reverse proxy runs on this host);
it generates all secrets **inside the image** — including a valid Fernet
`ENCRYPTION_KEY` and VAPID push keys — so the host needs nothing but Docker.

Only the app port is published; PostgreSQL and Redis bind to `127.0.0.1` **inside**
the container and are never network-exposed. Put a reverse proxy in front for HTTPS
(say "yes" to the proxy prompt to loopback-bind the port).

> **Prefer to do it by hand?** `cp .env.example .env`, fill the `REQUIRED` block
> (see [Credential Generation](#credential-generation)), `mkdir -p secrets` and add
> your VAPID key, then `docker compose up -d`.
>
> **Custom port / Synology:** set `APP_PORT` in `.env` (e.g. `5050`) — no separate file.
>
> **Already on the old 4-container stack?** See [Migrating to the Single Container](#migrating-to-the-single-container) — guided, verified, auto-rollback.

### Build from source (for development)

```bash
git clone https://github.com/aiulian25/GearCargo.git && cd gearcargo
cp .env.example .env && ./setup.sh            # or edit .env by hand
docker compose -f docker-compose.dev.yml up -d --build   # builds the single image
```

---

## Deployment options

For almost everyone, **the single container is the answer** — see
[Install in 3 steps](#install-in-3-steps). Pick another row only if it matches you:

| Scenario | What to use |
|----------|-------------|
| **Standard install** (recommended) | `docker-compose.yml` — pulls the single image. Run `./setup.sh` and you're done. |
| **Custom port / Synology NAS** | The *same* `docker-compose.yml`; just set `APP_PORT` in `.env` (e.g. `5050`). No separate file. |
| **Build from source / develop** | `docker-compose.dev.yml` — builds the single image locally (`up -d --build`). |
| **External DB/Redis (dual-mode)** | The standard compose; point `DATABASE_URL` / `REDIS_URL` at your host and the embedded servers stay dormant. |

**Image:** `ghcr.io/aiulian25/gearcargo:latest` — the single all-in-one image
(`:single` is an alias). That's the whole app.

The single container runs PostgreSQL 16 + Redis 7 + gunicorn + scheduled backups
under [s6-overlay](https://github.com/just-containers/s6-overlay); only the app
port is published and the datastores bind to `127.0.0.1` **inside** the container.
Clean PostgreSQL shutdown on `docker stop` (no WAL recovery on next boot).
**~2 GB RAM recommended.**

- Every environment variable is documented in **`examples/.env.reference`**.

## Migrating to the Single Container

If you already run the **4-container** stack and want to move to the single
container, use the guided migration script. It is **safe and reversible** — it
never deletes your old data, so you can roll back instantly.

**What it does:**
1. Checks your `ENCRYPTION_KEY` is present (PII is unrecoverable without it).
2. Takes a portable backup **and** an independent raw tarball.
3. Records your current row counts.
4. Stops the 4-container stack (volumes are preserved).
5. Starts the single container with a **fresh** embedded PostgreSQL at
   `./volumes/pgdata` — your old `./volumes/db` is never touched.
6. Restores your data and **verifies row counts match**, automatically rolling
   back to the 4-container stack if anything fails.

Run it from a checkout of this repository (`scripts/migrate-to-single.sh` +
`docker-compose.dev.yml`), in the folder that holds your existing `.env`,
`secrets/` and `volumes/`. It **reuses your existing `.env`** — same
`ENCRYPTION_KEY` / `SECRET_KEY` / `JWT_SECRET_KEY`, so encrypted data stays
readable.

```bash
# from your repo checkout, pointed at your data dir. Tell it your existing compose:
GC_PROD_COMPOSE=docker-compose.yml scripts/migrate-to-single.sh   # add --yes to skip prompts
```

> `GC_PROD_COMPOSE` must point at your **existing** multi-container compose (the
> one currently running db/redis/backend) — GearCargo no longer ships one.

> ⚠️ **Reuse the same `ENCRYPTION_KEY`.** A different key makes all encrypted PII
> permanently unrecoverable. The script refuses to run if the key is missing.

**Rollback (anytime — your original `./volumes/db` is never touched):**
bring your old stack back up with your own compose
(`docker compose -f <your-old-compose> up -d`), or restore the automatic backup
the script wrote to `./volumes/backups/` into a fresh install.

Keep the raw tarball and the old `./volumes/db` until the migrated install has run
cleanly for several days. Full details: [DEPLOY.md §15](DEPLOY.md).

---

## Credential Generation

### Required Secrets

GearCargo requires several cryptographic secrets. **Never use default values in production!**

#### 1. SECRET_KEY (Flask session encryption)

```bash
# Using Python
python3 -c "import secrets; print(secrets.token_hex(32))"

# Using OpenSSL
openssl rand -hex 32

# Example output: a1b2c3d4e5f6...64 characters
```

#### 2. JWT_SECRET_KEY (JWT token signing)

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
# or
openssl rand -hex 32
```

#### 3. WTF_CSRF_SECRET_KEY (CSRF protection)

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
# or
openssl rand -hex 32
```

#### 4. ENCRYPTION_KEY (Data encryption at rest)

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
# or
openssl rand -hex 32
```

> **Startup enforcement.** In any non-development environment (i.e. `FLASK_ENV`
> is not `development`), GearCargo **refuses to start** if `SECRET_KEY`,
> `JWT_SECRET_KEY`, `WTF_CSRF_SECRET_KEY` or `ENCRYPTION_KEY` is missing or still a
> placeholder. This check is independent of `DEBUG`, so a stray `DEBUG=true` can
> never bypass it. For local development only, set `FLASK_ENV=development`.

> **Rotating the encryption key (S06).** `ENCRYPTION_KEY` derives the key for all
> at-rest PII (2FA/email-OTP secrets, notification email, CalDAV credentials) via
> HKDF, and ciphertext is versioned, so the key can be rotated without data loss:
> 1. Generate a new key (command above).
> 2. Redeploy with the new value in `ENCRYPTION_KEY` and the **old** value in
>    `ENCRYPTION_KEYS_OLD` (comma-separated for multiple). New data is written
>    under the new key; old data still decrypts under the old key — no downtime.
> 3. Re-encrypt all existing rows under the new key:
>    `docker compose exec gearcargo python scripts/reencrypt_pii.py --execute`
>    (run without `--execute` first for a dry run).
> 4. Once it reports `0` undecryptable rows, remove `ENCRYPTION_KEYS_OLD` and
>    redeploy.

#### 5. DB_PASSWORD (PostgreSQL password)

```bash
# Generate a strong password
python3 -c "import secrets; print(secrets.token_urlsafe(24))"
# or
openssl rand -base64 24
```

#### 6. REDIS_PASSWORD (Redis authentication)

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(24))"
# or
openssl rand -base64 24
```

#### 7. VAPID Keys (Push notifications)

VAPID keys are required for web push notifications. Generate them using:

**Method 1: Using web-push CLI (Recommended)**
```bash
# Install web-push globally
npm install -g web-push

# Generate VAPID keys
web-push generate-vapid-keys

# Output:
# Public Key: BNx...
# Private Key: abc...
```

**Method 2: Using Python**
```bash
pip install py-vapid

python3 -c "
from py_vapid import Vapid
from cryptography.hazmat.primitives.serialization import (
    Encoding, PublicFormat, PrivateFormat, NoEncryption
)
import base64
v = Vapid()
v.generate_keys()
priv = base64.urlsafe_b64encode(
    v._private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
).rstrip(b'=').decode()
pub = base64.urlsafe_b64encode(
    v._private_key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
).rstrip(b'=').decode()
print('VAPID_PUBLIC_KEY=' + pub)
print('VAPID_PRIVATE_KEY=' + priv)
"
```

**Method 3: Online Generator**
Visit https://vapidkeys.com/ (use only for testing)

---

### Complete .env Example

```bash
# ===========================================
# GEARCARGO ENVIRONMENT CONFIGURATION
# ===========================================

# Application
APP_URL=https://gearcargo.yourdomain.com
APP_PORT=5000
ADMIN_DOMAIN=garaj.yourdomain.com
USER_DOMAIN=car.yourdomain.com

# Database (CHANGE THIS!)
DB_PASSWORD=your-super-secure-database-password-here

# Redis (CHANGE THIS!)
REDIS_PASSWORD=your-super-secure-redis-password-here

# Security Keys (GENERATE UNIQUE VALUES!)
SECRET_KEY=a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2
JWT_SECRET_KEY=b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3
WTF_CSRF_SECRET_KEY=c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4
ENCRYPTION_KEY=d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5

# CORS (your domain)
CORS_ORIGINS=https://gearcargo.yourdomain.com

# Admin User (Optional - see Admin User Setup section)
ADMIN_EMAIL=admin@yourdomain.com
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your-temporary-admin-password-min-8-chars

# Email (for password reset, notifications)
MAIL_ENABLED=true
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-specific-password
MAIL_DEFAULT_SENDER=noreply@yourdomain.com

# Push Notifications (GENERATE YOUR OWN!)
VAPID_PUBLIC_KEY=your-vapid-public-key
VAPID_PRIVATE_KEY=your-vapid-private-key
VAPID_SUBJECT=mailto:admin@yourdomain.com

# AI Features (optional)
OLLAMA_ENABLED=false
OLLAMA_BASE_URL=http://192.168.1.80:11434
# Global model fallback (run: ollama list to see installed models)
OLLAMA_MODEL=qwen2.5
OLLAMA_TIMEOUT=60
# Per-task model overrides (leave empty to inherit OLLAMA_MODEL)
OLLAMA_MODEL_PREDICT=qwen2.5
OLLAMA_MODEL_OCR=qwen2.5
OLLAMA_MODEL_ANOMALY=llama3.2
OLLAMA_MODEL_REMINDER=qwen2.5

# Reverse Proxy (1 = nginx/Traefik/Cloudflare)
TRUSTED_PROXY_COUNT=1

# GeoIP (optional — download GeoLite2-City.mmdb from MaxMind)
GEOIP_DB_PATH=

# Widget API CORS
WIDGET_CORS_ORIGINS=*

# Automated Backups
BACKUP_KEEP_LAST=7

# Theme
DEFAULT_THEME=dark
```

---

## Admin User Setup

GearCargo supports **two methods** for creating the initial admin user:

### Method 1: Environment Variables (Automatic - Recommended)

**With the pre-built image** (`docker-compose.yml`), admin creation is **fully automatic!**

Configure your `.env` file:
```bash
ADMIN_EMAIL=admin@yourdomain.com
ADMIN_USERNAME=admin
ADMIN_PASSWORD=YourSecurePassword123!
```

**What happens automatically on first startup:**
1. Database tables are created via migrations
2. Admin user is created if no users exist
3. Application starts ready to use

**Security Notes:**
- **Change default password immediately after first login!**
- Password must be at least 8 characters
- The admin user has full admin privileges (`is_admin=true`)
- After login, update credentials in Settings → Account

**Important:**
- Generate strong, unique credentials before deployment
- The admin user will have `calendar_enabled=true`, `push_enabled=true`, and `email_notifications_enabled=true` by default
- Never use default or example passwords in production

---

### Method 2: Self-Registration (Bootstrap Only)

If no `ADMIN_EMAIL`/`ADMIN_PASSWORD` environment variables are set:

1. Start the containers normally
2. Navigate to your configured **admin domain** (or http://localhost:5000 if domains are not configured)
3. **The first user to register automatically becomes the admin**
4. After an admin exists, public self-registration is automatically disabled

**Security Note:** This method is bootstrap-only and should be completed immediately after deployment. If `ADMIN_DOMAIN` is configured, first registration is only accepted from that domain.

### Verifying Admin Status

After creating the admin, verify in the logs:

```bash
docker compose logs backend | grep -i admin

# Expected output:
# Default admin user created: admin@yourdomain.com
# IMPORTANT: Change the admin password immediately and remove ADMIN_PASSWORD from environment!
```

### Admin Capabilities

The admin user can:
- View all users and their activity
- Create/edit/delete user accounts
- Set user permissions and vehicle limits
- View system-wide statistics
- Access activity logs and security events
- Block/unblock IPs and devices
- Manage system settings
- Run maintenance tasks

---

## Configuration Reference

### Environment Variables

| Variable | Required | Description | Default |
|----------|----------|-------------|---------|
| `SECRET_KEY` | Yes | Flask secret key (64 hex chars) | - |
| `JWT_SECRET_KEY` | Yes | JWT signing key (64 hex chars) | - |
| `DB_PASSWORD` | Yes | PostgreSQL password | - |
| `REDIS_PASSWORD` | Yes | Redis password | `changeme` |
| `APP_URL` | Yes | Public URL of your app | `http://localhost:5000` |
| `ADMIN_DOMAIN` | Optional | Domain reserved for admin logins | empty |
| `USER_DOMAIN` | Optional | Domain reserved for non-admin logins | empty |
| `CORS_ORIGINS` | Yes | Allowed origins (comma-separated) | `http://localhost:5000` |
| `WTF_CSRF_SECRET_KEY` | Recommended | CSRF secret | Falls back to SECRET_KEY |
| `ENCRYPTION_KEY` | Recommended | Data encryption key | - |
| `ADMIN_EMAIL` | Optional | Auto-create admin email | - |
| `ADMIN_PASSWORD` | Optional | Auto-create admin password | - |
| `MAIL_ENABLED` | Optional | Enable email features | `false` |
| `VAPID_PUBLIC_KEY` | Optional | Push notification public key | - |
| `VAPID_PRIVATE_KEY` | Optional | Push notification private key (prefer Docker secret) | - |
| `MAX_UPLOAD_SIZE_MB` | Optional | Max file upload size in MB | `200` |
| `GUNICORN_WORKERS` | Optional | Gunicorn worker process count | `4` |
| `TRUSTED_PROXY_COUNT` | Optional | Trusted reverse proxy depth for real IP detection | `1` |
| `GEOIP_DB_PATH` | Optional | Container path to GeoLite2-City.mmdb for login country detection | empty |
| `WIDGET_CORS_ORIGINS` | Optional | CORS origin allowlist for widget API endpoints | `*` |
| `BACKUP_KEEP_LAST` | Optional | Number of daily/weekly backup archives to retain | `7` |

### Ollama AI Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OLLAMA_ENABLED` | Enable all AI features | `false` |
| `OLLAMA_BASE_URL` | Ollama server URL | `http://host.docker.internal:11434` |
| `OLLAMA_MODEL` | Global default model (fallback for all tasks) | empty |
| `OLLAMA_TIMEOUT` | HTTP timeout in seconds | `60` |
| `OLLAMA_MODEL_PREDICT` | Model for nightly maintenance predictions (complex JSON + multilingual) | inherits `OLLAMA_MODEL` |
| `OLLAMA_MODEL_OCR` | Model for receipt OCR data extraction (structured fields) | inherits `OLLAMA_MODEL` |
| `OLLAMA_MODEL_ANOMALY` | Model for fuel anomaly detection (fast classification) | inherits `OLLAMA_MODEL` |
| `OLLAMA_MODEL_REMINDER` | Model for AI-generated reminder suggestions | inherits `OLLAMA_MODEL` |

**Recommended model split** (8 GB VRAM):
| Task | Model | Reason |
|------|-------|--------|
| Predictions, OCR, Reminders | `qwen2.5` | Best structured JSON + EN/RO/ES multilingual output |
| Anomaly detection | `llama3.2` | Fast and lightweight — speed matters on every fuel save |

### JWT Token Expiration

| Variable | Description | Default |
|----------|-------------|---------|
| `JWT_ACCESS_TOKEN_EXPIRES` | Access token lifetime (seconds) | `3600` (1 hour) |
| `JWT_REFRESH_TOKEN_EXPIRES` | Refresh token lifetime (seconds) | `2592000` (30 days) |

### Rate Limiting

| Variable | Description | Default |
|----------|-------------|---------|
| `RATELIMIT_ENABLED` | Enable rate limiting | `true` |
| `RATELIMIT_DEFAULT` | Default rate limit | `200 per day` (dev) / `100 per hour` (prod) |

---

## Backup & Restore

### Automatic Backups

Configure automatic backups in Settings > Backup:
- Schedule daily/weekly backups
- Set retention period
- Configure one or more external backup destinations (HTTPS)
- Each destination can be independently enabled/disabled per user
- Reorder destinations to control primary destination precedence
- Toggle credential visibility per destination (credentials stay masked by default)

### Manual Backup

**Using the CLI (inside the container):**
```bash
# Runs the same archive builder the scheduler uses, against the embedded database.
docker compose exec gearcargo /etc/gearcargo/scripts/run-backup.sh manual
# Creates: ./volumes/backups/system/manual/gearcargo_manual_YYYYMMDD_HHMMSS.tar.gz
```

**Using the web interface:**
1. Go to Settings > Backup
2. Click "Create Backup"
3. Download the backup file

**External destination payload (multi-destination):**
Send `external_destinations` in `PUT /api/backup/schedule` as a list of objects:
- `name` (string)
- `provider` (currently `webdav`)
- `enabled` (boolean)
- `external_url` (HTTPS required)
- `external_api_key` (supports `username:app-password`)
- `external_path` (destination folder path)

When multiple destinations are configured, manual and scheduled backups upload to all enabled targets and return per-destination success/error details.

Destination order is significant: the first enabled destination is treated as primary for legacy compatibility fields (`external_url`, `external_path`) while all enabled destinations are used for backup uploads.

**Admin full-state export/import:**
1. POST `/api/backup/system/export` to download a portable archive containing a PostgreSQL logical dump plus `volumes/attachments` and `volumes/uploads`
2. POST `/api/backup/system/import` with the `.tar.gz` archive to restore the entire deployment elsewhere
3. API responses include stable `message_key` values for frontend localization

### Restore from Backup

**Using the web interface (recommended):**
1. Go to Settings > Backup
2. Click "Restore"
3. Upload your backup file
4. Choose merge or replace mode

The web restore runs inside the container against the embedded database, so no
CLI restore script is needed. For a full deployment move, use the admin
full-state export/import endpoints described above.

### Backup Regression Tests

Run backend tests for `external_destinations` validation and API-key preservation behavior:

```bash
cd backend
pytest tests/test_backup_external_destinations.py -q
```

---

## Tech Stack

### Backend
| Component | Technology | Purpose |
|-----------|------------|---------|
| **Framework** | Flask 3.0 | Web framework & REST API |
| **Database** | PostgreSQL 16 | Primary data storage |
| **Cache** | Redis 7 | Sessions, rate limiting, caching |
| **ORM** | SQLAlchemy 2.x | Database abstraction |
| **Server** | Gunicorn | Production WSGI server |
| **Auth** | JWT + bcrypt | Authentication |
| **2FA** | PyOTP | TOTP authentication |
| **Email** | Flask-Mail | Transactional emails |
| **PDF** | ReportLab | Report generation |
| **Security** | Flask-Talisman | Security headers |
| **OCR** | pytesseract + Pillow + NumPy | Receipt text extraction with illumination-normalised preprocessing |
| **GeoIP** | geoip2 + GeoLite2 | Suspicious-login country detection |

### Frontend
| Component | Technology | Purpose |
|-----------|------------|---------|
| **Framework** | React 18 | UI library |
| **Build** | Vite | Fast build tool |
| **Styling** | TailwindCSS | Utility-first CSS |
| **PWA** | Workbox | Service workers |
| **Offline DB** | Dexie.js | IndexedDB wrapper |
| **i18n** | i18next | Internationalization |

### Infrastructure
| Component | Technology | Purpose |
|-----------|------------|---------|
| **Containers** | Docker | Containerization |
| **Orchestration** | Docker Compose | Multi-container management |
| **AI (Optional)** | Ollama | Local LLM inference (predictions, OCR parsing, anomaly detection) |

---

## API Documentation

Base URL: `/api/`

### Authentication
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/register` | POST | Register new user |
| `/api/auth/login` | POST | Login (returns JWT) |
| `/api/auth/logout` | POST | Logout (blacklists token) |
| `/api/auth/refresh` | POST | Refresh access token |
| `/api/auth/me` | GET | Get current user |

### Vehicles
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/vehicles` | GET | List user's vehicles |
| `/api/vehicles` | POST | Create vehicle |
| `/api/vehicles/<id>` | GET | Get vehicle details |
| `/api/vehicles/<id>` | PUT | Update vehicle |
| `/api/vehicles/<id>` | DELETE | Delete vehicle |

### Entries
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/fuel` | GET/POST | Fuel entries |
| `/api/services` | GET/POST | Service entries |
| `/api/repairs` | GET/POST | Repair entries |
| `/api/insurance` | GET/POST | Insurance policies |
| `/api/taxes` | GET/POST | Tax entries |
| `/api/parking` | GET/POST | Parking entries |

### Other
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/reminders` | GET/POST | Reminders |
| `/api/attachments` | GET/POST | File attachments |
| `/api/attachments/<id>/ocr` | GET | Get OCR-extracted text for an attachment |
| `/api/attachments/<id>/ocr/retry` | POST | Re-trigger OCR scan for an attachment |
| `/api/reports/generate` | POST | Generate PDF report |
| `/api/backup/export` | POST | Export backup |

### AI Endpoints (requires `OLLAMA_ENABLED=true`)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/predictions/generate` | POST | Manually trigger AI maintenance predictions for a vehicle |
| `/api/predictions/status` | GET | Ollama connectivity status and available models |
| `/api/vehicles/<id>/suggest-reminder` | POST | Get 3 AI-generated reminder suggestions |
### Widget API (Gethomepage)
| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/widget/v1/homepage` | GET | API Key | Summary stats (vehicles, services, reminders) |
| `/api/widget/v1/vehicles` | GET | API Key | Per-vehicle detail stats |
| `/api/widget/api-key` | POST | JWT | Generate/regenerate API key |
| `/api/widget/api-key` | GET | JWT | Get current API key |
| `/api/widget/api-key` | DELETE | JWT | Revoke API key |

### Import
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/backup/import/lubelog` | POST | Import LubeLogger backup (.zip) |
---

## Project Structure

```
gearcargo/
├── backend/
│   ├── app/
│   │   ├── __init__.py       # App factory
│   │   ├── config.py         # Configuration
│   │   ├── models/           # Database models
│   │   ├── routes/           # API endpoints
│   │   ├── services/         # Background services
│   │   ├── templates/        # Email templates
│   │   └── utils/            # Utilities
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── pages/            # React pages
│   │   ├── components/       # Reusable components
│   │   ├── contexts/         # React contexts
│   │   ├── hooks/            # Custom hooks
│   │   ├── services/         # API services
│   │   ├── i18n/             # Translations
│   │   └── db/               # IndexedDB (Dexie)
│   └── package.json
├── volumes/                   # Persistent data
│   ├── pgdata/               # PostgreSQL data (single image)
│   ├── redis/                # Redis data
│   ├── attachments/          # User uploads
│   └── backups/              # Backup archives
├── docker-compose.yml         # Standard install — pulls the single image
├── docker-compose.dev.yml  # Dev — builds the single image locally
├── examples/                  # Full .env reference (examples/.env.reference)
├── Dockerfile                 # The single all-in-one image
├── setup.sh                   # Guided installer
└── scripts/                   # Utility scripts (docker-backup.sh, migration, maintenance)
```

---

## Updating

### Standard (pre-built single image)
```bash
docker compose pull
docker compose up -d
```
(Synology: prefix with `sudo`.)

### Development (build from source)
```bash
git pull
docker compose -f docker-compose.dev.yml up -d --build
```

---

## Troubleshooting

### Container won't start
```bash
# Check logs
docker compose logs backend

# Check health
docker compose ps

# Restart all services
docker compose down && docker compose up -d
```

### Database connection errors
```bash
# Check if DB is healthy
docker compose exec db pg_isready -U gearcargo

# Check DB logs
docker compose logs db
```

### Redis connection errors
```bash
# Test Redis connection
docker compose exec redis redis-cli -a \$REDIS_PASSWORD ping
```

### Permission errors on volumes
```bash
# Fix ownership (use your user ID)
sudo chown -R 1000:1000 ./volumes/
```

---

## License

**Proprietary Software - All Rights Reserved**

Copyright © 2024-2026 GearCargo. All rights reserved.

This software and its source code are proprietary and confidential. Unauthorized copying, modification, distribution, or use of this software, via any medium, is strictly prohibited without prior written permission from the copyright holder.

- No redistribution allowed
- No modification for commercial use
- No derivative works
- No sublicensing

For licensing inquiries, contact: licensing@gearcargo.app

---

## Support

- Email: support@gearcargo.app
- Issues: [GitHub Issues](https://github.com/aiulian25/GearCargo/issues)
- Discussions: [GitHub Discussions](https://github.com/aiulian25/GearCargo/discussions)

---

Made for vehicle enthusiasts

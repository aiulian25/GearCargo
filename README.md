# GearCargo 🚗

A comprehensive vehicle management Progressive Web App (PWA) for tracking fuel consumption, services, repairs, insurance, taxes, and all vehicle-related expenses.

![GearCargo](./frontend/public/icons/icon-192x192.png)

---

## 🚀 Quick Deploy with Pre-built Image

**New to GearCargo? Deploy in 2 minutes with our pre-built image!**

```bash
# Download deployment files
wget https://raw.githubusercontent.com/aiulian25/gearcargo/main/docker-compose.deploy.yml
wget https://raw.githubusercontent.com/aiulian25/gearcargo/main/.env.production

# Edit configuration
nano .env.production
# Set your credentials, domains, and secrets

# Create directories
mkdir -p volumes/{db,redis,attachments,backups,uploads}

# Start (pulls image from ghcr.io)
docker compose -f docker-compose.deploy.yml --env-file .env.production up -d

# Check logs
docker compose -f docker-compose.deploy.yml logs -f backend
```

✨ **Features:**
- ⚡ No build time - image pre-built on GitHub
- 🗄️ Database auto-initialized on first start
- 👤 Admin user auto-created from environment variables
- 🔒 Production-ready security settings
- 📅 Calendar sync enabled by default for admin
- 🔔 Push notifications ready to configure

See [Deployment Options](#deployment-options) for details.

---

## Quick Start (Recommended Method)

- [Features](#features)
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

### 🚗 Vehicle Management
- Multiple vehicle profiles with photos and detailed specs
- Track mileage, fuel type, engine size, transmission
- Vehicle timeline with all activities
- Archive/restore vehicles
- Drag-and-drop vehicle reordering on dashboard

### ⛽ Fuel Tracking
- Log fuel entries with automatic consumption calculation
- Track fuel costs and efficiency (L/100km or MPG)
- Price comparison by station
- Full tank vs partial fill tracking
- Station location and address storage

### 🔧 Service & Repair Logs
- Scheduled service tracking (oil changes, filters, etc.)
- Repair history with warranty tracking
- Parts and labor cost breakdown
- Service provider/shop information
- Mileage-based service intervals

### 🛡️ Insurance Management
- Track multiple insurance policies per vehicle
- Policy expiration alerts
- Coverage details and premium tracking
- Document attachment support

### 💰 Tax & Registration
- Vehicle tax payment tracking
- Registration renewal reminders
- Road tax calculations
- MOT/inspection tracking

### 🅿️ Parking & Tolls
- Parking expense logging
- Toll payment tracking
- Location-based entries

### ⏰ Smart Reminders
- Date-based reminders (insurance renewal, tax due)
- Mileage-based reminders (service intervals)
- Push notifications (browser & mobile)
- Email notifications
- Calendar integration (CalDAV - Google, Nextcloud, Baikal, Radicale)
- Multi-language reminder translations

### 📊 Analytics & Reports
- Cost breakdown by category (fuel, service, repairs, insurance, tax)
- Monthly/yearly expense reports
- PDF report generation with charts
- Fuel efficiency trends
- Cost per kilometer/mile analysis

### 🤖 AI-Powered Features (Optional)
- Maintenance predictions based on vehicle history
- Smart alerts for potential issues
- OCR for receipt scanning
- Powered by Ollama (local or external)

### 📎 Attachments & Documents
- Attach receipts, invoices, documents to any entry
- Image preview and gallery view
- PDF document support
- Organized by vehicle and entry type

### ✅ To-Do Lists
- Vehicle-specific task lists
- Priority levels and due dates
- Completion tracking

### 🔒 Security Features
- **Two-Factor Authentication (2FA)** - TOTP with backup codes
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

### 💾 Data Management
- Automatic scheduled backups
- Manual backup/restore
- Export to external servers (HTTPS)
- JSON and ZIP backup formats
- Import from backup files
- Data migration tools

### 📱 Mobile-First PWA
- Installable on any device (iOS, Android, Desktop)
- Works offline with service workers
- Push notifications
- Touch-optimized compact UI
- Dark and light themes

### 🌐 Internationalization
- Multi-language support (English, Romanian, Spanish)
- Customizable date formats
- Multiple currency support (EUR, GBP, USD, RON, etc.)
- Distance units (km/miles)
- Volume units (liters/gallons)

---

## Quick Start (Recommended Method)

### Prerequisites
- Docker & Docker Compose v2+
- Git
- 2GB RAM minimum (4GB recommended with Ollama)

### Automated Setup

```bash
# Clone the repository
git clone https://github.com/aiulian25/GearCargo.git
cd gearcargo

# Run the setup script (generates credentials automatically)
chmod +x setup.sh
./setup.sh

# Access at http://localhost:5000
```

The setup script will:
1. Check prerequisites
2. Generate all required secret keys
3. Generate VAPID keys for push notifications
4. Ask about Ollama AI configuration
5. Build and start all containers
6. Run database migrations

---

## Table of Contents

GearCargo provides **multiple deployment configurations** for different use cases:

---

### 🚀 Option 1: Pre-built Image from GitHub (Recommended for Production)

Pull the latest pre-built image from GitHub Container Registry - **no build required!**

**Best for:** Quick deployment, production servers, testing

\`\`\`bash
# 1. Download deployment files
wget https://raw.githubusercontent.com/aiulian25/gearcargo/main/docker-compose.test.yml
wget https://raw.githubusercontent.com/aiulian25/gearcargo/main/.env.test

# 2. Customize your configuration
nano .env.test
# Edit: ADMIN_EMAIL, ADMIN_PASSWORD, domains, etc.

# 3. Create required directories
mkdir -p volumes/{db,redis,attachments,backups,uploads}

# 4. Start the application (image will be pulled automatically)
docker compose -f docker-compose.test.yml --env-file .env.test up -d

# 5. Check startup logs
docker compose -f docker-compose.test.yml logs -f backend

# Look for:
#   "Running database migrations..."
#   "Database migrations complete."
#   "Default admin user created: admin@test.local"
\`\`\`

**What happens on first startup:**
1. 🐳 Docker pulls pre-built image from `ghcr.io/aiulian25/gearcargo:latest`
2. 🗄️ Database migrations run automatically (creates all tables)
3. 👤 Admin user is created from your `.env.test` credentials
4. 🚀 Application starts and is ready to use!

**Default admin credentials** (from `.env.test`):
- Email: `admin@test.local`
- Password: `TestAdmin123!`
- ⚠️ **Change these immediately after first login!**

**Features:**
- ✅ No build time (image pre-built on GitHub)
- ✅ Automatic database initialization
- ✅ Production-ready configuration
- ✅ HTTPS support (set `SESSION_COOKIE_SECURE=true`)
- ✅ Domain-based access control
- ✅ Smaller resource footprint

---

### Option 2: Development (\`docker-compose.yml\`)

Best for: Local development, testing, feature development

\`\`\`bash
# Basic startup (no AI)
docker compose up -d --build

# With local Ollama AI
docker compose --profile ollama-local up -d --build

# With external Ollama server
# Set OLLAMA_BASE_URL in .env first, then:
docker compose up -d --build
\`\`\`

**Features:**
- Debug mode enabled
- Hot-reload for development
- Verbose logging
- All features available

---

### Option 3: Production with AI (\`docker-compose.prod.yml\`)

Best for: Full-featured production deployment with AI predictions

\`\`\`bash
# 1. Copy and configure production environment
cp .env.production .env
nano .env  # Edit all required values

# 2. Build the image
docker compose -f docker-compose.prod.yml build

# 3. Start services
docker compose -f docker-compose.prod.yml up -d

# 4. View logs
docker compose -f docker-compose.prod.yml logs -f backend
\`\`\`

**Features:**
- Production-optimized settings
- Resource limits (CPU/memory)
- Log rotation
- Health checks
- Optional Ollama AI integration
- HTTPS-ready session cookies

---

### Option 4: Simple Production (\`docker-compose.simple.yml\`)

Best for: Lightweight production without AI features

\`\`\`bash
# 1. Copy and configure simple environment
cp .env.simple .env
nano .env  # Edit all required values

# 2. Build the image
docker compose -f docker-compose.simple.yml build

# 3. Start services
docker compose -f docker-compose.simple.yml up -d

# 4. View logs
docker compose -f docker-compose.simple.yml logs -f backend
\`\`\`

**Features:**
- Minimal resource usage
- No Ollama dependency
- Production-hardened
- Ideal for VPS/small servers

---

### Deployment File Comparison

| Feature | Pre-built Image | \`docker-compose.yml\` | \`docker-compose.prod.yml\` | \`docker-compose.simple.yml\` |
|---------|----------------|---------------------|---------------------------|----------------------------|
| **Use Case** | **Quick Production** | Development | Full Production | Lightweight Production |
| **Build Time** | ⚡ **None (pre-built)** | ~2-5 minutes | ~2-5 minutes | ~2-5 minutes |
| **Image Source** | `ghcr.io` | Local build | Local build | Local build |
| **Auto Migrations** | ✅ **Yes** | Manual | Manual | Manual |
| **Debug Mode** | ❌ Disabled | ✅ Enabled | ❌ Disabled | ❌ Disabled |
| **Ollama AI** | ❌ Disabled | Optional | Optional | ❌ Disabled |
| **Resource Limits** | 2 CPU, 1GB RAM | None | 2 CPU, 1GB RAM | 2 CPU, 1GB RAM |
| **Log Rotation** | Yes (10MB × 3) | No | Yes (10MB × 3) | Yes (10MB × 3) |
| **Session Security** | Strict (HTTPS) | Relaxed | Strict (HTTPS) | Strict (HTTPS) |
| **Rate Limiting** | 100/hour | 200/day | 100/hour | 100/hour |
| **Best For** | 🚀 **Production VPS** | Local dev | AI features | Minimal setup |

---

## Credential Generation

### Required Secrets

GearCargo requires several cryptographic secrets. **Never use default values in production!**

#### 1. SECRET_KEY (Flask session encryption)

\`\`\`bash
# Using Python
python3 -c "import secrets; print(secrets.token_hex(32))"

# Using OpenSSL
openssl rand -hex 32

# Example output: a1b2c3d4e5f6...64 characters
\`\`\`

#### 2. JWT_SECRET_KEY (JWT token signing)

\`\`\`bash
python3 -c "import secrets; print(secrets.token_hex(32))"
# or
openssl rand -hex 32
\`\`\`

#### 3. WTF_CSRF_SECRET_KEY (CSRF protection)

\`\`\`bash
python3 -c "import secrets; print(secrets.token_hex(32))"
# or
openssl rand -hex 32
\`\`\`

#### 4. ENCRYPTION_KEY (Data encryption at rest)

\`\`\`bash
python3 -c "import secrets; print(secrets.token_hex(32))"
# or
openssl rand -hex 32
\`\`\`

#### 5. DB_PASSWORD (PostgreSQL password)

\`\`\`bash
# Generate a strong password
python3 -c "import secrets; print(secrets.token_urlsafe(24))"
# or
openssl rand -base64 24
\`\`\`

#### 6. REDIS_PASSWORD (Redis authentication)

\`\`\`bash
python3 -c "import secrets; print(secrets.token_urlsafe(24))"
# or
openssl rand -base64 24
\`\`\`

#### 7. VAPID Keys (Push notifications)

VAPID keys are required for web push notifications. Generate them using:

**Method 1: Using web-push CLI (Recommended)**
\`\`\`bash
# Install web-push globally
npm install -g web-push

# Generate VAPID keys
web-push generate-vapid-keys

# Output:
# Public Key: BNx...
# Private Key: abc...
\`\`\`

**Method 2: Using Python**
\`\`\`bash
pip install py-vapid

python3 -c "
from py_vapid import Vapid
v = Vapid()
v.generate_keys()
print('VAPID_PUBLIC_KEY=' + v.public_key.public_bytes_raw().hex())
print('VAPID_PRIVATE_KEY=' + v.private_key.private_bytes_raw().hex())
"
\`\`\`

**Method 3: Online Generator**
Visit https://vapidkeys.com/ (use only for testing)

---

### Complete .env Example

\`\`\`bash
# ===========================================
# GEARCARGO ENVIRONMENT CONFIGURATION
# ===========================================

# Application
APP_URL=https://gearcargo.yourdomain.com
APP_PORT=5000

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
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2

# Theme
DEFAULT_THEME=dark
\`\`\`

---

## Admin User Setup

GearCargo supports **two methods** for creating the initial admin user:

### Method 1: Environment Variables (Automatic - Recommended) ✨

**With the pre-built image** (`docker-compose.test.yml`), admin creation is **fully automatic!**

The `.env.test` file includes:
```bash
ADMIN_EMAIL=admin@test.local
ADMIN_USERNAME=admin
ADMIN_PASSWORD=TestAdmin123!
```

**What happens automatically on first startup:**
1. 🗄️ Database tables are created via migrations
2. 👤 Admin user is created if no users exist
3. 🚀 Application starts ready to use

**Security Notes:**
- ⚠️ **Change default password immediately after first login!**
- Password must be at least 8 characters
- The admin user has full admin privileges (`is_admin=true`)
- After login, update credentials in Settings → Account

**For custom credentials:**
Edit `.env.test` before first startup:
```bash
ADMIN_EMAIL=admin@yourdomain.com
ADMIN_USERNAME=admin
ADMIN_PASSWORD=YourSecurePassword123!
```

---

### Method 2: Self-Registration (First User Becomes Admin)

If no \`ADMIN_EMAIL\`/\`ADMIN_PASSWORD\` environment variables are set:

1. Start the containers normally
2. Navigate to http://localhost:5000/register
3. **The first user to register automatically becomes the admin**
4. All subsequent registrations create regular users

**Security Note:** This method is simpler but requires you to register immediately after deployment to prevent unauthorized admin creation.

### Verifying Admin Status

After creating the admin, verify in the logs:

\`\`\`bash
docker compose logs backend | grep -i admin

# Expected output:
# Default admin user created: admin@yourdomain.com
# IMPORTANT: Change the admin password immediately and remove ADMIN_PASSWORD from environment!
\`\`\`

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
| \`SECRET_KEY\` | ✅ Yes | Flask secret key (64 hex chars) | - |
| \`JWT_SECRET_KEY\` | ✅ Yes | JWT signing key (64 hex chars) | - |
| \`DB_PASSWORD\` | ✅ Yes | PostgreSQL password | - |
| \`REDIS_PASSWORD\` | ✅ Yes | Redis password | \`changeme\` |
| \`APP_URL\` | ✅ Yes | Public URL of your app | \`http://localhost:5000\` |
| \`CORS_ORIGINS\` | ✅ Yes | Allowed origins (comma-separated) | \`http://localhost:5000\` |
| \`WTF_CSRF_SECRET_KEY\` | ⚠️ Recommended | CSRF secret | Falls back to SECRET_KEY |
| \`ENCRYPTION_KEY\` | ⚠️ Recommended | Data encryption key | - |
| \`ADMIN_EMAIL\` | Optional | Auto-create admin email | - |
| \`ADMIN_PASSWORD\` | Optional | Auto-create admin password | - |
| \`MAIL_ENABLED\` | Optional | Enable email features | \`false\` |
| \`VAPID_PUBLIC_KEY\` | Optional | Push notification public key | - |
| \`VAPID_PRIVATE_KEY\` | Optional | Push notification private key | - |
| \`OLLAMA_ENABLED\` | Optional | Enable AI features | \`false\` |
| \`OLLAMA_BASE_URL\` | Optional | Ollama server URL | \`http://host.docker.internal:11434\` |

### JWT Token Expiration

| Variable | Description | Default |
|----------|-------------|---------|
| \`JWT_ACCESS_TOKEN_EXPIRES\` | Access token lifetime (seconds) | \`3600\` (1 hour) |
| \`JWT_REFRESH_TOKEN_EXPIRES\` | Refresh token lifetime (seconds) | \`2592000\` (30 days) |

### Rate Limiting

| Variable | Description | Default |
|----------|-------------|---------|
| \`RATELIMIT_ENABLED\` | Enable rate limiting | \`true\` |
| \`RATELIMIT_DEFAULT\` | Default rate limit | \`200 per day\` (dev) / \`100 per hour\` (prod) |

---

## Backup & Restore

### Automatic Backups

Configure automatic backups in Settings > Backup:
- Schedule daily/weekly backups
- Set retention period
- Configure external backup server (HTTPS)

### Manual Backup

**Using the backup script:**
\`\`\`bash
./backup.sh
# Creates: ./volumes/backups/gearcargo_backup_YYYYMMDD_HHMMSS.tar.gz
\`\`\`

**Using the web interface:**
1. Go to Settings > Backup
2. Click "Create Backup"
3. Download the backup file

### Restore from Backup

**Using the restore script:**
\`\`\`bash
./restore.sh ./volumes/backups/gearcargo_backup_20240115_120000.tar.gz
\`\`\`

**Using the web interface:**
1. Go to Settings > Backup
2. Click "Restore"
3. Upload your backup file
4. Choose merge or replace mode

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
| **AI (Optional)** | Ollama | Local LLM inference |

---

## API Documentation

Base URL: \`/api/\`

### Authentication
| Endpoint | Method | Description |
|----------|--------|-------------|
| \`/api/auth/register\` | POST | Register new user |
| \`/api/auth/login\` | POST | Login (returns JWT) |
| \`/api/auth/logout\` | POST | Logout (blacklists token) |
| \`/api/auth/refresh\` | POST | Refresh access token |
| \`/api/auth/me\` | GET | Get current user |

### Vehicles
| Endpoint | Method | Description |
|----------|--------|-------------|
| \`/api/vehicles\` | GET | List user's vehicles |
| \`/api/vehicles\` | POST | Create vehicle |
| \`/api/vehicles/<id>\` | GET | Get vehicle details |
| \`/api/vehicles/<id>\` | PUT | Update vehicle |
| \`/api/vehicles/<id>\` | DELETE | Delete vehicle |

### Entries
| Endpoint | Method | Description |
|----------|--------|-------------|
| \`/api/fuel\` | GET/POST | Fuel entries |
| \`/api/services\` | GET/POST | Service entries |
| \`/api/repairs\` | GET/POST | Repair entries |
| \`/api/insurance\` | GET/POST | Insurance policies |
| \`/api/taxes\` | GET/POST | Tax entries |
| \`/api/parking\` | GET/POST | Parking entries |

### Other
| Endpoint | Method | Description |
|----------|--------|-------------|
| \`/api/reminders\` | GET/POST | Reminders |
| \`/api/attachments\` | GET/POST | File attachments |
| \`/api/reports/generate\` | POST | Generate PDF report |
| \`/api/backup/export\` | POST | Export backup |

---

## Project Structure

\`\`\`
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
│   ├── db/                   # PostgreSQL data
│   ├── redis/                # Redis data
│   ├── attachments/          # User uploads
│   └── backups/              # Backup files
├── docker-compose.yml         # Development config
├── docker-compose.prod.yml    # Production config
├── docker-compose.simple.yml  # Simple production
├── Dockerfile                 # Multi-stage build
├── setup.sh                   # Setup script
├── backup.sh                  # Backup script
└── restore.sh                 # Restore script
\`\`\`

---

## Updating

### Development
\`\`\`bash
git pull
docker compose up -d --build
\`\`\`

### Production
\`\`\`bash
git pull
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d --force-recreate
docker compose -f docker-compose.prod.yml logs -f backend
\`\`\`

---

## Troubleshooting

### Container won't start
\`\`\`bash
# Check logs
docker compose logs backend

# Check health
docker compose ps

# Restart all services
docker compose down && docker compose up -d
\`\`\`

### Database connection errors
\`\`\`bash
# Check if DB is healthy
docker compose exec db pg_isready -U gearcargo

# Check DB logs
docker compose logs db
\`\`\`

### Redis connection errors
\`\`\`bash
# Test Redis connection
docker compose exec redis redis-cli -a \$REDIS_PASSWORD ping
\`\`\`

### Permission errors on volumes
\`\`\`bash
# Fix ownership (use your user ID)
sudo chown -R 1000:1000 ./volumes/
\`\`\`

---

## Contributing

1. Fork the repository
2. Create a feature branch: \`git checkout -b feature/amazing-feature\`
3. Commit changes: \`git commit -m 'Add amazing feature'\`
4. Push to branch: \`git push origin feature/amazing-feature\`
5. Open a Pull Request

---

## License

**Proprietary Software - All Rights Reserved**

Copyright © 2024-2026 GearCargo. All rights reserved.

This software and its source code are proprietary and confidential. Unauthorized copying, modification, distribution, or use of this software, via any medium, is strictly prohibited without prior written permission from the copyright holder.

- ❌ No redistribution allowed
- ❌ No modification for commercial use
- ❌ No derivative works
- ❌ No sublicensing

For licensing inquiries, contact: licensing@gearcargo.app

---

## Support

- 📧 Email: support@gearcargo.app
- 🐛 Issues: [GitHub Issues](https://github.com/aiulian25/GearCargo/issues)
- 💬 Discussions: [GitHub Discussions](https://github.com/aiulian25/GearCargo/discussions)

---

Made with ❤️ for vehicle enthusiasts

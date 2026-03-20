# GearCargo — Deployment Guide

Complete step-by-step guide to deploy GearCargo on any Docker-capable machine — Linux servers, Synology NAS, cloud VMs, or Raspberry Pi.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Download the Compose File](#2-download-the-compose-file)
3. [Create Data Directories](#3-create-data-directories)
4. [Configure Environment Variables](#4-configure-environment-variables)
   - [4.1 Generate Secrets](#41-generate-secrets)
   - [4.2 Application Settings](#42-application-settings)
   - [4.3 Domain-Based Access Control](#43-domain-based-access-control)
   - [4.4 User / Group IDs](#44-user--group-ids-important-for-synology--nas)
   - [4.5 Change the Default Port](#45-change-the-default-port)
   - [4.6 Email (SMTP)](#46-email-smtp)
   - [4.7 Push Notifications (VAPID Keys)](#47-push-notifications-vapid-keys)
   - [4.8 AI Features (Ollama)](#48-ai-features-ollama---optional)
   - [4.9 Admin Account Bootstrap](#49-admin-account-bootstrap)
5. [Login to GitHub Container Registry](#5-login-to-github-container-registry)
6. [Start the Application](#6-start-the-application)
7. [Verify the Deployment](#7-verify-the-deployment)
8. [Post-Install Steps](#8-post-install-steps)
9. [Reverse Proxy Setup](#9-reverse-proxy-setup)
10. [Updating to a New Version](#10-updating-to-a-new-version)
11. [Backup & Restore](#11-backup--restore)
12. [Troubleshooting](#12-troubleshooting)
13. [Platform-Specific Notes](#13-platform-specific-notes)
14. [Complete .env Reference](#14-complete-env-reference)

---

## 1. Prerequisites

- **Docker Engine** 20.10+ and **Docker Compose** v2
- At least **1 GB RAM** and **2 GB disk** free
- A terminal / SSH session on the target machine

Verify Docker is installed:

```bash
docker --version
docker compose version
```

If not installed, follow the official guide: https://docs.docker.com/engine/install/

---

## 2. Download the Compose File

Create a directory for GearCargo and download the compose file:

```bash
mkdir -p ~/gearcargo && cd ~/gearcargo

curl -fsSL https://raw.githubusercontent.com/aiulian25/gearcargo/main/docker-compose.deploy.yml -o docker-compose.yml
```

> **Synology / Portainer users:** You can paste the compose file directly into the Stacks UI instead. See [Platform-Specific Notes](#13-platform-specific-notes).

---

## 3. Create Data Directories

GearCargo needs six directories to persist data between container restarts. The container runs as **UID 1000** (non-root), so the backend directories must be owned by that UID.

```bash
# Create all directories
mkdir -p volumes/{db,redis,attachments,backups,uploads,logs}
```

Set correct ownership on the directories the backend writes to:

```bash
# Linux / standard Docker
sudo chown -R 1000:1000 volumes/attachments volumes/backups volumes/uploads volumes/logs
```

> **Why UID 1000?** The container runs with `user: "1000:1000"` and `no-new-privileges` security policy, which means it cannot change its own user at runtime. All writable directories must be pre-owned by this UID.
>
> **Custom UID (Synology, etc.):** If your system user has a different UID, see [Section 4.4](#44-user--group-ids-important-for-synology--nas).

| Directory | Purpose | Written by |
|-----------|---------|------------|
| `volumes/db` | PostgreSQL database files | postgres container (manages its own permissions) |
| `volumes/redis` | Redis persistence (AOF + RDB) | redis container (manages its own permissions) |
| `volumes/attachments` | Uploaded vehicle documents, receipts | backend (UID 1000) |
| `volumes/backups` | Database backup archives | backend (UID 1000) |
| `volumes/uploads` | User avatars, vehicle photos | backend (UID 1000) |
| `volumes/logs` | Security audit logs | backend (UID 1000) |

---

## 4. Configure Environment Variables

Copy the template and edit it:

```bash
curl -fsSL https://raw.githubusercontent.com/aiulian25/gearcargo/main/.env.production -o .env
nano .env     # or vi, micro, etc.
```

Below are all the sections you need to configure. **At minimum, you must change all passwords and secret keys.**

---

### 4.1 Generate Secrets

GearCargo needs four unique secret keys. **Each must be different.** Generate them with any of these methods:

```bash
# Method 1: Python (most systems)
python3 -c "import secrets; print(secrets.token_hex(32))"

# Method 2: OpenSSL
openssl rand -hex 32

# Method 3: /dev/urandom (any Linux)
head -c 32 /dev/urandom | xxd -p -c 64
```

Run the command **four times** and paste each result into your `.env`:

```env
SECRET_KEY=<paste-first-key-here>
JWT_SECRET_KEY=<paste-second-key-here>
WTF_CSRF_SECRET_KEY=<paste-third-key-here>
ENCRYPTION_KEY=<paste-fourth-key-here>
```

Generate passwords for the database and Redis:

```bash
# Passwords (URL-safe, no special chars that might break connection strings)
python3 -c "import secrets; print(secrets.token_urlsafe(24))"
# or
openssl rand -base64 24
```

```env
DB_PASSWORD=<paste-db-password-here>
REDIS_PASSWORD=<paste-redis-password-here>
```

> **Warning:** Once you start the application, do NOT change `DB_PASSWORD` or `REDIS_PASSWORD` — the database and Redis are already initialized with those values. Changing them will lock you out. If you must change them, you need to update the password inside PostgreSQL/Redis first.

---

### 4.2 Application Settings

```env
# The public URL users will access (used for CORS, links in emails, etc.)
APP_URL=https://car.yourdomain.com

# CORS — which origins can make API requests
# Must include your APP_URL. Comma-separated, no spaces.
CORS_ORIGINS=https://car.yourdomain.com

# Cookie security — set to true ONLY if using HTTPS
SESSION_COOKIE_SECURE=true

# Rate limiting (protects against brute force)
RATELIMIT_DEFAULT=200 per day
```

If you're running without HTTPS (e.g., local network only):

```env
APP_URL=http://192.168.1.50:5000
CORS_ORIGINS=http://192.168.1.50:5000
SESSION_COOKIE_SECURE=false
SESSION_COOKIE_SAMESITE=Lax
```

---

### 4.3 Domain-Based Access Control

If you serve GearCargo on two domains — one for admins (e.g., `admin.yourdomain.com`) and one for regular users (e.g., `car.yourdomain.com`) — you can enforce strict domain separation:

```env
ADMIN_DOMAIN=admin.yourdomain.com
USER_DOMAIN=car.yourdomain.com
```

With this configured:
- **Admins can only log in** on the admin domain
- **Regular users can only log in** on the user domain
- **First admin registration** is only accepted on the admin domain
- Attempting to log in on the wrong domain returns an access denied error

**If you use a single domain**, leave both empty:

```env
ADMIN_DOMAIN=
USER_DOMAIN=
```

---

### 4.4 User / Group IDs (Important for Synology / NAS)

The container runs as a non-root user. By default, this is **UID 1000 / GID 1000** (the `gearcargo` user built into the image). On most Linux servers, this matches the first non-root user.

**To find your system's UID/GID:**

```bash
id
# Output: uid=1000(ubuntu) gid=1000(ubuntu) ...
```

**If your UID is NOT 1000** (common on Synology DSM where the admin user is UID 1026, or on some cloud VMs):

You need to edit the `user:` line in `docker-compose.yml`:

```yaml
services:
  backend:
    # Change 1000:1000 to your UID:GID
    user: "1026:100"
```

Then set the volume ownership to match:

```bash
sudo chown -R 1026:100 volumes/attachments volumes/backups volumes/uploads volumes/logs
```

**Synology DSM common UIDs:**
| User | UID | GID |
|------|-----|-----|
| admin | 1024 | 100 |
| First user | 1026 | 100 (users group) |

> **Tip:** On Synology, you can also check UID via SSH: `id youruser`

---

### 4.5 Change the Default Port

The backend listens on port **5000** inside the container. To change the host port (e.g., if port 5000 is already in use):

```env
APP_PORT=8080
```

This maps `host:8080 → container:5000`. Update `APP_URL` and `CORS_ORIGINS` to match:

```env
APP_URL=https://yourdomain.com:8080
CORS_ORIGINS=https://yourdomain.com:8080
```

If you're using a **reverse proxy** (Nginx, Caddy, Traefik), the proxy handles the public port and you don't need to change `APP_PORT`. Just map the internal port:

```env
APP_PORT=5000
APP_URL=https://yourdomain.com    # no port — proxy handles 443→5000
CORS_ORIGINS=https://yourdomain.com
```

---

### 4.6 Email (SMTP)

Email is required for password resets and notifications. If you don't need email, set `MAIL_ENABLED=false` and skip this section.

**Gmail example:**

1. Enable 2-Factor Authentication on your Google account
2. Generate an App Password: https://myaccount.google.com/apppasswords
3. Configure:

```env
MAIL_ENABLED=true
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=yourname@gmail.com
MAIL_PASSWORD=abcd-efgh-ijkl-mnop    # 16-char App Password, NOT your Google password
MAIL_DEFAULT_SENDER=GearCargo <yourname@gmail.com>
```

**Other SMTP providers:**

| Provider | Server | Port | TLS |
|----------|--------|------|-----|
| Gmail | smtp.gmail.com | 587 | true |
| Outlook/Hotmail | smtp.office365.com | 587 | true |
| Yahoo | smtp.mail.yahoo.com | 587 | true |
| Mailgun | smtp.mailgun.org | 587 | true |
| SendGrid | smtp.sendgrid.net | 587 | true |

---

### 4.7 Push Notifications (VAPID Keys)

Push notifications require VAPID (Voluntary Application Server Identification) keys. Generate them once:

```bash
# Method 1: npx (if Node.js is installed)
npx web-push generate-vapid-keys

# Method 2: Python
pip install py-vapid
python3 -c "
from py_vapid import Vapid
v = Vapid()
v.generate_keys()
print('Public:', v.public_key.public_bytes_raw().hex())
print('Private:', v.private_key.private_bytes_raw().hex())
"
```

Paste the keys into your `.env`:

```env
VAPID_PUBLIC_KEY=BNxG3...your-public-key
VAPID_PRIVATE_KEY=abc123...your-private-key
VAPID_SUBJECT=mailto:yourname@gmail.com
```

> **Note:** If you don't need push notifications (reminders, service alerts), leave these empty. The app will work without them — push features will just be unavailable.

---

### 4.8 AI Features (Ollama) — Optional

GearCargo can use Ollama for AI-powered predictions (maintenance forecasts, cost estimates). This is entirely optional.

**Disabled (default):**
```env
OLLAMA_ENABLED=false
```

**Ollama running on the same host:**
```env
OLLAMA_ENABLED=true
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=llama3.2
OLLAMA_TIMEOUT=30
```

**Ollama on a different machine:**
```env
OLLAMA_ENABLED=true
OLLAMA_BASE_URL=http://192.168.1.100:11434
OLLAMA_MODEL=llama3.2
OLLAMA_TIMEOUT=30
```

---

### 4.9 Admin Account Bootstrap

The first user to register becomes the admin. After the admin exists, public registration is permanently disabled (only admins can invite new users).

**Option A — Auto-create via environment (recommended):**

Set these in `.env` before the first start:

```env
ADMIN_EMAIL=admin@yourdomain.com
ADMIN_USERNAME=admin
ADMIN_PASSWORD=YourStrongPassword123!
```

> **Security:** Remove `ADMIN_PASSWORD` from `.env` after the first successful login. The account is already created in the database — the env var is no longer needed.

**Option B — Register via the web UI:**

1. Open the app in your browser
2. Click "Sign Up"
3. The first account that registers becomes admin
4. After that, registration closes automatically

If `ADMIN_DOMAIN` is configured, you **must** register from the admin domain URL.

---

## 5. Login to GitHub Container Registry

The GearCargo image is hosted on GitHub Container Registry (GHCR). If the repository is private, you need a Personal Access Token to pull it.

1. Go to https://github.com/settings/tokens
2. Create a new token (classic) with `read:packages` scope
3. Login:

```bash
echo "ghp_YOUR_TOKEN_HERE" | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
```

> **If the repository is public**, you can skip this step — `docker compose pull` will work without authentication.

---

## 6. Start the Application

```bash
cd ~/gearcargo

# Pull the latest images
docker compose pull

# Start all services
docker compose up -d
```

This starts three containers:
- **gearcargo-backend** — the application (Flask + Gunicorn)
- **gearcargo-db** — PostgreSQL 16 database
- **gearcargo-redis** — Redis 7 cache and session store

The backend will wait for the database and Redis to be healthy before starting, then:
1. Run database migrations
2. Verify all tables and columns exist
3. Start the Gunicorn web server

---

## 7. Verify the Deployment

Wait about 60-90 seconds for the health checks to pass, then:

```bash
# Check all containers are healthy
docker compose ps

# Expected output:
# NAME                STATUS                  IMAGE
# gearcargo-backend   Up 2 minutes (healthy)  ghcr.io/aiulian25/gearcargo:latest
# gearcargo-db        Up 2 minutes (healthy)  postgres:16-alpine
# gearcargo-redis     Up 2 minutes (healthy)  redis:7-alpine
```

Test the health endpoint:

```bash
curl http://localhost:5000/health
```

Check the backend logs for any errors:

```bash
docker compose logs backend
```

A successful startup shows:

```
Starting GearCargo...
Fixing volume permissions...
Waiting for database...
ok
Database is ready.
Running database migrations...
All tables and columns verified.
Database setup complete.
[INFO] Booting worker with pid: 10
[INFO] Booting worker with pid: 11
...
```

---

## 8. Post-Install Steps

1. **Open the app** at your configured `APP_URL` (or `http://YOUR_IP:5000`)
2. **Create your admin account** (register first, or it was auto-created via env vars)
3. **Remove `ADMIN_PASSWORD`** from `.env` if you used auto-bootstrap
4. **Add your first vehicle** and start tracking
5. **Set up a reverse proxy** if exposing to the internet (see next section)

---

## 9. Reverse Proxy Setup

For production use with HTTPS, put a reverse proxy in front of GearCargo.

**Caddy (simplest — auto HTTPS):**

```
car.yourdomain.com {
    reverse_proxy localhost:5000
}
```

**Nginx:**

```nginx
server {
    listen 443 ssl http2;
    server_name car.yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/car.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/car.yourdomain.com/privkey.pem;

    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
    }
}
```

> **Important:** The `X-Forwarded-Host` header is what GearCargo uses for domain-based access control. Your reverse proxy **must** pass the original `Host` header through. Caddy does this automatically. For Nginx, the `proxy_set_header X-Forwarded-Host $host;` line is essential.

**Two-domain setup** (admin + user):

```nginx
# Admin domain
server {
    listen 443 ssl http2;
    server_name admin.yourdomain.com;
    # ... same SSL/proxy config as above ...
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Host $host;
        # ... other headers ...
    }
}

# User domain
server {
    listen 443 ssl http2;
    server_name car.yourdomain.com;
    # ... same config, same proxy_pass target ...
}
```

Both domains point to the same backend — the app uses the Host header to enforce access policies.

---

## 10. Updating to a New Version

```bash
cd ~/gearcargo

# Pull the new image
docker compose pull

# Recreate the backend with the new image
docker compose up -d --force-recreate

# Check logs for migration output
docker compose logs -f backend
```

The entrypoint automatically runs database migrations on every startup, so schema changes are applied seamlessly.

---

## 11. Backup & Restore

**Manual backup:**

```bash
# Database dump
docker compose exec db pg_dump -U gearcargo gearcargo | gzip > backup_$(date +%Y%m%d).sql.gz

# Volumes (attachments, uploads)
tar czf volumes_$(date +%Y%m%d).tar.gz volumes/attachments volumes/uploads volumes/logs
```

**Manual restore:**

```bash
# Stop backend
docker compose stop backend

# Restore database
gunzip -c backup_20260320.sql.gz | docker compose exec -T db psql -U gearcargo gearcargo

# Restore volumes
tar xzf volumes_20260320.tar.gz

# Start backend
docker compose start backend
```

> GearCargo also has a built-in backup feature accessible from the admin panel (Settings → Backups), which saves backups to the `volumes/backups` directory.

---

## 12. Troubleshooting

### Container keeps restarting

```bash
docker compose logs backend --tail 50
```

**Common errors:**

| Error | Cause | Fix |
|-------|-------|-----|
| `Read-only file system: '/app/volumes/logs'` | Missing logs volume mount | Add `./volumes/logs:/app/volumes/logs` to compose volumes |
| `Permission denied: 'security_audit.log'` | Wrong ownership on volumes | `sudo chown -R 1000:1000 volumes/logs` |
| `failed switching to "gearcargo": operation not permitted` | `gosu` blocked by `no-new-privileges` | Add `user: "1000:1000"` to compose backend service |
| `Connection refused` to database | DB not ready yet | Wait — entrypoint retries for 60 seconds |
| `FATAL: password authentication failed` | Wrong `DB_PASSWORD` | Wipe `volumes/db` and restart to re-initialize |
| `NanoCPUs can not be set, as your kernel does not support CPU CFS scheduler` | Synology/older kernels lack CFS | Remove all `deploy:` resource limit blocks from compose |

### Redis health check fails

```bash
docker compose logs redis --tail 20
```

If you see `Permission denied` on `appendonlydir`, the Redis container needs CHOWN capability:

```yaml
# In docker-compose.yml under the redis service:
cap_add:
  - CHOWN
  - DAC_OVERRIDE
  - SETGID
  - SETUID
```

### Can't connect from browser

1. Check the container is healthy: `docker compose ps`
2. Check the port is open: `curl http://localhost:5000/health`
3. Check firewall allows the port: `sudo ufw status` or `sudo iptables -L`
4. If behind a reverse proxy, check proxy logs and ensure `X-Forwarded-Host` is passed

### Wrong domain — "Access denied"

If domain-based access control is enabled and you get "Access denied for this domain":
- Admins must use the `ADMIN_DOMAIN` URL
- Regular users must use the `USER_DOMAIN` URL
- Check your reverse proxy is passing the correct `Host` / `X-Forwarded-Host` header

---

## 13. Platform-Specific Notes

### Synology DSM (Container Manager / SSH)

#### Quick Path — Container Manager UI

1. **Create a project** in Container Manager → Project → Create
2. Paste the contents of `docker-compose.deploy.yml` and your `.env` values
3. **Remove all `deploy:` blocks** (CPU resource limits) — see below
4. Update the compose `user:` field to match your UID (see step 3 in SSH path)

#### Full Path — SSH

1. **SSH into your Synology:**
   ```bash
   ssh -p 401 youruser@synology-ip
   ```
   > If you hit "Too many authentication failures", force password auth:
   > `ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -p 401 youruser@synology-ip`

2. **Docker requires `sudo`** on Synology DSM. The admin user is not in the `docker` group by default. Prefix every docker command with `sudo`, and ensure the PATH includes `/usr/local/bin`:
   ```bash
   export PATH=/usr/local/bin:$PATH
   sudo docker --version
   sudo docker compose version
   ```

3. **Find your UID:**
   ```bash
   id
   # Typical output: uid=1026(youruser) gid=100(users)
   ```
   Common Synology UIDs: first admin user = `1026`, GID = `100`.

4. **Create the project directory and volumes:**
   ```bash
   sudo mkdir -p /volume1/docker/gearcargo/volumes/{db,redis,attachments,backups,uploads,logs}
   sudo chown -R 1026:100 /volume1/docker/gearcargo/volumes
   ```

5. **Get the compose file.** `curl` should be available; if not, download it on your PC and upload via DSM File Station (SCP is often unavailable on Synology — see note below):
   ```bash
   cd /volume1/docker/gearcargo
   sudo curl -fsSL https://raw.githubusercontent.com/aiulian25/gearcargo/main/docker-compose.deploy.yml -o docker-compose.yml
   ```

6. **Edit the compose file** — two mandatory changes for Synology:

   **a) Update the `user:` directive** to your UID:
   ```bash
   sudo sed -i 's/user: "1000:1000"/user: "1026:100"/g' docker-compose.yml
   ```

   **b) Remove all `deploy:` resource limit blocks** — Synology's DSM kernel does not support CPU CFS scheduler, and `docker compose up` will fail with *"NanoCPUs can not be set"*:
   ```bash
   # Remove deploy sections (they span multiple lines under each service)
   sudo sed -i '/^[[:space:]]*deploy:/,/^[[:space:]]*[a-z]/{ /^[[:space:]]*deploy:/d; /^[[:space:]]*resources:/d; /^[[:space:]]*limits:/d; /^[[:space:]]*cpus:/d; /^[[:space:]]*memory:/d; }' docker-compose.yml
   ```
   Or simply open the file and delete every `deploy:` → `resources:` → `limits:` block.

7. **Create the `.env` file** — follow [Section 4](#4-configure-environment-variables). Set:
   ```
   PUID=1026
   PGID=100
   APP_PORT=5050        # or any free port (DSM may use 5000/5001)
   APP_URL=http://your-synology-ip:5050
   ```

8. **Login to GHCR** (or see [Section 5](#5-login-to-github-container-registry)):
   ```bash
   echo "YOUR_GITHUB_TOKEN" | sudo docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
   ```

9. **Start:**
   ```bash
   cd /volume1/docker/gearcargo
   sudo docker compose pull
   sudo docker compose up -d
   ```

10. **Verify** (wait ~60 seconds for health checks):
    ```bash
    sudo docker compose ps
    curl http://localhost:5050/health
    ```

#### Synology-Specific Gotchas

| Issue | Detail |
|-------|--------|
| **`sudo` required** | Docker commands need `sudo` on DSM. The admin user is not in the docker group. |
| **`NanoCPUs can not be set`** | Synology's kernel lacks CPU CFS scheduler support. Remove all `deploy:` resource limit blocks from compose. |
| **SCP / SFTP unavailable** | DSM's SSH subsystem often doesn't support SCP. Use **DSM File Station** to upload files, or pipe via SSH: `cat file.yml \| ssh synology "sudo tee /path/file.yml > /dev/null"` |
| **Port 5000/5001 in use** | DSM uses ports 5000 (HTTP) and 5001 (HTTPS). Use a different `APP_PORT` like `5050`. |
| **PATH doesn't include docker** | Run `export PATH=/usr/local/bin:$PATH` before docker commands, or add it to your shell profile. |
| **Volume paths** | Use `/volume1/docker/gearcargo/...` (or `/volume2/...` depending on your storage pool). |

### Portainer

1. Go to **Stacks → Add stack**
2. Paste the compose file contents
3. Add environment variables in the **Environment variables** section (same as `.env`)
4. Volume paths use absolute host paths — adjust to your system

### Oracle Cloud (Free Tier / ARM)

The image is built for **linux/amd64**. If running on ARM (Ampere A1):
- You may need to build from source, or
- Use QEMU emulation: `docker run --platform linux/amd64 ...` (slow)

For AMD64 instances (VM.Standard.E2.1.Micro — free tier), the image works natively.

Firewall: Oracle Cloud has both **iptables** and a **VCN Security List**. You must open the port in both:

```bash
# iptables
sudo iptables -I INPUT -p tcp --dport 5000 -j ACCEPT
sudo netfilter-persistent save

# VCN: Oracle Cloud Console → Networking → VCN → Security Lists → Add Ingress Rule
```

### Raspberry Pi

- Use a **Pi 4 with 2GB+ RAM** minimum
- The image is amd64 — you'll need to build from the Dockerfile for ARM:
  ```bash
  git clone https://github.com/aiulian25/gearcargo.git
  cd gearcargo
  docker compose -f docker-compose.yml build
  docker compose -f docker-compose.yml up -d
  ```
- Consider reducing Gunicorn workers in `.env`: `GUNICORN_WORKERS=2`

---

## 14. Complete .env Reference

Every environment variable the application reads, with its default value:

| Variable | Default | Description |
|----------|---------|-------------|
| **Application** | | |
| `APP_URL` | `http://localhost:5000` | Public URL (used in emails, CORS) |
| `APP_PORT` | `5000` | Host port mapping |
| `FLASK_ENV` | `production` | Flask environment |
| `DEFAULT_THEME` | `dark` | UI theme (`dark` or `light`) |
| **Secrets** | | |
| `SECRET_KEY` | *(must set)* | Flask session signing key |
| `JWT_SECRET_KEY` | *(must set)* | JWT token signing key |
| `WTF_CSRF_SECRET_KEY` | *(must set)* | CSRF protection key |
| `ENCRYPTION_KEY` | *(must set)* | Data-at-rest encryption key |
| `DB_PASSWORD` | *(must set)* | PostgreSQL password |
| `REDIS_PASSWORD` | *(must set)* | Redis password |
| **Security** | | |
| `ADMIN_DOMAIN` | *(empty)* | Domain restricted to admin logins |
| `USER_DOMAIN` | *(empty)* | Domain restricted to user logins |
| `CORS_ORIGINS` | `http://localhost:5000` | Allowed CORS origins (comma-separated) |
| `SESSION_COOKIE_SECURE` | `false` | Set `true` when using HTTPS |
| `SESSION_COOKIE_SAMESITE` | `Lax` | Cookie SameSite policy (`Lax` or `Strict`) |
| `RATELIMIT_DEFAULT` | `200 per day` | Global rate limit |
| `JWT_ACCESS_TOKEN_EXPIRES` | `3600` | Access token lifetime (seconds) |
| `JWT_REFRESH_TOKEN_EXPIRES` | `2592000` | Refresh token lifetime (seconds, default: 30 days) |
| **Email** | | |
| `MAIL_ENABLED` | `false` | Enable email features |
| `MAIL_SERVER` | `smtp.gmail.com` | SMTP server hostname |
| `MAIL_PORT` | `587` | SMTP port |
| `MAIL_USE_TLS` | `true` | Use STARTTLS |
| `MAIL_USERNAME` | *(empty)* | SMTP username |
| `MAIL_PASSWORD` | *(empty)* | SMTP password / app password |
| `MAIL_DEFAULT_SENDER` | `noreply@gearcargo.local` | From address |
| **Push Notifications** | | |
| `VAPID_PUBLIC_KEY` | *(empty)* | VAPID public key |
| `VAPID_PRIVATE_KEY` | *(empty)* | VAPID private key |
| `VAPID_SUBJECT` | `mailto:admin@gearcargo.local` | VAPID subject (email URI) |
| **AI (Ollama)** | | |
| `OLLAMA_ENABLED` | `false` | Enable AI features |
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434` | Ollama API URL |
| `OLLAMA_MODEL` | `llama3.2` | Ollama model name |
| `OLLAMA_TIMEOUT` | `30` | API timeout (seconds) |
| **Admin Bootstrap** | | |
| `ADMIN_EMAIL` | *(empty)* | Auto-create admin with this email |
| `ADMIN_USERNAME` | *(empty)* | Admin username |
| `ADMIN_PASSWORD` | *(empty)* | Admin password (remove after first login) |
| **Docker** | | |
| `PUID` | `1000` | Container user UID |
| `PGID` | `1000` | Container user GID |
| `GUNICORN_WORKERS` | `(CPU × 2) + 1` | Number of web server workers |

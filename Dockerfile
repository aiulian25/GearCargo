# GearCargo — the all-in-one image (single container via s6-overlay)
#
# One image that runs, under an s6-overlay v3 supervision tree:
#   • PostgreSQL 16  (embedded, loopback-only)   — or external via DATABASE_URL
#   • Redis 7        (embedded, loopback-only)    — or external via REDIS_URL
#   • gunicorn       (Flask API + PWA, :5000, the ONLY published port)
#   • cron           (scheduled pg_dump + media backups → mounted volume)
#
# Dual-mode: when DATABASE_URL / REDIS_URL point off-box the matching embedded
# server is skipped, so the SAME image also works with an external DB/Redis.
#
# Published to GHCR as ghcr.io/aiulian25/gearcargo:latest (multi-arch).

# ============================================================
# STAGE 1: Build Frontend (React PWA)
# ============================================================
FROM node:20-alpine AS frontend-builder
WORKDIR /frontend
# Build metadata baked into the PWA (via Vite's import.meta.env) so the running
# app can detect a newer published build and tell a feature update apart from a
# weekly OS-security rebuild. Default to dev-friendly values for local builds.
ARG GIT_SHA=dev
ARG BUILD_DATE=
ARG APP_VERSION=0.0.0
ENV VITE_GIT_SHA=$GIT_SHA \
    VITE_BUILD_DATE=$BUILD_DATE \
    VITE_APP_VERSION=$APP_VERSION
COPY frontend/package*.json ./
COPY frontend/package-lock.json* ./
RUN npm install --silent
COPY frontend/ .
RUN npm run build

# ============================================================
# STAGE 2: All-in-one runtime
# Pinned to bookworm so PostgreSQL 16 (from PGDG) is available on both
# amd64 and arm64 — the migration is a 16→16 logical restore (Single-Image.md §12).
# ============================================================
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    # s6-overlay behaviour: keep container env, crash the container if a oneshot
    # (e.g. migrate) fails instead of running half-initialised, wait for readiness.
    S6_KEEP_ENV=1 \
    S6_BEHAVIOUR_IF_STAGE2_FAILS=2 \
    S6_CMD_WAIT_FOR_SERVICES_MAXTIME=0 \
    S6_VERBOSITY=1

WORKDIR /app

# TARGETARCH is provided by buildx (amd64 / arm64) for multi-arch builds.
ARG TARGETARCH
ARG S6_OVERLAY_VERSION=3.2.0.2

# Build metadata (same values passed to the frontend stage) — surfaced by the
# backend at /api/app-version so the running PWA can detect a newer build and
# distinguish a feature update (git_sha changed) from a weekly OS-security
# rebuild (same git_sha, newer build_date).
ARG GIT_SHA=dev
ARG BUILD_DATE=
ARG APP_VERSION=0.0.0

# ------------------------------------------------------------
# System packages: PostgreSQL 16 (PGDG), Redis, cron, OCR, s6-overlay.
# ------------------------------------------------------------
RUN set -eux; \
    apt-get update; \
    mkdir -p /app; \
    apt-get -s upgrade 2>/dev/null | awk '/^Inst /{v=$3; gsub(/[()[\]]/,"",v); print $2" "v}' > /app/patched-packages.txt || true; \
    apt-get upgrade -y; \
    apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg xz-utils \
        gcc libpq-dev \
        redis-server cron \
        tesseract-ocr tesseract-ocr-eng tesseract-ocr-ron tesseract-ocr-spa; \
    # --- PostgreSQL 16 from the official PGDG apt repository ---
    install -d /usr/share/postgresql-common/pgdg; \
    curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc; \
    echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] http://apt.postgresql.org/pub/repos/apt $(. /etc/os-release; echo "$VERSION_CODENAME")-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends postgresql-16 postgresql-client-16; \
    # The postgresql-16 postinst auto-creates a 'main' cluster we don't use
    # (we manage our own PGDATA at /var/lib/postgresql/data). Drop it.
    pg_dropcluster --stop 16 main || true; \
    # --- s6-overlay v3 (noarch + arch-specific) ---
    case "$TARGETARCH" in \
        amd64) S6_ARCH=x86_64 ;; \
        arm64) S6_ARCH=aarch64 ;; \
        *) echo "Unsupported TARGETARCH: $TARGETARCH" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-noarch.tar.xz" -o /tmp/s6-noarch.tar.xz; \
    curl -fsSL "https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-${S6_ARCH}.tar.xz" -o /tmp/s6-arch.tar.xz; \
    tar -C / -Jxpf /tmp/s6-noarch.tar.xz; \
    tar -C / -Jxpf /tmp/s6-arch.tar.xz; \
    rm -f /tmp/s6-*.tar.xz; \
    apt-get purge -y --auto-remove gnupg xz-utils; \
    rm -rf /var/lib/apt/lists/*

# ------------------------------------------------------------
# Python dependencies (same requirements as the backend image)
# ------------------------------------------------------------
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip uninstall -y wheel setuptools || true

# ------------------------------------------------------------
# Application code, backup script, built frontend
# ------------------------------------------------------------
COPY backend/ .
COPY scripts/ /app/scripts/
COPY --from=frontend-builder /frontend/dist /app/static

# Assemble the build manifest the backend serves at /api/app-version. Combines
# the build-arg metadata with the captured OS-security package list.
RUN APP_VERSION="$APP_VERSION" GIT_SHA="$GIT_SHA" BUILD_DATE="$BUILD_DATE" python3 -c "import json,os; p='/app/patched-packages.txt'; pkgs=[l.strip() for l in open(p)][:120] if os.path.exists(p) else []; json.dump({'version':os.environ.get('APP_VERSION') or '0.0.0','git_sha':os.environ.get('GIT_SHA') or 'dev','build_date':os.environ.get('BUILD_DATE') or '','patched_packages':[x for x in pkgs if x]}, open('/app/build-info.json','w'))" && rm -f /app/patched-packages.txt

# s6 service tree + service scripts (docker/rootfs → /)
COPY docker/rootfs/ /

# Self-contained install assets: the exact compose + env + setup baked in, so a
# host with only Docker (private repo, no raw-GitHub access) can bootstrap via:
#   docker run --rm ghcr.io/aiulian25/gearcargo:latest install > gearcargo-install.sh
COPY docker-compose.yml .env.example setup.sh /install/
COPY docker/install/print-installer.sh /install/print-installer.sh
COPY docker/entrypoint.sh /usr/local/bin/gearcargo-entrypoint.sh

# ------------------------------------------------------------
# Users, directories, permissions
# (postgres & redis users are created by their apt packages)
# ------------------------------------------------------------
RUN set -eux; \
    useradd -m -u 1000 gearcargo; \
    mkdir -p /app/volumes/attachments /app/volumes/backups/system \
             /app/uploads /app/volumes/logs \
             /var/lib/postgresql/data /run/gearcargo; \
    chown -R gearcargo:gearcargo /app/volumes /app/uploads /run/gearcargo; \
    chown postgres:postgres /var/lib/postgresql/data; \
    chmod 700 /var/lib/postgresql/data; \
    # Executable bits for s6 longrun 'run' scripts and our service scripts.
    chmod +x /etc/gearcargo/scripts/*.sh; \
    find /etc/s6-overlay/s6-rc.d -type f -name run -exec chmod +x {} +; \
    # /etc/cron.d entry must be root-owned and not group/other-writable.
    chown root:root /etc/cron.d/gearcargo; chmod 644 /etc/cron.d/gearcargo; \
    # Install helpers executable.
    chmod +x /install/print-installer.sh /install/setup.sh /usr/local/bin/gearcargo-entrypoint.sh

HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

EXPOSE 5000

# Thin wrapper: `install` prints the self-extracting installer; anything else
# hands off to the s6-overlay init (PID 1), which reaps zombies, forwards
# signals, and supervises the service tree.
ENTRYPOINT ["/usr/local/bin/gearcargo-entrypoint.sh"]

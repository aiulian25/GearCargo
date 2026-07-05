#!/usr/bin/env bash
# ============================================================
# GearCargo — one-step setup (single-image, pre-built)
# ============================================================
# Pulls the ready image, generates all secrets for you, creates the data dirs,
# and starts the app. Re-runnable: it never overwrites an existing .env/secrets.
#
# The only thing that must exist on the host is Docker. All crypto (Fernet
# ENCRYPTION_KEY, VAPID keys, tokens) is generated INSIDE the image, so you don't
# need python/openssl locally.
set -euo pipefail

IMAGE="ghcr.io/aiulian25/gearcargo:latest"

RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[1;33m'; BLUE=$'\033[0;34m'; NC=$'\033[0m'
say()  { printf '%s\n' "$*"; }
ok()   { printf '%s✓%s %s\n' "$GREEN" "$NC" "$*"; }
warn() { printf '%s!%s %s\n'  "$YELLOW" "$NC" "$*"; }
die()  { printf '%s✗ %s%s\n' "$RED" "$*" "$NC" >&2; exit 1; }

cd "$(dirname "$0")"

printf '%s\n' "${BLUE}== GearCargo setup ==${NC}"

# ── prerequisites ───────────────────────────────────────────
command -v docker >/dev/null 2>&1 || die "Docker is not installed."
if docker compose version >/dev/null 2>&1; then DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then DC="docker-compose"
else die "Docker Compose v2 is required."; fi
ok "Docker + Compose present"
[ -f docker-compose.yml ] || die "Run this from the folder containing docker-compose.yml"
[ -f .env.example ] || die ".env.example not found next to docker-compose.yml"
[ "$(id -u)" = "0" ] && warn "Running as root — a non-root user in the 'docker' group is recommended."

# ── pull the image (also used to generate secrets) ──────────
say "${YELLOW}Pulling ${IMAGE} …${NC}"
docker pull "$IMAGE" >/dev/null
ok "Image pulled"

# ── .env + secrets (generated once, never overwritten) ──────
mkdir -p secrets
if [ ! -f .env ]; then
    cp .env.example .env

    say "${YELLOW}Generating secrets inside the image …${NC}"
    # --entrypoint python3 bypasses the s6 init so nothing else starts.
    GEN="$(docker run --rm --entrypoint python3 "$IMAGE" -c '
import secrets, base64
from cryptography.fernet import Fernet
def t(): return secrets.token_urlsafe(48)
print("SECRET_KEY="+t())
print("JWT_SECRET_KEY="+t())
print("WTF_CSRF_SECRET_KEY="+t())
print("ENCRYPTION_KEY="+Fernet.generate_key().decode())
print("DB_PASSWORD="+secrets.token_urlsafe(24))
print("REDIS_PASSWORD="+secrets.token_urlsafe(24))
from py_vapid import Vapid
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
v=Vapid(); v.generate_keys()
# P-256 keys do NOT support Raw encoding — take the raw 32-byte scalar directly.
priv=base64.urlsafe_b64encode(v._private_key.private_numbers().private_value.to_bytes(32,"big")).rstrip(b"=").decode()
pub=base64.urlsafe_b64encode(v._private_key.public_key().public_bytes(Encoding.X962,PublicFormat.UncompressedPoint)).rstrip(b"=").decode()
print("VAPID_PRIVATE_KEY="+priv)
print("VAPID_PUBLIC_KEY="+pub)
')"
    [ -n "$GEN" ] || die "Secret generation failed."

    set_env() { # key value  → replace "key=" in .env (| delimiter; values are url-safe)
        local k="$1" v="$2"
        sed -i "s|^${k}=.*|${k}=${v}|" .env
    }
    # Split on the FIRST '=' only — a Fernet ENCRYPTION_KEY ends in '=' padding
    # that a normal IFS='=' split would strip.
    while IFS= read -r line; do
        [ -n "$line" ] || continue
        k="${line%%=*}"; v="${line#*=}"
        case "$k" in
            VAPID_PRIVATE_KEY) printf '%s' "$v" > secrets/vapid_private_key; chmod 600 secrets/vapid_private_key ;;
            * ) set_env "$k" "$v" ;;
        esac
    done <<< "$GEN"
    ok "Secrets generated (ENCRYPTION_KEY is a Fernet key; VAPID private key → secrets/vapid_private_key)"

    # ── URL + port ──────────────────────────────────────────
    printf 'App URL (how you will reach GearCargo) [http://localhost:5000]: '
    read -r app_url || true; app_url="${app_url:-http://localhost:5000}"
    set_env APP_URL "$app_url"
    set_env CORS_ORIGINS "$app_url"

    printf 'App port [5000] (Synology: 5050): '
    read -r app_port || true; app_port="${app_port:-5000}"
    set_env APP_PORT "$app_port"

    # ── loopback bind (SECURITY_ASSESSMENT.md D2) ───────────
    printf 'Is a reverse proxy (nginx/Traefik/Caddy) running on THIS machine? [y/N]: '
    read -r proxy || true
    case "$proxy" in
        y|Y|yes|YES)
            if grep -q '^# APP_BIND_IP=' .env; then sed -i 's|^# APP_BIND_IP=.*|APP_BIND_IP=127.0.0.1|' .env
            else printf 'APP_BIND_IP=127.0.0.1\n' >> .env; fi
            set_env TRUSTED_PROXY_COUNT 1
            ok "Bound to 127.0.0.1 — only your proxy can reach it" ;;
        *)
            set_env TRUSTED_PROXY_COUNT 0
            warn "Listening on all interfaces — make sure your firewall blocks the port from the internet, or run behind a proxy." ;;
    esac
else
    ok ".env already exists — keeping it (no secrets changed)"
    [ -f secrets/vapid_private_key ] || warn "secrets/vapid_private_key is missing — push notifications will be disabled."
fi

# ── data directories (Synology needs these pre-created) ─────
mkdir -p volumes/{pgdata,redis,attachments,uploads,backups,logs,geoip}
ok "Data directories ready under ./volumes"

# ── start ───────────────────────────────────────────────────
say "${YELLOW}Starting GearCargo …${NC}"
$DC up -d

# ── wait for health ─────────────────────────────────────────
say "${YELLOW}Waiting for the app to become healthy (first boot initializes the database) …${NC}"
name="$($DC ps -q gearcargo 2>/dev/null | head -1)"
healthy=0
for _ in $(seq 1 45); do
    st="$(docker inspect -f '{{.State.Health.Status}}' "$name" 2>/dev/null || echo starting)"
    [ "$st" = "healthy" ] && { healthy=1; break; }
    sleep 4
done

port="$(grep -E '^APP_PORT=' .env | cut -d= -f2)"; port="${port:-5000}"
if [ "$healthy" = "1" ]; then
    printf '%s\n' "${GREEN}== GearCargo is running 🎉 ==${NC}"
    say "Open: ${BLUE}$(grep -E '^APP_URL=' .env | cut -d= -f2-)${NC}  (local: http://localhost:${port})"
    say "First run? Create your admin account from the login screen."
else
    warn "It didn't report healthy yet. Check logs:  $DC logs -f"
fi
say ""
say "Useful commands:"
say "  • Logs:    $DC logs -f"
say "  • Stop:    $DC down"
say "  • Update:  $DC pull && $DC up -d"

#!/bin/bash

# GearCargo Setup Script
# This script initializes the GearCargo application

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}"
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║                     GearCargo Setup                           ║"
echo "║               Vehicle Management PWA                          ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Check prerequisites
echo -e "${YELLOW}Checking prerequisites...${NC}"

# Check Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker is not installed. Please install Docker first.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker is installed${NC}"

# Check Docker Compose
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo -e "${RED}❌ Docker Compose is not installed. Please install Docker Compose first.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker Compose is installed${NC}"

# Check if running as root (not recommended for docker)
if [ "$EUID" -eq 0 ]; then
    echo -e "${YELLOW}⚠ Running as root is not recommended. Consider using a non-root user with docker group.${NC}"
fi

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo -e "${YELLOW}Creating .env file from template...${NC}"
    cp .env.example .env
    
    # Generate secure keys
    echo -e "${YELLOW}Generating secure keys...${NC}"
    
    # Generate SECRET_KEY
    SECRET_KEY=$(openssl rand -hex 32)
    sed -i "s/your-super-secret-key-change-in-production-min-32-chars/$SECRET_KEY/" .env
    
    # Generate JWT_SECRET_KEY
    JWT_SECRET=$(openssl rand -hex 32)
    sed -i "s/your-jwt-secret-key-change-in-production/$JWT_SECRET/" .env
    
    # Generate ENCRYPTION_KEY
    ENCRYPTION_KEY=$(openssl rand -hex 32)
    sed -i "s/your-encryption-key-32-bytes-hex/$ENCRYPTION_KEY/" .env
    
    echo -e "${GREEN}✓ Generated secure keys${NC}"
    
    echo -e "${YELLOW}"
    echo "╔═══════════════════════════════════════════════════════════════╗"
    echo "║                    IMPORTANT                                  ║"
    echo "║  Please edit the .env file to configure:                      ║"
    echo "║  - Database password                                          ║"
    echo "║  - SMTP settings for emails                                   ║"
    echo "║  - VAPID keys for push notifications                          ║"
    echo "║  - Ollama settings (if using AI features)                     ║"
    echo "╚═══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
else
    echo -e "${GREEN}✓ .env file exists${NC}"
fi

# Create required directories
echo -e "${YELLOW}Creating required directories...${NC}"
mkdir -p data/postgres
mkdir -p data/redis
mkdir -p data/backups
mkdir -p data/uploads
mkdir -p logs
echo -e "${GREEN}✓ Directories created${NC}"

# Generate VAPID keys if not set
if grep -q "VAPID_PRIVATE_KEY=$" .env 2>/dev/null || grep -q "VAPID_PRIVATE_KEY=your-vapid" .env 2>/dev/null; then
    echo -e "${YELLOW}Generating VAPID keys for push notifications...${NC}"
    
    # Check if we have python and can generate keys
    if command -v python3 &> /dev/null; then
        # Try to generate VAPID keys using Python.
        # py_vapid stores keys as P-256 (ECDSA / SECP256R1).  The browser's
        # PushManager requires the public key as the 65-byte uncompressed point
        # (0x04 || X || Y) encoded in URL-safe base64 (no padding).
        # pywebpush accepts the private key as the raw 32-byte scalar in
        # URL-safe base64.  We use the cryptography library's serialisation API
        # (always available alongside py_vapid) to extract both in the correct
        # format.  NOTE: public_bytes_raw() does NOT exist on P-256 keys in the
        # cryptography library — using it would silently fall into the except and
        # produce unusable random bytes.
        VAPID_KEYS=$(python3 -c "
try:
    from py_vapid import Vapid
    from cryptography.hazmat.primitives.serialization import (
        Encoding, PublicFormat, PrivateFormat, NoEncryption
    )
    import base64
    vapid = Vapid()
    vapid.generate_keys()
    # Private: raw 32-byte scalar → URL-safe base64
    priv_bytes = vapid._private_key.private_bytes(
        Encoding.Raw, PrivateFormat.Raw, NoEncryption()
    )
    priv = base64.urlsafe_b64encode(priv_bytes).rstrip(b'=').decode()
    # Public: uncompressed P-256 point (65 bytes: 04 || X || Y) → URL-safe base64
    pub_bytes = vapid._private_key.public_key().public_bytes(
        Encoding.X962, PublicFormat.UncompressedPoint
    )
    pub = base64.urlsafe_b64encode(pub_bytes).rstrip(b'=').decode()
    print(priv)
    print(pub)
except Exception as e:
    import sys
    print(f'VAPID generation failed: {e}', file=sys.stderr)
" 2>/dev/null || echo "")
        
        if [ -n "$VAPID_KEYS" ]; then
            VAPID_PRIVATE=$(echo "$VAPID_KEYS" | head -1)
            VAPID_PUBLIC=$(echo "$VAPID_KEYS" | tail -1)
            sed -i "s/VAPID_PRIVATE_KEY=.*/VAPID_PRIVATE_KEY=$VAPID_PRIVATE/" .env
            sed -i "s/VAPID_PUBLIC_KEY=.*/VAPID_PUBLIC_KEY=$VAPID_PUBLIC/" .env
            echo -e "${GREEN}✓ VAPID keys generated${NC}"
        fi
    fi
fi

# Ollama configuration
echo -e "${YELLOW}"
echo "Ollama AI Configuration:"
echo "  1) Don't use Ollama (disabled)"
echo "  2) Install Ollama locally via Docker"
echo "  3) Connect to existing Ollama instance"
echo -e "${NC}"

read -p "Select option [1-3] (default: 1): " ollama_option
ollama_option=${ollama_option:-1}

case $ollama_option in
    2)
        echo -e "${GREEN}✓ Ollama will be installed locally${NC}"
        sed -i "s/OLLAMA_ENABLED=false/OLLAMA_ENABLED=true/" .env
        sed -i "s/OLLAMA_URL=.*/OLLAMA_URL=http:\/\/ollama:11434/" .env
        DOCKER_PROFILE="--profile ollama-local"
        ;;
    3)
        read -p "Enter Ollama URL (e.g., http://192.168.1.100:11434): " ollama_url
        if [ -n "$ollama_url" ]; then
            sed -i "s/OLLAMA_ENABLED=false/OLLAMA_ENABLED=true/" .env
            sed -i "s|OLLAMA_URL=.*|OLLAMA_URL=$ollama_url|" .env
            echo -e "${GREEN}✓ Configured to use external Ollama at $ollama_url${NC}"
        fi
        DOCKER_PROFILE=""
        ;;
    *)
        echo -e "${GREEN}✓ Ollama disabled${NC}"
        DOCKER_PROFILE=""
        ;;
esac

# Build and start containers
echo -e "${YELLOW}"
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║                   Building Containers                         ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Determine docker compose command
if docker compose version &> /dev/null; then
    DOCKER_COMPOSE="docker compose"
else
    DOCKER_COMPOSE="docker-compose"
fi

echo -e "${YELLOW}Building images (this may take a few minutes)...${NC}"
$DOCKER_COMPOSE build

echo -e "${YELLOW}Starting services...${NC}"
$DOCKER_COMPOSE $DOCKER_PROFILE up -d

# Wait for services to be ready
echo -e "${YELLOW}Waiting for services to be ready...${NC}"
sleep 10

# Check if services are running
if $DOCKER_COMPOSE ps | grep -q "Up"; then
    echo -e "${GREEN}✓ Services are running${NC}"
else
    echo -e "${RED}❌ Some services failed to start. Check logs with: docker compose logs${NC}"
    exit 1
fi

# Run database migrations
echo -e "${YELLOW}Running database migrations...${NC}"
$DOCKER_COMPOSE exec -T backend flask db upgrade 2>/dev/null || echo "Migrations will run on first request"

# Get the port from .env or use default
PORT=$(grep "^PORT=" .env | cut -d= -f2)
PORT=${PORT:-5000}

echo -e "${GREEN}"
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║                   Setup Complete! 🎉                          ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

echo -e "GearCargo is now running at: ${BLUE}http://localhost:${PORT}${NC}"
echo ""
echo "Useful commands:"
echo "  • View logs:        $DOCKER_COMPOSE logs -f"
echo "  • Stop services:    $DOCKER_COMPOSE down"
echo "  • Restart:          $DOCKER_COMPOSE restart"
echo "  • Update:           git pull && $DOCKER_COMPOSE build && $DOCKER_COMPOSE up -d"
echo ""
echo -e "${YELLOW}First time? Create an admin account at: http://localhost:${PORT}/register${NC}"

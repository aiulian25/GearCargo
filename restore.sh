#!/bin/bash

# GearCargo Restore Script
# Restores from backup archive

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Check arguments
if [ -z "$1" ]; then
    echo -e "${YELLOW}Usage: ./restore.sh <backup_file.tar.gz>${NC}"
    echo ""
    echo "Available backups:"
    ls -lh ./data/backups/*.tar.gz 2>/dev/null || echo "No backups found in ./data/backups/"
    exit 1
fi

BACKUP_FILE="$1"

if [ ! -f "$BACKUP_FILE" ]; then
    echo -e "${RED}❌ Backup file not found: $BACKUP_FILE${NC}"
    exit 1
fi

# Determine docker compose command
if docker compose version &> /dev/null; then
    DOCKER_COMPOSE="docker compose"
else
    DOCKER_COMPOSE="docker-compose"
fi

echo -e "${YELLOW}"
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║                   GearCargo Restore                           ║"
echo "║                                                               ║"
echo "║  ⚠  WARNING: This will overwrite existing data!              ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

read -p "Are you sure you want to restore from $BACKUP_FILE? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    echo "Restore cancelled."
    exit 0
fi

# Create temp directory for extraction
TEMP_DIR=$(mktemp -d)
echo -e "${YELLOW}Extracting backup...${NC}"
tar -xzf "$BACKUP_FILE" -C "$TEMP_DIR"

# Find the database dump
DB_DUMP=$(ls "$TEMP_DIR"/*_db.sql.gz 2>/dev/null | head -1)
UPLOADS_ARCHIVE=$(ls "$TEMP_DIR"/*_uploads.tar.gz 2>/dev/null | head -1)

if [ -z "$DB_DUMP" ]; then
    echo -e "${RED}❌ No database dump found in backup${NC}"
    rm -rf "$TEMP_DIR"
    exit 1
fi

# Stop the backend to prevent connections
echo -e "${YELLOW}Stopping backend service...${NC}"
$DOCKER_COMPOSE stop backend

# Restore database
echo -e "${YELLOW}Restoring database...${NC}"
gunzip -c "$DB_DUMP" | $DOCKER_COMPOSE exec -T db psql -U postgres -d gearcargo

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Database restored${NC}"
else
    echo -e "${RED}❌ Database restore failed${NC}"
    $DOCKER_COMPOSE start backend
    rm -rf "$TEMP_DIR"
    exit 1
fi

# Restore uploads if available
if [ -n "$UPLOADS_ARCHIVE" ] && [ -f "$UPLOADS_ARCHIVE" ]; then
    echo -e "${YELLOW}Restoring uploads...${NC}"
    mkdir -p ./data
    tar -xzf "$UPLOADS_ARCHIVE" -C ./data
    echo -e "${GREEN}✓ Uploads restored${NC}"
fi

# Start backend
echo -e "${YELLOW}Starting backend service...${NC}"
$DOCKER_COMPOSE start backend

# Cleanup
rm -rf "$TEMP_DIR"

echo -e "${GREEN}"
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║               Restore Completed Successfully!                 ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

echo "Note: You may need to restart all services for changes to take effect:"
echo "  $DOCKER_COMPOSE restart"

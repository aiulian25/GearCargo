#!/bin/bash

# GearCargo Backup Script
# Creates backups of database and uploads

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Configuration
BACKUP_DIR="${BACKUP_DIR:-./data/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_NAME="gearcargo_backup_${TIMESTAMP}"

# Determine docker compose command
if docker compose version &> /dev/null; then
    DOCKER_COMPOSE="docker compose"
else
    DOCKER_COMPOSE="docker-compose"
fi

echo -e "${YELLOW}Starting GearCargo backup...${NC}"

# Create backup directory
mkdir -p "${BACKUP_DIR}"

# Backup PostgreSQL database
echo -e "${YELLOW}Backing up database...${NC}"
$DOCKER_COMPOSE exec -T db pg_dump -U postgres gearcargo | gzip > "${BACKUP_DIR}/${BACKUP_NAME}_db.sql.gz"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Database backup created${NC}"
else
    echo -e "${RED}❌ Database backup failed${NC}"
    exit 1
fi

# Backup uploads directory
if [ -d "./data/uploads" ] && [ "$(ls -A ./data/uploads 2>/dev/null)" ]; then
    echo -e "${YELLOW}Backing up uploads...${NC}"
    tar -czf "${BACKUP_DIR}/${BACKUP_NAME}_uploads.tar.gz" -C ./data uploads
    echo -e "${GREEN}✓ Uploads backup created${NC}"
else
    echo -e "${YELLOW}⚠ No uploads to backup${NC}"
fi

# Backup .env file (encrypted)
echo -e "${YELLOW}Backing up configuration...${NC}"
if [ -f ".env" ]; then
    # Simple backup without encryption (for user to handle security)
    cp .env "${BACKUP_DIR}/${BACKUP_NAME}_env.bak"
    chmod 600 "${BACKUP_DIR}/${BACKUP_NAME}_env.bak"
    echo -e "${GREEN}✓ Configuration backed up${NC}"
fi

# Create combined archive
echo -e "${YELLOW}Creating combined backup archive...${NC}"
cd "${BACKUP_DIR}"
tar -czf "${BACKUP_NAME}.tar.gz" \
    "${BACKUP_NAME}_db.sql.gz" \
    "${BACKUP_NAME}_uploads.tar.gz" 2>/dev/null || \
tar -czf "${BACKUP_NAME}.tar.gz" \
    "${BACKUP_NAME}_db.sql.gz"

# Cleanup individual files
rm -f "${BACKUP_NAME}_db.sql.gz"
rm -f "${BACKUP_NAME}_uploads.tar.gz"
cd - > /dev/null

echo -e "${GREEN}✓ Combined backup created: ${BACKUP_DIR}/${BACKUP_NAME}.tar.gz${NC}"

# Calculate backup size
BACKUP_SIZE=$(du -h "${BACKUP_DIR}/${BACKUP_NAME}.tar.gz" | cut -f1)
echo -e "Backup size: ${BACKUP_SIZE}"

# Cleanup old backups
echo -e "${YELLOW}Cleaning up old backups (older than ${RETENTION_DAYS} days)...${NC}"
find "${BACKUP_DIR}" -name "gearcargo_backup_*.tar.gz" -mtime +${RETENTION_DAYS} -delete 2>/dev/null || true
find "${BACKUP_DIR}" -name "*_env.bak" -mtime +${RETENTION_DAYS} -delete 2>/dev/null || true

REMAINING_BACKUPS=$(ls -1 "${BACKUP_DIR}"/gearcargo_backup_*.tar.gz 2>/dev/null | wc -l)
echo -e "${GREEN}✓ Cleanup complete. ${REMAINING_BACKUPS} backup(s) retained.${NC}"

echo -e "${GREEN}"
echo "═══════════════════════════════════════════════════════════════"
echo "Backup completed successfully!"
echo "Location: ${BACKUP_DIR}/${BACKUP_NAME}.tar.gz"
echo "═══════════════════════════════════════════════════════════════"
echo -e "${NC}"

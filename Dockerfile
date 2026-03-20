# GearCargo - Multi-stage Dockerfile
# Stage 1: Build Frontend
# Stage 2: Backend + Serve Static Files

# ============================================================
# STAGE 1: Build Frontend (React PWA)
# ============================================================
FROM node:20-alpine AS frontend-builder

WORKDIR /frontend

# Copy package files first (better caching)
COPY frontend/package*.json ./
COPY frontend/package-lock.json* ./

# Install dependencies
RUN npm install --silent

# Copy frontend source
COPY frontend/ .

# Build for production
RUN npm run build

# ============================================================
# STAGE 2: Backend + Static Files
# ============================================================
FROM python:3.11-slim

# Environment
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

# Install system dependencies and apply security patches
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    tesseract-ocr \
    tesseract-ocr-eng \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Install Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip uninstall -y wheel setuptools || true

# Copy backend code
COPY backend/ .

# Copy built frontend from stage 1
COPY --from=frontend-builder /frontend/dist /app/static

# Create non-root user and install gosu for privilege dropping
RUN apt-get update && apt-get install -y --no-install-recommends gosu && rm -rf /var/lib/apt/lists/* && \
    useradd -m -u 1000 gearcargo && \
    mkdir -p /app/volumes/attachments /app/volumes/backups /app/uploads && \
    chown -R gearcargo:gearcargo /app && \
    chmod +x /app/docker-entrypoint.sh

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

EXPOSE 5000

# Run entrypoint script (handles migrations then starts Gunicorn)
CMD ["/app/docker-entrypoint.sh"]

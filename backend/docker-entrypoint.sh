#!/bin/bash
set -e

echo "Starting GearCargo..."

# Run database migrations
echo "Running database migrations..."
flask db upgrade || {
    echo "Migration failed, attempting to initialize database..."
    flask db init 2>/dev/null || true
    flask db migrate -m "Initial migration" 2>/dev/null || true
    flask db upgrade
}

echo "Database migrations complete."

# Start Gunicorn
exec gunicorn --config gunicorn.conf.py "app:create_app()"

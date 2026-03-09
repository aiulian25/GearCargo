#!/bin/bash
set -e

echo "Starting GearCargo..."

# Wait for database to be ready
echo "Waiting for database..."
for i in $(seq 1 30); do
    if python -c "
import psycopg2, os
conn = psycopg2.connect(os.environ.get('DATABASE_URL', 'postgresql://gearcargo:password@db:5432/gearcargo'))
conn.close()
print('ok')
" 2>/dev/null; then
        echo "Database is ready."
        break
    fi
    echo "  Waiting... ($i/30)"
    sleep 2
done

# Run database migrations
echo "Running database migrations..."
flask db upgrade 2>&1 || {
    echo "Migration failed, attempting to initialize database..."
    flask db init 2>/dev/null || true
    flask db migrate -m "Initial migration" 2>/dev/null || true
    flask db upgrade 2>&1 || echo "WARNING: Migration failed - tables may need manual setup"
}

# Ensure all tables AND columns exist
echo "Ensuring all model tables and columns exist..."
python << 'PYEOF'
from app import create_app, db
from sqlalchemy import inspect, text

app = create_app()
with app.app_context():
    db.create_all()

    inspector = inspect(db.engine)
    existing_tables = inspector.get_table_names()

    for table in db.metadata.tables.values():
        if table.name not in existing_tables:
            continue

        existing_cols = {col['name'] for col in inspector.get_columns(table.name)}
        model_cols = {col.name for col in table.columns}
        missing_cols = model_cols - existing_cols

        if missing_cols:
            print(f'  Adding missing columns to {table.name}: {missing_cols}')
            for col_name in missing_cols:
                col = table.columns[col_name]
                col_type = col.type.compile(db.engine.dialect)
                nullable = 'NULL' if col.nullable else 'NOT NULL'
                default = ''
                if col.default is not None:
                    dv = col.default.arg
                    if callable(dv):
                        default = ''
                    elif isinstance(dv, bool):
                        default = ' DEFAULT true' if dv else ' DEFAULT false'
                    elif isinstance(dv, (int, float)):
                        default = f' DEFAULT {dv}'
                    elif isinstance(dv, str):
                        safe = dv.replace("'", "''")
                        default = f" DEFAULT '{safe}'"
                    else:
                        default = ''
                sql = f'ALTER TABLE {table.name} ADD COLUMN IF NOT EXISTS {col_name} {col_type} {nullable}{default}'
                try:
                    db.session.execute(text(sql))
                    db.session.commit()
                    print(f'    + {col_name} ({col_type})')
                except Exception as e:
                    db.session.rollback()
                    print(f'    ! {col_name} failed: {e}')

    print('All tables and columns verified.')
PYEOF

echo "Database setup complete."

# Start Gunicorn
exec gunicorn --config gunicorn.conf.py "app:create_app()"

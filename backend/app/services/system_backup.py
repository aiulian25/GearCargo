"""System archive schedules share the same ownership/restore guard as app jobs."""
import os
from pathlib import Path
import subprocess
from sqlalchemy.engine import make_url
from app.services.scheduler_ownership import active_run


def system_backup(app, frequency):
    url = make_url(app.config['SQLALCHEMY_DATABASE_URI'])
    if not url.drivername.startswith('postgresql'):
        raise RuntimeError('System archive jobs require PostgreSQL')
    run = active_run.get()
    if not run:
        raise RuntimeError('System archive requires a claimed scheduled occurrence')
    run.lock.check()
    environment = {**os.environ, 'PGPASSWORD': url.password or '', 'PGPORT': str(url.port or 5432),
        'DB_HOST': url.host or 'localhost', 'DB_USER': url.username or '', 'DB_NAME': url.database or '',
        'BACKUP_ROOT': str(Path(app.config['BACKUP_FOLDER']) / 'system'),
        'ATTACHMENTS_DIR': app.config['UPLOAD_FOLDER'],
        'UPLOADS_DIR': str(Path(app.root_path).parent / 'uploads'),
        'KEEP_LAST': str(app.config.get('SYSTEM_BACKUP_KEEP_LAST', 7)),
        'BACKUP_PASSPHRASE_FILE': app.config.get('BACKUP_PASSPHRASE_FILE', ''),
        'BACKUP_OCCURRENCE': run.occurrence.strftime('%Y%m%d_%H%M%S')}
    script = app.config.get('SYSTEM_BACKUP_SCRIPT', '/app/scripts/docker-backup.sh')
    subprocess.run([script, frequency], env=environment, check=True)


def daily_backup(app):
    system_backup(app, 'daily')


def weekly_backup(app):
    system_backup(app, 'weekly')

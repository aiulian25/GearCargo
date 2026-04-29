"""
GearCargo - Backup Model
"""

import json
from datetime import datetime, timezone
from app import db


class Backup(db.Model):
    """Backup record model."""
    
    __tablename__ = 'backups'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    
    # Backup info
    backup_type = db.Column(db.String(20), nullable=False)  # full, incremental, export
    format = db.Column(db.String(20), default='json')  # json, csv, xlsx, zip
    
    # Storage
    filename = db.Column(db.String(255))
    filepath = db.Column(db.String(500))
    file_size = db.Column(db.Integer)  # Bytes
    
    # Cloud storage
    cloud_provider = db.Column(db.String(50))  # google_drive, dropbox, onedrive
    cloud_file_id = db.Column(db.String(255))
    cloud_url = db.Column(db.String(500))
    
    # Content summary
    vehicles_count = db.Column(db.Integer, default=0)
    entries_count = db.Column(db.Integer, default=0)
    reminders_count = db.Column(db.Integer, default=0)
    attachments_count = db.Column(db.Integer, default=0)
    
    # Status
    status = db.Column(db.String(20), default='pending')  # pending, in_progress, completed, failed
    error_message = db.Column(db.Text)
    
    # Encryption
    encrypted = db.Column(db.Boolean, default=True)
    checksum = db.Column(db.String(64))  # SHA-256
    
    # Timestamps
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Backup {self.id} - {self.backup_type}>'
    
    @property
    def duration_seconds(self):
        """Get backup duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
    
    @property
    def file_size_human(self):
        """Return human-readable file size."""
        if not self.file_size:
            return '0 B'
        
        size = self.file_size
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            'id': self.id,
            'backup_type': self.backup_type,
            'format': self.format,
            'filename': self.filename,
            'file_size': self.file_size,
            'file_size_human': self.file_size_human,
            'cloud_provider': self.cloud_provider,
            'vehicles_count': self.vehicles_count,
            'entries_count': self.entries_count,
            'reminders_count': self.reminders_count,
            'attachments_count': self.attachments_count,
            'status': self.status,
            # S12: Never surface raw exception text from the DB to API clients.
            # The DB column may contain internal details (filesystem paths, connection
            # strings, stack fragments) written before this fix. Return a fixed generic
            # sentinel when an error is recorded; the full detail lives in server logs.
            'error_message': 'Backup failed. Check server logs for details.' if self.error_message else None,
            'encrypted': self.encrypted,
            'duration_seconds': self.duration_seconds,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class BackupSchedule(db.Model):
    """Backup schedule configuration."""
    
    __tablename__ = 'backup_schedules'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
    
    # Schedule - weekly, monthly, quarterly (3 months)
    enabled = db.Column(db.Boolean, default=False)
    frequency = db.Column(db.String(20), default='weekly')  # weekly, monthly, quarterly
    day_of_week = db.Column(db.Integer, default=0)  # 0-6 for weekly (Monday=0)
    day_of_month = db.Column(db.Integer, default=1)  # 1-31 for monthly/quarterly
    hour = db.Column(db.Integer, default=3)  # Hour of day (0-23)
    
    # Options
    backup_type = db.Column(db.String(20), default='full')
    include_attachments = db.Column(db.Boolean, default=True)
    
    # External backup destination
    external_enabled = db.Column(db.Boolean, default=False)
    external_url = db.Column(db.String(500))  # URL for external backup server
    external_api_key = db.Column(db.String(255))  # API key for auth (encrypted)
    external_path = db.Column(db.String(255))  # Path on external server
    
    # Cloud storage (Google Drive, Dropbox, etc.)
    cloud_enabled = db.Column(db.Boolean, default=False)
    cloud_provider = db.Column(db.String(50))  # google_drive, dropbox, onedrive
    cloud_credentials = db.Column(db.Text)  # Encrypted OAuth tokens
    
    # Retention
    retention_days = db.Column(db.Integer, default=90)  # Default 90 days
    max_backups = db.Column(db.Integer, default=10)
    
    # Notifications
    notify_on_success = db.Column(db.Boolean, default=False)
    notify_on_failure = db.Column(db.Boolean, default=True)
    
    # Last run
    last_run_at = db.Column(db.DateTime)
    last_status = db.Column(db.String(20))
    last_error = db.Column(db.Text)
    next_run_at = db.Column(db.DateTime)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def _cloud_metadata(self):
        """Return cloud_credentials parsed as JSON metadata when possible."""
        if not self.cloud_credentials:
            return {}
        try:
            parsed = json.loads(self.cloud_credentials)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _set_cloud_metadata(self, metadata):
        """Persist cloud metadata payload into cloud_credentials."""
        self.cloud_credentials = json.dumps(metadata)

    def get_external_destinations(self):
        """Return normalized list of configured external backup destinations."""
        metadata = self._cloud_metadata()
        raw_destinations = metadata.get('backup_destinations')
        destinations = []

        if isinstance(raw_destinations, list):
            for index, destination in enumerate(raw_destinations):
                if not isinstance(destination, dict):
                    continue
                url = (destination.get('external_url') or destination.get('url') or '').strip()
                if not url:
                    continue
                destinations.append({
                    'id': destination.get('id') or f'destination_{index + 1}',
                    'name': (destination.get('name') or destination.get('label') or f'Destination {index + 1}').strip(),
                    'provider': (destination.get('provider') or 'webdav').strip(),
                    'enabled': bool(destination.get('enabled', True)),
                    'external_url': url,
                    'external_api_key': destination.get('external_api_key') or destination.get('api_key') or '',
                    'external_path': destination.get('external_path') or destination.get('path') or '/GearCargo',
                })

        # Backwards compatibility: include legacy single target if present.
        if self.external_url:
            legacy_url = self.external_url.strip()
            legacy_exists = any(d.get('external_url') == legacy_url for d in destinations)
            if not legacy_exists:
                destinations.insert(0, {
                    'id': 'legacy_primary',
                    'name': 'Primary Destination',
                    'provider': 'webdav',
                    'enabled': bool(self.external_enabled),
                    'external_url': legacy_url,
                    'external_api_key': self.external_api_key or '',
                    'external_path': self.external_path or '/GearCargo',
                })

        return destinations

    def set_external_destinations(self, destinations):
        """Persist external backup destinations and mirror the first one into legacy fields."""
        cleaned = []
        if isinstance(destinations, list):
            for index, destination in enumerate(destinations):
                if not isinstance(destination, dict):
                    continue
                url = (destination.get('external_url') or destination.get('url') or '').strip()
                if not url:
                    continue
                cleaned.append({
                    'id': destination.get('id') or f'destination_{index + 1}',
                    'name': (destination.get('name') or destination.get('label') or f'Destination {index + 1}').strip(),
                    'provider': (destination.get('provider') or 'webdav').strip(),
                    'enabled': bool(destination.get('enabled', True)),
                    'external_url': url,
                    'external_api_key': destination.get('external_api_key') or destination.get('api_key') or '',
                    'external_path': destination.get('external_path') or destination.get('path') or '/GearCargo',
                })

        metadata = self._cloud_metadata()
        metadata['backup_destinations'] = cleaned
        self._set_cloud_metadata(metadata)

        primary = next((destination for destination in cleaned if destination.get('enabled')), cleaned[0] if cleaned else None)
        if primary:
            self.external_enabled = True
            self.external_url = primary.get('external_url')
            self.external_api_key = primary.get('external_api_key') or None
            self.external_path = primary.get('external_path') or '/GearCargo'
        else:
            self.external_enabled = False
            self.external_url = None
            self.external_api_key = None
            self.external_path = None
    
    def calculate_next_run(self):
        """Calculate the next run date based on frequency."""
        from datetime import timedelta
        import calendar
        
        now = datetime.now(timezone.utc)
        
        if self.frequency == 'weekly':
            # Next occurrence of the specified day of week
            days_ahead = self.day_of_week - now.weekday()
            if days_ahead <= 0:  # Target day already happened this week
                days_ahead += 7
            next_date = now.date() + timedelta(days=days_ahead)
            self.next_run_at = datetime.combine(next_date, datetime.min.time().replace(hour=self.hour))
            
        elif self.frequency == 'monthly':
            # Next occurrence on the specified day of month
            year = now.year
            month = now.month
            day = min(self.day_of_month, calendar.monthrange(year, month)[1])
            
            if now.day >= day:  # Already passed this month
                month += 1
                if month > 12:
                    month = 1
                    year += 1
                day = min(self.day_of_month, calendar.monthrange(year, month)[1])
            
            self.next_run_at = datetime(year, month, day, self.hour)
            
        elif self.frequency == 'quarterly':
            # Every 3 months
            year = now.year
            month = now.month
            day = min(self.day_of_month, calendar.monthrange(year, month)[1])
            
            if now.day >= day:
                month += 3
            else:
                month += 3 - 3  # Next quarter
                
            # Find next quarter month
            quarter_months = [1, 4, 7, 10]
            next_quarter = None
            for qm in quarter_months:
                if qm > month:
                    next_quarter = qm
                    break
            if next_quarter is None:
                next_quarter = 1
                year += 1
            
            month = next_quarter
            day = min(self.day_of_month, calendar.monthrange(year, month)[1])
            self.next_run_at = datetime(year, month, day, self.hour)
        
        return self.next_run_at
    
    def to_dict(self):
        """Convert to dictionary."""
        destinations = self.get_external_destinations()
        return {
            'id': self.id,
            'enabled': self.enabled,
            'frequency': self.frequency,
            'day_of_week': self.day_of_week,
            'day_of_month': self.day_of_month,
            'hour': self.hour,
            'backup_type': self.backup_type,
            'include_attachments': self.include_attachments,
            'external_enabled': self.external_enabled,
            'external_url': self.external_url,
            'external_path': self.external_path,
            'has_external_api_key': bool(self.external_api_key),
            'external_destinations': [
                {
                    'id': d.get('id'),
                    'name': d.get('name'),
                    'provider': d.get('provider'),
                    'enabled': d.get('enabled', True),
                    'external_url': d.get('external_url'),
                    'external_path': d.get('external_path'),
                    'has_external_api_key': bool(d.get('external_api_key')),
                }
                for d in destinations
            ],
            'external_destination_count': len(destinations),
            # Don't expose external_api_key
            'cloud_enabled': self.cloud_enabled,
            'cloud_provider': self.cloud_provider,
            'retention_days': self.retention_days,
            'max_backups': self.max_backups,
            'notify_on_success': self.notify_on_success,
            'notify_on_failure': self.notify_on_failure,
            'last_run_at': self.last_run_at.isoformat() if self.last_run_at else None,
            'last_status': self.last_status,
            'last_error': self.last_error,
            'next_run_at': self.next_run_at.isoformat() if self.next_run_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

"""
GearCargo - Attachment Model
"""

from datetime import datetime
from app.utils.timeutils import utc_naive_now
from app import db


class Attachment(db.Model):
    """Attachment model for file uploads."""
    
    __tablename__ = 'attachments'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # File info
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255))
    filepath = db.Column(db.String(500), nullable=False)
    file_type = db.Column(db.String(50))  # MIME type
    file_size = db.Column(db.Integer)  # Bytes
    
    # Metadata
    description = db.Column(db.Text)
    category = db.Column(db.String(50))  # receipt, document, photo, manual, etc.
    tags = db.Column(db.JSON)
    
    # OCR
    ocr_text = db.Column(db.Text)
    ocr_processed = db.Column(db.Boolean, default=False)
    vin_extracted = db.Column(db.String(17))  # If VIN found in document
    
    # Expiry tracking
    expires_at = db.Column(db.Date)
    expiry_notified = db.Column(db.Boolean, default=False)
    
    # Associations
    entry_id = db.Column(db.Integer, db.ForeignKey('entries.id'), index=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey('vehicles.id'), index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=utc_naive_now)
    updated_at = db.Column(db.DateTime, default=utc_naive_now, onupdate=utc_naive_now)
    
    def __repr__(self):
        return f'<Attachment {self.filename}>'
    
    @property
    def is_image(self):
        """Check if attachment is an image."""
        return self.file_type and self.file_type.startswith('image/')
    
    @property
    def is_pdf(self):
        """Check if attachment is a PDF."""
        return self.file_type == 'application/pdf'
    
    @property
    def file_size_human(self):
        """Return human-readable file size.

        R4-01: formats a LOCAL copy. The previous body divided ``self.file_size``
        — the mapped column — in place, so every read (to_dict, the backup
        export, the documents list) shrank the stored value and the next commit
        persisted it. Mirrors ``Backup.file_size_human``.
        """
        if not self.file_size:
            return '0 B'

        size = float(self.file_size)
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            'id': self.id,
            'filename': self.filename,
            'original_filename': self.original_filename,
            'file_type': self.file_type,
            'file_size': self.file_size,
            'file_size_human': self.file_size_human,
            'description': self.description,
            'category': self.category,
            'tags': self.tags,
            'is_image': self.is_image,
            'is_pdf': self.is_pdf,
            'ocr_processed': self.ocr_processed,
            'has_text': bool(self.ocr_text and self.ocr_text.strip()),
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'entry_id': self.entry_id,
            'vehicle_id': self.vehicle_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            # URLs for viewing/downloading
            'url': f'/api/attachments/{self.id}/view',
            'download_url': f'/api/attachments/{self.id}/download',
            'view_url': f'/api/attachments/{self.id}/view',
        }

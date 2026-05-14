"""
GearCargo - App Settings Model

A simple key-value store for runtime-configurable settings.
Values set here override env-var defaults without requiring a restart.

Admin writes via PUT /api/admin/settings.
All reads go through AppSetting.get(key, default) which is safe to call
even before the table exists (returns default on any DB error).
"""

from datetime import datetime, timezone
from app import db


class AppSetting(db.Model):
    """Persistent key-value settings table.

    Keys are short snake_case strings (e.g. 'ollama_model_predict').
    Values are plain text; callers cast as needed.
    """

    __tablename__ = 'app_settings'

    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text, nullable=True)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # ---------------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------------

    @classmethod
    def get(cls, key: str, default: str | None = None) -> str | None:
        """Return the stored value for *key*, or *default* if absent / on error."""
        try:
            row = db.session.get(cls, key)
            return row.value if (row and row.value is not None) else default
        except Exception:
            return default

    @classmethod
    def set(cls, key: str, value: str | None) -> None:
        """Upsert *key* with *value*.  Caller must commit the session."""
        row = db.session.get(cls, key)
        if row is None:
            row = cls(key=key, value=value)
            db.session.add(row)
        else:
            row.value = value
            row.updated_at = datetime.now(timezone.utc)

    def __repr__(self) -> str:
        return f'<AppSetting {self.key}={self.value!r}>'

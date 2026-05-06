"""
GearCargo - Calendar Sync Service
Supports: Google Calendar, Nextcloud, Baikal, Radicale, Generic CalDAV
"""

from datetime import datetime, timedelta, timezone
from flask import current_app
from typing import Optional, Dict, List, Any, Tuple
import logging
from urllib.parse import urlparse
import caldav
from icalendar import Calendar, Event, Alarm
from cryptography.fernet import Fernet
import base64
import hashlib
import uuid

logger = logging.getLogger(__name__)


# ============================================================
# CALENDAR PROVIDERS CONFIGURATION
# ============================================================

CALENDAR_PROVIDERS = {
    'google': {
        'name': 'Google Calendar',
        'caldav_url': 'https://apidata.googleusercontent.com/caldav/v2/{email}/events',
        'requires_oauth': True,
        'help_url': 'https://support.google.com/calendar/answer/37111',
        'setup_guide': '''
            <h4>Google Calendar Setup</h4>
            <ol>
                <li>Go to <a href="https://myaccount.google.com/apppasswords" target="_blank">Google App Passwords</a></li>
                <li>Sign in with your Google account</li>
                <li>Select "Other (Custom name)" and enter "GearCargo"</li>
                <li>Click "Generate" and copy the 16-character password</li>
                <li>Use your Gmail address as username</li>
                <li>Use the generated app password as password</li>
            </ol>
            <p><strong>CalDAV URL:</strong> https://apidata.googleusercontent.com/caldav/v2/{your-email}/events</p>
        '''
    },
    'nextcloud': {
        'name': 'Nextcloud',
        'caldav_url': '{server}/remote.php/dav/calendars/{username}/',
        'requires_oauth': False,
        'help_url': 'https://docs.nextcloud.com/server/latest/user_manual/en/groupware/calendar.html',
        'setup_guide': '''
            <h4>Nextcloud Calendar Setup</h4>
            <ol>
                <li>Log in to your Nextcloud instance</li>
                <li>Go to Settings → Security</li>
                <li>Create a new App Password for "GearCargo"</li>
                <li>Enter your Nextcloud server URL (e.g., https://cloud.example.com)</li>
                <li>Use your Nextcloud username</li>
                <li>Use the generated app password</li>
            </ol>
            <p><strong>CalDAV URL format:</strong> https://your-server/remote.php/dav/calendars/username/</p>
        '''
    },
    'baikal': {
        'name': 'Baïkal',
        'caldav_url': '{server}/dav.php/calendars/{username}/',
        'requires_oauth': False,
        'help_url': 'https://sabre.io/baikal/',
        'setup_guide': '''
            <h4>Baïkal Calendar Setup</h4>
            <ol>
                <li>Log in to your Baïkal admin panel</li>
                <li>Create a user if you haven't already</li>
                <li>Note your Baïkal server URL</li>
                <li>Enter your Baïkal username and password</li>
            </ol>
            <p><strong>CalDAV URL format:</strong> https://your-server/dav.php/calendars/username/</p>
        '''
    },
    'radicale': {
        'name': 'Radicale',
        'caldav_url': '{server}/{username}/',
        'requires_oauth': False,
        'help_url': 'https://radicale.org/v3.html',
        'setup_guide': '''
            <h4>Radicale Calendar Setup</h4>
            <ol>
                <li>Ensure Radicale is running on your server</li>
                <li>Enter your Radicale server URL (e.g., https://cal.example.com)</li>
                <li>Enter your Radicale username and password</li>
                <li>The calendar will be auto-created if it doesn't exist</li>
            </ol>
            <p><strong>CalDAV URL format:</strong> https://your-server/username/</p>
        '''
    },
    'caldav': {
        'name': 'Generic CalDAV',
        'caldav_url': '',
        'requires_oauth': False,
        'help_url': '',
        'setup_guide': '''
            <h4>Generic CalDAV Setup</h4>
            <ol>
                <li>Find your CalDAV server URL from your provider</li>
                <li>Enter the full CalDAV URL to your calendar</li>
                <li>Enter your username and password</li>
                <li>Test the connection to verify settings</li>
            </ol>
            <p><strong>Common CalDAV URL patterns:</strong></p>
            <ul>
                <li>Fastmail: https://caldav.fastmail.com/dav/calendars/user/{email}/</li>
                <li>iCloud: https://caldav.icloud.com/</li>
                <li>Synology: https://your-nas:5001/caldav/username/</li>
            </ul>
        '''
    }
}


# ============================================================
# ENCRYPTION HELPERS
# ============================================================

def get_encryption_key() -> bytes:
    """Derive a symmetric key for credential encryption."""
    key_seed = current_app.config.get('ENCRYPTION_KEY') or current_app.config.get('SECRET_KEY')
    if not key_seed or key_seed in ('', 'dev-secret-key-change-in-production'):
        raise RuntimeError('ENCRYPTION_KEY or SECRET_KEY must be set for credential encryption')
    return base64.urlsafe_b64encode(hashlib.sha256(str(key_seed).encode()).digest())


def encrypt_password(password: str) -> str:
    """Encrypt a password for storage."""
    if not password:
        return ''
    fernet = Fernet(get_encryption_key())
    return fernet.encrypt(password.encode()).decode()


def decrypt_password(encrypted: str) -> str:
    """Decrypt a stored password.

    Falls back to treating the value as plaintext for legacy rows that were
    written before field-level encryption was introduced (S04).  The caller
    will receive the raw credential so CalDAV auth continues to work; the
    value is automatically re-encrypted the next time the user saves their
    calendar settings.
    """
    if not encrypted:
        return ''
    try:
        fernet = Fernet(get_encryption_key())
        return fernet.decrypt(encrypted.encode()).decode()
    except Exception:
        # Not a valid Fernet token — treat as legacy plaintext credential.
        logger.warning(
            '[Security] CalDAV credential could not be decrypted — '
            'treating as legacy plaintext. Re-save calendar settings to encrypt.'
        )
        return encrypted


def _ensure_encrypted(value: str) -> str:
    """Return *value* encrypted with the current key.

    If *value* is already a valid Fernet token for the current key it is
    returned unchanged (idempotent).  If it is plaintext — e.g., a row
    written before encryption was enforced — it is encrypted and the
    ciphertext is returned.  This acts as a one-shot, transparent migration:
    plaintext values are upgraded on the next write without requiring a
    separate migration script.
    """
    if not value:
        return ''
    try:
        Fernet(get_encryption_key()).decrypt(value.encode())
        return value  # already a valid ciphertext for this key
    except Exception:
        logger.warning('[Security] Re-encrypting legacy plaintext CalDAV credential')
        return encrypt_password(value)


def _is_allowed_caldav_url(url: str) -> bool:
    """Validate CalDAV URL scheme.

    GearCargo is a self-hosted application and users frequently run CalDAV
    servers (Nextcloud, Radicale, Baikal) on their local network. Blocking
    private/LAN IP ranges would prevent all such setups, so we allow them.
    We still reject non-HTTP(S) schemes to prevent protocol-level abuse.
    """
    if not url:
        return False

    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        return False

    host = (parsed.hostname or '').lower()
    if not host:
        return False

    return True


def get_user_calendar_sources(user, include_secrets: bool = False) -> List[Dict[str, Any]]:
    """Return normalized calendar sources for the user with legacy fallback."""
    preferences = user.preferences or {}
    raw_sources = preferences.get('calendar_sources')
    sources: List[Dict[str, Any]] = []

    if isinstance(raw_sources, list):
        for source in raw_sources:
            if not isinstance(source, dict):
                continue
            normalized = {
                'id': str(source.get('id') or uuid.uuid4()),
                'name': str(source.get('name') or source.get('provider') or 'caldav').strip()[:120],
                'provider': str(source.get('provider') or 'caldav').strip().lower(),
                'url': str(source.get('url') or '').strip(),
                'username': str(source.get('username') or '').strip(),
                'calendar_id': str(source.get('calendar_id') or '').strip(),
                'enabled': bool(source.get('enabled', True)),
                'has_password': bool(source.get('password')),
            }
            if include_secrets and source.get('password'):
                normalized['password'] = source.get('password')
            sources.append(normalized)

    # Backward compatibility with legacy single-source columns.
    if not sources and user.calendar_provider and user.calendar_url and user.calendar_username:
        legacy_source = {
            'id': 'legacy_primary',
            'name': user.calendar_provider.capitalize(),
            'provider': user.calendar_provider,
            'url': user.calendar_url,
            'username': user.calendar_username,
            'calendar_id': user.calendar_id or '',
            'enabled': bool(user.calendar_enabled),
            'has_password': bool(user.calendar_password),
        }
        if include_secrets and user.calendar_password:
            legacy_source['password'] = user.calendar_password
        sources.append(legacy_source)

    return sources


def set_user_calendar_sources(user, sources: List[Dict[str, Any]]) -> None:
    """Persist calendar sources and keep legacy fields synchronized."""
    preferences = dict(user.preferences or {})
    preferences['calendar_sources'] = sources
    user.preferences = preferences

    primary = next((source for source in sources if source.get('enabled')), None) or (sources[0] if sources else None)
    if primary:
        user.calendar_enabled = bool(primary.get('enabled', True))
        user.calendar_provider = primary.get('provider')
        user.calendar_url = primary.get('url')
        user.calendar_username = primary.get('username')
        # Passwords in `sources` are already encrypted by build_source_for_storage.
        # _ensure_encrypted is an extra safety net for any future caller that
        # bypasses build_source_for_storage (S04).
        user.calendar_password = _ensure_encrypted(primary.get('password', '')) or None
        user.calendar_id = primary.get('calendar_id')
    else:
        user.calendar_enabled = False
        user.calendar_provider = None
        user.calendar_url = None
        user.calendar_username = None
        user.calendar_password = None
        user.calendar_id = None


def validate_calendar_source(source: Dict[str, Any]) -> Optional[str]:
    """Validate a single calendar source payload. Returns an error key."""
    provider = str(source.get('provider') or '').strip().lower()
    url = str(source.get('url') or '').strip()
    username = str(source.get('username') or '').strip()
    source_id = str(source.get('id') or '').strip()

    if not source_id:
        return 'calendar.source.invalid_id'
    if provider not in CALENDAR_PROVIDERS:
        return 'calendar.source.invalid_provider'
    if not url or len(url) > 500:
        return 'calendar.source.invalid_url'
    if not _is_allowed_caldav_url(url):
        return 'calendar.source.https_required'
    if not username or len(username) > 255:
        return 'calendar.source.invalid_username'

    return None


def build_source_for_storage(payload: Dict[str, Any], existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build a secure source object for persistence."""
    existing = existing or {}

    incoming_password = str(payload.get('password') or '').strip()
    encrypted_password = incoming_password and encrypt_password(incoming_password)

    # If no new password was supplied, preserve the stored one — but ensure it
    # is encrypted (migrates legacy plaintext values on the first save after S04).
    preserved_password = _ensure_encrypted(existing.get('password', ''))

    return {
        'id': str(payload.get('id') or existing.get('id') or uuid.uuid4()),
        'name': str(payload.get('name') or existing.get('name') or payload.get('provider') or 'caldav').strip()[:120],
        'provider': str(payload.get('provider') or existing.get('provider') or 'caldav').strip().lower(),
        'url': str(payload.get('url') or existing.get('url') or '').strip(),
        'username': str(payload.get('username') or existing.get('username') or '').strip(),
        'calendar_id': str(payload.get('calendar_id') or existing.get('calendar_id') or '').strip(),
        'enabled': bool(payload.get('enabled', existing.get('enabled', True))),
        # Keep current secret when password is omitted from update payload.
        'password': encrypted_password or preserved_password,
    }


# ============================================================
# CALENDAR SERVICE CLASS
# ============================================================

class CalendarService:
    """Service for syncing with CalDAV calendars."""
    
    def __init__(self, user, source: Optional[Dict[str, Any]] = None):
        """Initialize for a specific source; falls back to legacy fields."""
        self.user = user
        self.source = source or {
            'provider': user.calendar_provider,
            'url': user.calendar_url,
            'username': user.calendar_username,
            'password': user.calendar_password,
            'calendar_id': user.calendar_id,
            'enabled': bool(user.calendar_enabled),
            'name': user.calendar_provider or 'caldav',
            'id': 'legacy_primary',
        }
        self.client = None
        self.calendar = None
        self._connected = False
    
    @property
    def is_configured(self) -> bool:
        """Check if calendar is configured for this user."""
        return bool(
            self.source.get('enabled', True) and
            self.source.get('provider') and
            self.source.get('url') and
            self.source.get('username')
        )
    
    def connect(self) -> Tuple[bool, str]:
        """Connect to the CalDAV server."""
        if not self.is_configured:
            return False, "Calendar not configured"
        
        try:
            password = decrypt_password(self.source.get('password') or '')

            url = self.source.get('url', '').rstrip('/')
            provider = self.source.get('provider', '').lower()

            # Nextcloud: append CalDAV base path when user only enters server root
            if provider == 'nextcloud' and '/remote.php/dav' not in url:
                url = url + '/remote.php/dav'

            self.client = caldav.DAVClient(
                url=url,
                username=self.source.get('username'),
                password=password,
                timeout=30,
            )
            
            # Try to get the principal (validates credentials)
            principal = self.client.principal()
            
            # Get or create calendar
            calendars = principal.calendars()
            
            requested_calendar_id = self.source.get('calendar_id')
            if requested_calendar_id:
                # Try to find specific calendar
                for cal in calendars:
                    cal_id = str(cal.id) if hasattr(cal, 'id') else str(getattr(cal, 'url', ''))
                    cal_name = str(cal.name) if hasattr(cal, 'name') else ''
                    if requested_calendar_id in {cal_id, cal_name}:
                        self.calendar = cal
                        break
            
            if not self.calendar and calendars:
                # Use first available calendar
                self.calendar = calendars[0]
            
            if not self.calendar:
                # Try to create a new calendar
                try:
                    self.calendar = principal.make_calendar(name="GearCargo")
                except Exception as e:
                    logger.warning(
                        f"Could not create default 'GearCargo' calendar on server "
                        f"(url={self.source.get('url', '?')!r}): {e}"
                    )
                    return False, "No calendars found and couldn't create one"
            
            self._connected = True
            calendar_name = self.calendar.name if hasattr(self.calendar, 'name') else 'Default'
            return True, f"Connected to calendar: {calendar_name}"
            
        except caldav.lib.error.AuthorizationError:
            return False, "Authentication failed. Check username and password."
        except caldav.lib.error.NotFoundError:
            return False, "Calendar URL not found. Check the URL."
        except Exception as e:
            logger.error(f"Calendar connection error: {e}")
            return False, f"Connection failed: {str(e)}"
    
    def get_calendars(self) -> List[Dict[str, str]]:
        """Get list of available calendars."""
        if not self._connected:
            success, _ = self.connect()
            if not success:
                return []
        
        try:
            principal = self.client.principal()
            calendars = principal.calendars()
            return [
                {
                    'id': str(cal.id) if hasattr(cal, 'id') else str(cal.url),
                    'name': cal.name if hasattr(cal, 'name') else 'Calendar'
                }
                for cal in calendars
            ]
        except Exception as e:
            logger.error(f"Failed to get calendars: {e}")
            return []
    
    def create_event(
        self,
        title: str,
        start: datetime,
        end: datetime = None,
        description: str = None,
        location: str = None,
        all_day: bool = False,
        reminder_minutes: int = 60,
        uid: str = None
    ) -> Tuple[bool, str]:
        """Create a calendar event."""
        if not self._connected:
            success, msg = self.connect()
            if not success:
                return False, msg
        
        try:
            # Create iCalendar event
            cal = Calendar()
            cal.add('prodid', '-//GearCargo//Vehicle Management//EN')
            cal.add('version', '2.0')
            
            event = Event()
            event.add('uid', uid or str(uuid.uuid4()))
            event.add('dtstamp', datetime.now(timezone.utc))
            event.add('summary', title)
            
            if all_day:
                event.add('dtstart', start.date() if isinstance(start, datetime) else start)
                if end:
                    event.add('dtend', end.date() if isinstance(end, datetime) else end)
            else:
                event.add('dtstart', start)
                event.add('dtend', end or start + timedelta(hours=1))
            
            if description:
                event.add('description', description)
            
            if location:
                event.add('location', location)
            
            # Add reminder/alarm
            if reminder_minutes > 0:
                alarm = Alarm()
                alarm.add('action', 'DISPLAY')
                alarm.add('trigger', timedelta(minutes=-reminder_minutes))
                alarm.add('description', f'Reminder: {title}')
                event.add_component(alarm)
            
            cal.add_component(event)
            
            # Save to CalDAV server
            self.calendar.save_event(cal.to_ical().decode('utf-8'))
            
            logger.info(f"Calendar event created: {title}")
            return True, event['uid']
            
        except Exception as e:
            logger.error(f"Failed to create calendar event: {e}")
            return False, str(e)
    
    def update_event(self, uid: str, **kwargs) -> Tuple[bool, str]:
        """Update an existing calendar event."""
        if not self._connected:
            success, msg = self.connect()
            if not success:
                return False, msg
        
        try:
            # Find and delete existing event
            events = self.calendar.search(uid=uid)
            if events:
                events[0].delete()
            
            # Create updated event with same UID
            return self.create_event(uid=uid, **kwargs)
            
        except Exception as e:
            logger.error(f"Failed to update calendar event: {e}")
            return False, str(e)
    
    def delete_event(self, uid: str) -> Tuple[bool, str]:
        """Delete a calendar event."""
        if not self._connected:
            success, msg = self.connect()
            if not success:
                return False, msg
        
        try:
            events = self.calendar.search(uid=uid)
            if events:
                events[0].delete()
                logger.info(f"Calendar event deleted: {uid}")
                return True, "Event deleted"
            return True, "Event not found (may already be deleted)"
            
        except Exception as e:
            logger.error(f"Failed to delete calendar event: {e}")
            return False, str(e)


# ============================================================
# ENTRY SYNC HELPERS
# ============================================================

def sync_entry_to_calendar(user, entry_type: str, entry: Any, action: str = 'create') -> Tuple[bool, str]:
    """
    Sync a vehicle entry to the user's calendar.
    
    Args:
        user: User object with calendar settings
        entry_type: Type of entry ('service', 'repair', 'reminder', 'insurance', 'tax')
        entry: The entry object to sync
        action: 'create', 'update', or 'delete'
    
    Returns:
        Tuple of (success, message)
    """
    if not user.calendar_enabled:
        return True, "Calendar sync disabled"

    sources = [source for source in get_user_calendar_sources(user, include_secrets=True) if source.get('enabled')]
    if not sources:
        return True, "Calendar not configured"
    
    try:
        # Get vehicle name for context
        vehicle_name = ""
        if hasattr(entry, 'vehicle') and entry.vehicle:
            vehicle_name = f"{entry.vehicle.make} {entry.vehicle.model}" if entry.vehicle.make else entry.vehicle.nickname or "Vehicle"
        
        # Generate UID for tracking
        uid = f"gearcargo-{entry_type}-{entry.id}@gearcargo.local"
        
        # Build event details based on entry type
        event_data = get_event_data_for_entry(entry_type, entry, vehicle_name)
        
        if not event_data:
            return False, f"Unknown entry type: {entry_type}"
        
        failures = []
        success_count = 0

        for source in sources:
            calendar_service = CalendarService(user, source)
            if action == 'delete':
                success, result = calendar_service.delete_event(uid)
            else:
                success, result = calendar_service.create_event(
                    uid=uid,
                    title=event_data['title'],
                    start=event_data['start'],
                    end=event_data.get('end'),
                    description=event_data.get('description'),
                    location=event_data.get('location'),
                    all_day=event_data.get('all_day', True),
                    reminder_minutes=event_data.get('reminder_minutes', 1440)
                )

            if success:
                success_count += 1
            else:
                source_name = source.get('name') or source.get('provider') or source.get('id')
                failures.append(f"{source_name}: {result}")

        if success_count == 0 and failures:
            return False, '; '.join(failures)
        if failures:
            return True, f"Synced to {success_count}/{len(sources)} sources. Failures: {'; '.join(failures)}"

        return True, f"Synced to {success_count} source(s)"
        
    except Exception as e:
        logger.error(f"Calendar sync error: {e}")
        return False, str(e)


def get_event_data_for_entry(entry_type: str, entry: Any, vehicle_name: str) -> Optional[Dict]:
    """Generate event data based on entry type."""
    
    if entry_type == 'service':
        # Service entry
        title = f"🔧 Service Due: {vehicle_name}"
        if hasattr(entry, 'service_type') and entry.service_type:
            title = f"🔧 {entry.service_type}: {vehicle_name}"
        
        # Use next_service_date if available, otherwise scheduled date
        event_date = getattr(entry, 'next_service_date', None) or getattr(entry, 'date', None)
        if not event_date:
            return None
        
        description = f"Vehicle: {vehicle_name}\n"
        if hasattr(entry, 'service_type'):
            description += f"Service: {entry.service_type}\n"
        if hasattr(entry, 'notes') and entry.notes:
            description += f"Notes: {entry.notes}\n"
        if hasattr(entry, 'mileage') and entry.mileage:
            description += f"Mileage: {entry.mileage}\n"
        
        return {
            'title': title,
            'start': event_date if isinstance(event_date, datetime) else datetime.combine(event_date, datetime.min.time()),
            'description': description,
            'all_day': True,
            'reminder_minutes': 1440  # 1 day before
        }
    
    elif entry_type == 'repair':
        title = f"🛠️ Repair: {vehicle_name}"
        if hasattr(entry, 'description') and entry.description:
            title = f"🛠️ {entry.description[:30]}: {vehicle_name}"
        
        event_date = getattr(entry, 'date', None)
        if not event_date:
            return None
        
        description = f"Vehicle: {vehicle_name}\n"
        if hasattr(entry, 'description') and entry.description:
            description += f"Repair: {entry.description}\n"
        if hasattr(entry, 'cost') and entry.cost:
            description += f"Cost: {entry.cost}\n"
        if hasattr(entry, 'notes') and entry.notes:
            description += f"Notes: {entry.notes}\n"
        
        return {
            'title': title,
            'start': event_date if isinstance(event_date, datetime) else datetime.combine(event_date, datetime.min.time()),
            'description': description,
            'all_day': True,
            'reminder_minutes': 0  # No reminder for past repairs
        }
    
    elif entry_type == 'reminder':
        title = f"📅 {entry.title}: {vehicle_name}" if vehicle_name else f"📅 {entry.title}"
        
        event_date = getattr(entry, 'due_date', None)
        if not event_date:
            return None
        
        description = f"Reminder: {entry.title}\n"
        if hasattr(entry, 'notes') and entry.notes:
            description += f"Notes: {entry.notes}\n"
        if vehicle_name:
            description += f"Vehicle: {vehicle_name}\n"
        
        return {
            'title': title,
            'start': event_date if isinstance(event_date, datetime) else datetime.combine(event_date, datetime.min.time()),
            'description': description,
            'all_day': True,
            'reminder_minutes': 1440
        }
    
    elif entry_type == 'insurance':
        title = f"🛡️ Insurance Expiry: {vehicle_name}"
        
        event_date = getattr(entry, 'end_date', None)
        if not event_date:
            return None
        
        description = f"Vehicle: {vehicle_name}\n"
        description += "Insurance policy expires on this date.\n"
        if hasattr(entry, 'provider') and entry.provider:
            description += f"Provider: {entry.provider}\n"
        if hasattr(entry, 'policy_number') and entry.policy_number:
            description += f"Policy #: {entry.policy_number}\n"
        
        return {
            'title': title,
            'start': event_date if isinstance(event_date, datetime) else datetime.combine(event_date, datetime.min.time()),
            'description': description,
            'all_day': True,
            'reminder_minutes': 10080  # 7 days before
        }
    
    elif entry_type == 'tax':
        title = f"📋 Road Tax Due: {vehicle_name}"
        
        event_date = getattr(entry, 'due_date', None) or getattr(entry, 'end_date', None)
        if not event_date:
            return None
        
        description = f"Vehicle: {vehicle_name}\n"
        description += "Road tax payment due on this date.\n"
        if hasattr(entry, 'amount') and entry.amount:
            description += f"Amount: {entry.amount}\n"
        
        return {
            'title': title,
            'start': event_date if isinstance(event_date, datetime) else datetime.combine(event_date, datetime.min.time()),
            'description': description,
            'all_day': True,
            'reminder_minutes': 10080  # 7 days before
        }

    elif entry_type == 'fuel':
        liters = getattr(entry, 'liters', None)
        total_price = getattr(entry, 'total_price', None) or getattr(entry, 'amount', None)
        fuel_type = getattr(entry, 'fuel_type', None)
        station = getattr(entry, 'station', None)

        parts = []
        if liters:
            parts.append(f"{float(liters):.1f}L")
        if total_price:
            parts.append(f"{float(total_price):.2f}")
        title = f"⛽ Fuel: {vehicle_name}" + (f" ({', '.join(parts)})" if parts else "")

        event_date = getattr(entry, 'date', None)
        if not event_date:
            return None

        description = f"Vehicle: {vehicle_name}\n"
        if fuel_type:
            description += f"Fuel Type: {fuel_type}\n"
        if liters:
            description += f"Volume: {float(liters):.2f} L\n"
        if total_price:
            description += f"Total Cost: {float(total_price):.2f}\n"
        if station:
            description += f"Station: {station}\n"
        if hasattr(entry, 'notes') and entry.notes:
            description += f"Notes: {entry.notes}\n"

        return {
            'title': title,
            'start': event_date if isinstance(event_date, datetime) else datetime.combine(event_date, datetime.min.time()),
            'description': description,
            'all_day': True,
            'reminder_minutes': 0,
        }

    elif entry_type == 'parking':
        amount = getattr(entry, 'amount', None)
        location = getattr(entry, 'location', None) or getattr(entry, 'title', None)

        title = f"🅿️ Parking: {vehicle_name}"
        if location:
            title += f" @ {location}"

        event_date = getattr(entry, 'date', None)
        if not event_date:
            return None

        description = f"Vehicle: {vehicle_name}\n"
        if location:
            description += f"Location: {location}\n"
        if amount:
            description += f"Cost: {float(amount):.2f}\n"
        parking_type = getattr(entry, 'parking_type', None)
        if parking_type:
            description += f"Type: {parking_type}\n"
        if hasattr(entry, 'notes') and entry.notes:
            description += f"Notes: {entry.notes}\n"

        return {
            'title': title,
            'start': event_date if isinstance(event_date, datetime) else datetime.combine(event_date, datetime.min.time()),
            'description': description,
            'all_day': True,
            'reminder_minutes': 0,
        }

    return None


def sync_all_entries_for_user(user) -> Dict[str, Any]:
    """Sync all vehicle entries to calendar for a user."""
    from app.models import ServiceEntry, Reminder, InsurancePolicy, TaxEntry, Vehicle
    
    results = {
        'synced': 0,
        'failed': 0,
        'errors': []
    }
    
    if not user.calendar_enabled:
        return results

    configured_sources = [source for source in get_user_calendar_sources(user, include_secrets=True) if source.get('enabled')]
    if not configured_sources:
        return results
    
    # Get all user's vehicles
    vehicles = Vehicle.query.filter_by(user_id=user.id).all()
    
    for vehicle in vehicles:
        # Sync services
        services = ServiceEntry.query.filter_by(vehicle_id=vehicle.id).all()
        for service in services:
            success, msg = sync_entry_to_calendar(user, 'service', service)
            if success:
                results['synced'] += 1
            else:
                results['failed'] += 1
                results['errors'].append(f"Service {service.id}: {msg}")
        
        # Sync reminders
        reminders = Reminder.query.filter_by(vehicle_id=vehicle.id).all()
        for reminder in reminders:
            success, msg = sync_entry_to_calendar(user, 'reminder', reminder)
            if success:
                results['synced'] += 1
            else:
                results['failed'] += 1
                results['errors'].append(f"Reminder {reminder.id}: {msg}")
        
        # Sync insurance
        policies = InsurancePolicy.query.filter_by(vehicle_id=vehicle.id).all()
        for policy in policies:
            success, msg = sync_entry_to_calendar(user, 'insurance', policy)
            if success:
                results['synced'] += 1
            else:
                results['failed'] += 1
                results['errors'].append(f"Insurance {policy.id}: {msg}")
        
        # Sync taxes
        taxes = TaxEntry.query.filter_by(vehicle_id=vehicle.id).all()
        for tax in taxes:
            success, msg = sync_entry_to_calendar(user, 'tax', tax)
            if success:
                results['synced'] += 1
            else:
                results['failed'] += 1
                results['errors'].append(f"Tax {tax.id}: {msg}")
    
    logger.info(f"Calendar sync complete for user {user.id}: {results['synced']} synced, {results['failed']} failed")
    return results


# ============================================================
# PROVIDER HELPERS
# ============================================================

def get_provider_info(provider: str) -> Optional[Dict]:
    """Get information about a calendar provider."""
    return CALENDAR_PROVIDERS.get(provider)


def get_all_providers() -> List[Dict]:
    """Get list of all supported providers."""
    return [
        {'id': key, 'setup_guide_key': f'settings.calendarSetupGuide.{key}',
         **{k: v for k, v in val.items() if k != 'setup_guide'}}
        for key, val in CALENDAR_PROVIDERS.items()
    ]


def build_caldav_url(provider: str, server: str, username: str, email: str = None) -> str:
    """Build the CalDAV URL for a provider."""
    provider_info = CALENDAR_PROVIDERS.get(provider)
    if not provider_info:
        return server
    
    url_template = provider_info.get('caldav_url', '')
    if not url_template:
        return server
    
    # Clean up server URL
    server = server.rstrip('/')
    
    return url_template.format(
        server=server,
        username=username,
        email=email or username
    )

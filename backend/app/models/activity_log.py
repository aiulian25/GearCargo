"""
GearCargo - Activity Log Model
"""

from datetime import datetime
from app import db


class ActivityLog(db.Model):
    """Activity log for tracking user actions and system events."""
    
    __tablename__ = 'activity_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    
    # Event info
    event_type = db.Column(db.String(50), nullable=False, index=True)  # login, logout, password_change, 2fa_enable, etc.
    event_category = db.Column(db.String(30), nullable=False, default='auth', index=True)  # auth, vehicle, entry, admin, system
    description = db.Column(db.String(500))
    
    # Request context
    ip_address = db.Column(db.String(45))  # IPv6 can be up to 45 chars
    user_agent = db.Column(db.String(500))
    
    # Device info (parsed from user agent)
    device_type = db.Column(db.String(50))  # desktop, mobile, tablet
    browser = db.Column(db.String(100))
    browser_version = db.Column(db.String(20))
    os = db.Column(db.String(100))
    os_version = db.Column(db.String(20))
    
    # Language/Locale
    device_language = db.Column(db.String(20))  # From Accept-Language header
    
    # Geolocation (from IP)
    country = db.Column(db.String(100))
    country_code = db.Column(db.String(5))
    city = db.Column(db.String(100))
    region = db.Column(db.String(100))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    
    # Status
    success = db.Column(db.Boolean, default=True)
    error_message = db.Column(db.String(500))
    
    # Additional data (JSON for flexible storage)
    extra_data = db.Column(db.JSON, default=dict)
    
    # Timestamp
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    # Relationship
    user = db.relationship('User', backref=db.backref('activity_logs', lazy='dynamic'))
    
    def __repr__(self):
        return f'<ActivityLog {self.id} - {self.event_type}>'
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'user_email': self.user.email if self.user else None,
            'user_name': self.user.first_name if self.user else None,
            'event_type': self.event_type,
            'event_category': self.event_category,
            'description': self.description,
            'ip_address': self.ip_address,
            'device_type': self.device_type,
            'browser': self.browser,
            'browser_version': self.browser_version,
            'os': self.os,
            'os_version': self.os_version,
            'device_language': self.device_language,
            'country': self.country,
            'country_code': self.country_code,
            'city': self.city,
            'region': self.region,
            'success': self.success,
            'error_message': self.error_message,
            'extra_data': self.extra_data,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
    
    @classmethod
    def log(cls, event_type, event_category='auth', user_id=None, description=None,
            ip_address=None, user_agent=None, success=True, error_message=None, extra_data=None):
        """Create a new activity log entry."""
        from flask import request, has_request_context
        
        log_entry = cls(
            event_type=event_type,
            event_category=event_category,
            user_id=user_id,
            description=description,
            success=success,
            error_message=error_message,
            extra_data=extra_data or {},
        )
        
        # Get request context if available
        if has_request_context():
            # IP Address
            log_entry.ip_address = ip_address or cls._get_client_ip(request)
            
            # User Agent
            ua_string = user_agent or request.headers.get('User-Agent', '')
            log_entry.user_agent = ua_string[:500] if ua_string else None
            
            # Parse user agent for device info
            device_info = cls._parse_user_agent(ua_string)
            log_entry.device_type = device_info.get('device_type')
            log_entry.browser = device_info.get('browser')
            log_entry.browser_version = device_info.get('browser_version')
            log_entry.os = device_info.get('os')
            log_entry.os_version = device_info.get('os_version')
            
            # Language from Accept-Language header
            accept_lang = request.headers.get('Accept-Language', '')
            if accept_lang:
                # Get primary language
                primary_lang = accept_lang.split(',')[0].split(';')[0].strip()
                log_entry.device_language = primary_lang[:20] if primary_lang else None
        
        # Try to get geolocation from IP (async, don't block)
        if log_entry.ip_address:
            geo_info = cls._get_geo_from_ip(log_entry.ip_address)
            if geo_info:
                log_entry.country = geo_info.get('country')
                log_entry.country_code = geo_info.get('country_code')
                log_entry.city = geo_info.get('city')
                log_entry.region = geo_info.get('region')
                log_entry.latitude = geo_info.get('latitude')
                log_entry.longitude = geo_info.get('longitude')
        
        db.session.add(log_entry)
        
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Failed to log activity: {e}")
        
        return log_entry
    
    @staticmethod
    def _get_client_ip(request):
        """Get the real client IP address, considering proxies."""
        # Check X-Forwarded-For header (common with proxies/load balancers)
        if request.headers.get('X-Forwarded-For'):
            # Get the first IP in the chain
            ip = request.headers['X-Forwarded-For'].split(',')[0].strip()
        elif request.headers.get('X-Real-IP'):
            ip = request.headers['X-Real-IP']
        else:
            ip = request.remote_addr
        
        return ip
    
    @staticmethod
    def _parse_user_agent(ua_string):
        """Parse user agent string for device info."""
        if not ua_string:
            return {}
        
        result = {
            'device_type': 'desktop',
            'browser': None,
            'browser_version': None,
            'os': None,
            'os_version': None,
        }
        
        ua_lower = ua_string.lower()
        
        # Device type
        if 'mobile' in ua_lower or 'android' in ua_lower and 'mobile' in ua_lower:
            result['device_type'] = 'mobile'
        elif 'tablet' in ua_lower or 'ipad' in ua_lower:
            result['device_type'] = 'tablet'
        
        # Browser detection
        if 'firefox' in ua_lower:
            result['browser'] = 'Firefox'
            import re
            match = re.search(r'firefox[/\s]?([\d.]+)', ua_lower)
            if match:
                result['browser_version'] = match.group(1)
        elif 'edg/' in ua_lower or 'edge/' in ua_lower:
            result['browser'] = 'Edge'
            import re
            match = re.search(r'edg[e]?[/\s]?([\d.]+)', ua_lower)
            if match:
                result['browser_version'] = match.group(1)
        elif 'chrome' in ua_lower and 'chromium' not in ua_lower:
            result['browser'] = 'Chrome'
            import re
            match = re.search(r'chrome[/\s]?([\d.]+)', ua_lower)
            if match:
                result['browser_version'] = match.group(1)
        elif 'safari' in ua_lower and 'chrome' not in ua_lower:
            result['browser'] = 'Safari'
            import re
            match = re.search(r'version[/\s]?([\d.]+)', ua_lower)
            if match:
                result['browser_version'] = match.group(1)
        elif 'opera' in ua_lower or 'opr/' in ua_lower:
            result['browser'] = 'Opera'
        
        # OS detection
        if 'windows' in ua_lower:
            result['os'] = 'Windows'
            if 'windows nt 10' in ua_lower:
                result['os_version'] = '10/11'
            elif 'windows nt 6.3' in ua_lower:
                result['os_version'] = '8.1'
            elif 'windows nt 6.1' in ua_lower:
                result['os_version'] = '7'
        elif 'mac os x' in ua_lower or 'macintosh' in ua_lower:
            result['os'] = 'macOS'
            import re
            match = re.search(r'mac os x[/\s]?([\d_]+)', ua_lower)
            if match:
                result['os_version'] = match.group(1).replace('_', '.')
        elif 'android' in ua_lower:
            # Check Android BEFORE Linux since Android UA contains "Linux"
            result['os'] = 'Android'
            import re
            match = re.search(r'android[/\s]?([\d.]+)', ua_lower)
            if match:
                result['os_version'] = match.group(1)
        elif 'iphone' in ua_lower or 'ipad' in ua_lower:
            result['os'] = 'iOS'
            import re
            match = re.search(r'os[/\s]?([\d_]+)', ua_lower)
            if match:
                result['os_version'] = match.group(1).replace('_', '.')
        elif 'linux' in ua_lower:
            result['os'] = 'Linux'
            if 'ubuntu' in ua_lower:
                result['os'] = 'Ubuntu'
            elif 'fedora' in ua_lower:
                result['os'] = 'Fedora'
        
        return result
    
    @staticmethod
    def _get_geo_from_ip(ip_address):
        """Get geolocation data from IP address using free API."""
        # Skip private/local IPs
        if not ip_address or ip_address.startswith(('127.', '10.', '192.168.', '172.', '::1', 'localhost')):
            return None
        
        try:
            import requests
            # Using ip-api.com free API (no key needed, 45 requests/min limit)
            response = requests.get(
                f'http://ip-api.com/json/{ip_address}',
                timeout=2,
                params={'fields': 'status,country,countryCode,region,regionName,city,lat,lon'}
            )
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'success':
                    return {
                        'country': data.get('country'),
                        'country_code': data.get('countryCode'),
                        'region': data.get('regionName'),
                        'city': data.get('city'),
                        'latitude': data.get('lat'),
                        'longitude': data.get('lon'),
                    }
        except Exception as e:
            # Don't fail the request if geo lookup fails
            print(f"Geo lookup failed for {ip_address}: {e}")
        
        return None

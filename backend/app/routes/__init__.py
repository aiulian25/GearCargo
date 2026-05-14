"""
GearCargo - Routes Package
"""

from app.routes.auth import auth_bp
from app.routes.vehicles import vehicles_bp
from app.routes.fuel import fuel_bp
from app.routes.services import services_bp
from app.routes.repairs import repairs_bp
from app.routes.taxes import taxes_bp
from app.routes.parking import parking_bp
from app.routes.reminders import reminders_bp
from app.routes.predictions import predictions_bp
from app.routes.attachments import attachments_bp
from app.routes.insurance import insurance_bp
from app.routes.backup import backup_bp
from app.routes.calendar_sync import calendar_bp
from app.routes.admin import admin_bp
from app.routes.push import push_bp
from app.routes.external import external_bp
from app.routes.todos import todos_bp
from app.routes.reports import reports_bp
from app.routes.widget import widget_bp
from app.routes.search import search_bp

__all__ = [
    'auth_bp',
    'vehicles_bp',
    'fuel_bp',
    'services_bp',
    'repairs_bp',
    'taxes_bp',
    'parking_bp',
    'reminders_bp',
    'predictions_bp',
    'attachments_bp',
    'insurance_bp',
    'backup_bp',
    'calendar_bp',
    'admin_bp',
    'push_bp',
    'external_bp',
    'todos_bp',
    'reports_bp',
    'widget_bp',
    'search_bp',
]


def register_blueprints(app):
    """Register all blueprints with the app."""
    from app import csrf
    
    # List of all API blueprints
    blueprints = [
        (auth_bp, '/api/auth'),
        (vehicles_bp, '/api/vehicles'),
        (fuel_bp, '/api/fuel'),
        (services_bp, '/api/services'),
        (repairs_bp, '/api/repairs'),
        (taxes_bp, '/api/taxes'),
        (parking_bp, '/api/parking'),
        (reminders_bp, '/api/reminders'),
        (predictions_bp, '/api/predictions'),
        (attachments_bp, '/api/attachments'),
        (insurance_bp, '/api/insurance'),
        (backup_bp, '/api/backup'),
        (calendar_bp, '/api/calendar'),
        (admin_bp, '/api/admin'),
        (push_bp, '/api/push'),
        (external_bp, '/api/external'),
        (todos_bp, '/api/todos'),
        (reports_bp, '/api/reports'),
        (widget_bp, '/api/widget'),
        (search_bp, '/api/search'),
    ]
    
    for bp, prefix in blueprints:
        app.register_blueprint(bp, url_prefix=prefix)
        # Exempt from CSRF - API routes use JWT authentication which is CSRF-safe
        csrf.exempt(bp)

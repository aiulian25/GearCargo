"""
GearCargo - Email Notification Service
Handles all email notifications: alerts, reminders, reports
"""

from datetime import datetime, date, timedelta
from flask import current_app, render_template_string
from flask_mail import Message
from app import mail, db
from typing import List, Dict, Optional, Any
import logging
import re

logger = logging.getLogger(__name__)


# ============================================================
# EMAIL TEMPLATES
# ============================================================

BASE_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif; margin: 0; padding: 0; background-color: #0f172a; color: #e2e8f0; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%); padding: 30px; border-radius: 12px 12px 0 0; text-align: center; }
        .header-logo { width: 80px; height: 80px; margin-bottom: 15px; border-radius: 16px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); }
        .header h1 { color: #ffffff; margin: 0; font-size: 24px; }
        .header-subtitle { color: rgba(255,255,255,0.8); font-size: 14px; margin-top: 5px; }
        .content { background-color: #1e293b; padding: 30px; border-radius: 0 0 12px 12px; }
        .alert-card { background-color: #0f172a; border-radius: 8px; padding: 20px; margin-bottom: 15px; border-left: 4px solid #2563eb; }
        .alert-card.urgent { border-left-color: #ef4444; }
        .alert-card.warning { border-left-color: #f59e0b; }
        .alert-card.info { border-left-color: #3b82f6; }
        .alert-title { font-size: 16px; font-weight: 600; color: #f1f5f9; margin-bottom: 5px; }
        .alert-subtitle { font-size: 14px; color: #94a3b8; margin-bottom: 10px; }
        .alert-detail { font-size: 13px; color: #64748b; }
        .vehicle-badge { display: inline-block; background-color: #3b82f6; color: white; padding: 4px 10px; border-radius: 12px; font-size: 12px; margin-bottom: 10px; }
        .btn { display: inline-block; background-color: #2563eb; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: 500; margin-top: 20px; }
        .btn:hover { background-color: #1d4ed8; }
        .footer { text-align: center; padding: 20px; color: #64748b; font-size: 12px; }
        .footer a { color: #3b82f6; text-decoration: none; }
        .footer-logo { width: 40px; height: 40px; margin-bottom: 10px; border-radius: 8px; opacity: 0.8; }
        .divider { border-top: 1px solid #334155; margin: 20px 0; }
        .stat-row { display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #334155; }
        .stat-label { color: #94a3b8; }
        .stat-value { color: #f1f5f9; font-weight: 500; }
        .summary-box { background-color: #0f172a; border-radius: 8px; padding: 15px; margin: 15px 0; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 10px; text-align: left; border-bottom: 1px solid #334155; }
        th { color: #94a3b8; font-weight: 500; font-size: 12px; text-transform: uppercase; }
        td { color: #e2e8f0; font-size: 14px; }
        .currency { font-family: monospace; }
    </style>
</head>
<body>
    <div class="container">
        {{ content | safe }}
        <div class="footer">
            <img src="{{ logo_url }}" alt="GearCargo" class="footer-logo">
            <p>© {{ year }} GearCargo - Vehicle Management</p>
            <p>
                <a href="{{ app_url }}">Open App</a> | 
                <a href="{{ app_url }}/settings">Manage Notifications</a>
            </p>
            <p style="margin-top: 10px; font-size: 11px;">
                You received this email because you have email notifications enabled.<br>
                To unsubscribe, visit your settings page.
            </p>
        </div>
    </div>
</body>
</html>
"""

ALERT_REMINDER_TEMPLATE = """
<div class="header">
    <img src="{{ logo_url }}" alt="GearCargo" class="header-logo">
    <h1>🔔 {{ title }}</h1>
    <p class="header-subtitle">Vehicle Notification</p>
</div>
<div class="content">
    <p>Hi {{ user_name }},</p>
    <p>{{ intro_text }}</p>
    
    {% for alert in alerts %}
    <div class="alert-card {{ alert.severity }}">
        {% if alert.vehicle %}
        <span class="vehicle-badge">{{ alert.vehicle }}</span>
        {% endif %}
        <div class="alert-title">{{ alert.title }}</div>
        <div class="alert-subtitle">{{ alert.subtitle }}</div>
        {% if alert.details %}
        <div class="alert-detail">{{ alert.details }}</div>
        {% endif %}
    </div>
    {% endfor %}
    
    <a href="{{ app_url }}" class="btn">View in GearCargo</a>
</div>
"""

WEEKLY_REPORT_TEMPLATE = """
<div class="header">
    <img src="{{ logo_url }}" alt="GearCargo" class="header-logo">
    <h1>📊 Weekly Report</h1>
    <p class="header-subtitle">Your Vehicle Summary</p>
</div>
<div class="content">
    <p>Hi {{ user_name }},</p>
    <p>Here's your vehicle activity summary for the past week ({{ period }}).</p>
    
    <div class="summary-box">
        <h3 style="margin-top: 0; color: #f1f5f9;">Summary</h3>
        <div class="stat-row">
            <span class="stat-label">Total Vehicles</span>
            <span class="stat-value">{{ summary.total_vehicles }}</span>
        </div>
        <div class="stat-row">
            <span class="stat-label">Fuel Entries</span>
            <span class="stat-value">{{ summary.fuel_entries }}</span>
        </div>
        <div class="stat-row">
            <span class="stat-label">Total Fuel Spent</span>
            <span class="stat-value currency">{{ summary.currency }}{{ summary.fuel_spent }}</span>
        </div>
        <div class="stat-row">
            <span class="stat-label">Services Performed</span>
            <span class="stat-value">{{ summary.services }}</span>
        </div>
        <div class="stat-row">
            <span class="stat-label">Distance Traveled</span>
            <span class="stat-value">{{ summary.distance }} {{ summary.distance_unit }}</span>
        </div>
    </div>
    
    {% if upcoming_alerts %}
    <div class="divider"></div>
    <h3 style="color: #f1f5f9;">🔔 Upcoming Alerts</h3>
    {% for alert in upcoming_alerts %}
    <div class="alert-card {{ alert.severity }}">
        {% if alert.vehicle %}
        <span class="vehicle-badge">{{ alert.vehicle }}</span>
        {% endif %}
        <div class="alert-title">{{ alert.title }}</div>
        <div class="alert-subtitle">Due: {{ alert.due_date }}</div>
    </div>
    {% endfor %}
    {% endif %}
    
    <a href="{{ app_url }}" class="btn">View Full Dashboard</a>
</div>
"""

MONTHLY_REPORT_TEMPLATE = """
<div class="header">
    <img src="{{ logo_url }}" alt="GearCargo" class="header-logo">
    <h1>📈 Monthly Report - {{ month_name }}</h1>
    <p class="header-subtitle">Comprehensive Vehicle Analysis</p>
</div>
<div class="content">
    <p>Hi {{ user_name }},</p>
    <p>Here's your comprehensive vehicle report for {{ month_name }} {{ year }}.</p>
    
    <div class="summary-box">
        <h3 style="margin-top: 0; color: #f1f5f9;">💰 Expense Summary</h3>
        <div class="stat-row">
            <span class="stat-label">Fuel</span>
            <span class="stat-value currency">{{ summary.currency }}{{ summary.fuel_total }}</span>
        </div>
        <div class="stat-row">
            <span class="stat-label">Services</span>
            <span class="stat-value currency">{{ summary.currency }}{{ summary.services_total }}</span>
        </div>
        <div class="stat-row">
            <span class="stat-label">Repairs</span>
            <span class="stat-value currency">{{ summary.currency }}{{ summary.repairs_total }}</span>
        </div>
        <div class="stat-row">
            <span class="stat-label">Parking</span>
            <span class="stat-value currency">{{ summary.currency }}{{ summary.parking_total }}</span>
        </div>
        <div class="stat-row">
            <span class="stat-label">Taxes & Insurance</span>
            <span class="stat-value currency">{{ summary.currency }}{{ summary.taxes_insurance_total }}</span>
        </div>
        <div class="stat-row" style="border-top: 2px solid #3b82f6; padding-top: 15px; margin-top: 10px;">
            <span class="stat-label" style="font-weight: 600; color: #f1f5f9;">Total Expenses</span>
            <span class="stat-value currency" style="color: #3b82f6; font-size: 18px;">{{ summary.currency }}{{ summary.grand_total }}</span>
        </div>
    </div>
    
    {% if vehicles %}
    <div class="divider"></div>
    <h3 style="color: #f1f5f9;">🚗 Per Vehicle Breakdown</h3>
    <table>
        <thead>
            <tr>
                <th>Vehicle</th>
                <th>Fuel</th>
                <th>Service</th>
                <th>Total</th>
            </tr>
        </thead>
        <tbody>
        {% for v in vehicles %}
            <tr>
                <td>{{ v.name }}</td>
                <td class="currency">{{ summary.currency }}{{ v.fuel }}</td>
                <td class="currency">{{ summary.currency }}{{ v.service }}</td>
                <td class="currency" style="font-weight: 500;">{{ summary.currency }}{{ v.total }}</td>
            </tr>
        {% endfor %}
        </tbody>
    </table>
    {% endif %}
    
    {% if insights %}
    <div class="divider"></div>
    <h3 style="color: #f1f5f9;">💡 Insights</h3>
    {% for insight in insights %}
    <p style="margin: 10px 0;">• {{ insight }}</p>
    {% endfor %}
    {% endif %}
    
    <a href="{{ app_url }}" class="btn">View Detailed Analytics</a>
</div>
"""


# ============================================================
# EMAIL SERVICE CLASS
# ============================================================

class EmailService:
    """Service for sending email notifications."""
    
    @staticmethod
    def is_enabled() -> bool:
        """Check if email is enabled."""
        return current_app.config.get('MAIL_ENABLED', False)
    
    @staticmethod
    def send_email(
        to: str,
        subject: str,
        content_html: str,
        reply_to: str = None
    ) -> bool:
        """Send an email with the base template."""
        if not EmailService.is_enabled():
            logger.warning("Email not enabled, skipping send")
            return False
        
        try:
            app_url = current_app.config.get('APP_URL', 'https://car.ascunse.uk')
            logo_url = f"{app_url}/icons/logo.png"
            
            # Wrap content in base template
            full_html = render_template_string(
                BASE_TEMPLATE,
                content=content_html,
                year=datetime.now().year,
                app_url=app_url,
                logo_url=logo_url
            )
            
            msg = Message(
                subject=f"GearCargo: {subject}",
                recipients=[to],
                html=full_html,
                reply_to=reply_to
            )
            
            mail.send(msg)
            logger.info(f"Email sent to {to}: {subject}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email to {to}: {e}")
            return False
    
    @staticmethod
    def send_alert_notification(
        user,
        alerts: List[Dict[str, Any]],
        alert_type: str = "reminder"
    ) -> bool:
        """Send alert/reminder notification email."""
        if not user.notification_email and not user.email:
            return False
        
        to_email = user.notification_email or user.email
        app_url = current_app.config.get('APP_URL', 'https://car.ascunse.uk')
        logo_url = f"{app_url}/icons/logo.png"
        
        # Determine title and intro based on alert type
        titles = {
            "reminder": "Upcoming Reminders",
            "insurance": "Insurance Alert",
            "tax": "Road Tax Alert",
            "service": "Service Due",
            "maintenance": "Maintenance Alert",
            "smart": "Smart Recommendations"
        }
        
        intros = {
            "reminder": "You have important reminders that need your attention:",
            "insurance": "Your vehicle insurance needs attention:",
            "tax": "Your road tax is due soon:",
            "service": "Your vehicle service is due:",
            "maintenance": "Maintenance recommended for your vehicle:",
            "smart": "Based on your vehicle data, we recommend:"
        }
        
        content_html = render_template_string(
            ALERT_REMINDER_TEMPLATE,
            title=titles.get(alert_type, "Alert"),
            user_name=user.display_name or user.username,
            intro_text=intros.get(alert_type, "You have alerts that need attention:"),
            alerts=alerts,
            app_url=app_url,
            logo_url=logo_url
        )
        
        return EmailService.send_email(
            to=to_email,
            subject=titles.get(alert_type, "Alert"),
            content_html=content_html
        )
    
    @staticmethod
    def send_weekly_report(user, summary: Dict, upcoming_alerts: List[Dict]) -> bool:
        """Send weekly summary report."""
        if not user.notification_email and not user.email:
            return False
        
        to_email = user.notification_email or user.email
        app_url = current_app.config.get('APP_URL', 'https://car.ascunse.uk')
        logo_url = f"{app_url}/icons/logo.png"
        
        # Calculate period
        today = date.today()
        week_ago = today - timedelta(days=7)
        period = f"{week_ago.strftime('%b %d')} - {today.strftime('%b %d, %Y')}"
        
        content_html = render_template_string(
            WEEKLY_REPORT_TEMPLATE,
            user_name=user.display_name or user.username,
            period=period,
            summary=summary,
            upcoming_alerts=upcoming_alerts,
            app_url=app_url,
            logo_url=logo_url
        )
        
        return EmailService.send_email(
            to=to_email,
            subject=f"Weekly Report ({period})",
            content_html=content_html
        )
    
    @staticmethod
    def send_monthly_report(
        user,
        month: int,
        year: int,
        summary: Dict,
        vehicles: List[Dict],
        insights: List[str]
    ) -> bool:
        """Send monthly summary report."""
        if not user.notification_email and not user.email:
            return False
        
        to_email = user.notification_email or user.email
        app_url = current_app.config.get('APP_URL', 'https://car.ascunse.uk')
        logo_url = f"{app_url}/icons/logo.png"
        
        month_names = [
            "", "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        month_name = month_names[month]
        
        content_html = render_template_string(
            MONTHLY_REPORT_TEMPLATE,
            user_name=user.display_name or user.username,
            month_name=month_name,
            year=year,
            summary=summary,
            vehicles=vehicles,
            insights=insights,
            app_url=app_url,
            logo_url=logo_url
        )
        
        return EmailService.send_email(
            to=to_email,
            subject=f"Monthly Report - {month_name} {year}",
            content_html=content_html
        )
    
    @staticmethod
    def send_test_email(user) -> bool:
        """Send a test email to verify settings."""
        if not user.notification_email and not user.email:
            return False
        
        to_email = user.notification_email or user.email
        app_url = current_app.config.get('APP_URL', 'https://car.ascunse.uk')
        logo_url = f"{app_url}/icons/logo.png"
        
        content_html = """
        <div class="header">
            <img src="{{ logo_url }}" alt="GearCargo" class="header-logo">
            <h1>✅ Test Email</h1>
            <p class="header-subtitle">Email Configuration Verified</p>
        </div>
        <div class="content">
            <p>Hi {{ user_name }},</p>
            <p>This is a test email to confirm your email notifications are working correctly.</p>
            <div class="alert-card info">
                <div class="alert-title">Email Configuration: OK</div>
                <div class="alert-subtitle">You will receive alerts for:</div>
                <div class="alert-detail">
                    • Insurance expiry reminders<br>
                    • Road tax due dates<br>
                    • Service and maintenance alerts<br>
                    • Smart recommendations<br>
                    • Weekly/Monthly reports (if enabled)
                </div>
            </div>
            <a href="{{ app_url }}/settings" class="btn">Manage Notification Settings</a>
        </div>
        """
        
        content = render_template_string(
            content_html,
            user_name=user.display_name or user.username,
            app_url=app_url,
            logo_url=logo_url
        )
        
        return EmailService.send_email(
            to=to_email,
            subject="Test Notification",
            content_html=content
        )


# ============================================================
# ALERT GATHERING FUNCTIONS
# ============================================================

def get_insurance_alerts(user_id: int, days_ahead: int = 30) -> List[Dict]:
    """Get insurance policies expiring within days_ahead."""
    from app.models import InsurancePolicy, Vehicle
    
    cutoff = date.today() + timedelta(days=days_ahead)
    alerts = []
    
    policies = InsurancePolicy.query.join(Vehicle).filter(
        Vehicle.user_id == user_id,
        Vehicle.is_active == True,
        InsurancePolicy.end_date.isnot(None),
        InsurancePolicy.end_date <= cutoff,
        InsurancePolicy.end_date >= date.today()
    ).all()
    
    for policy in policies:
        days_left = (policy.end_date - date.today()).days
        severity = "urgent" if days_left <= 7 else "warning" if days_left <= 14 else "info"
        
        alerts.append({
            'title': f"Insurance Expiring: {policy.provider}",
            'subtitle': f"Expires on {policy.end_date.strftime('%B %d, %Y')}",
            'details': f"{days_left} days remaining • Policy: {policy.policy_number or 'N/A'}",
            'vehicle': policy.vehicle.name if policy.vehicle else None,
            'severity': severity,
            'due_date': policy.end_date.strftime('%b %d, %Y')
        })
    
    return alerts


def get_tax_alerts(user_id: int, days_ahead: int = 30) -> List[Dict]:
    """Get road taxes expiring within days_ahead."""
    from app.models import TaxEntry, Vehicle
    
    cutoff = date.today() + timedelta(days=days_ahead)
    alerts = []
    
    # Get most recent tax for each vehicle
    taxes = db.session.query(TaxEntry).join(Vehicle).filter(
        Vehicle.user_id == user_id,
        Vehicle.is_active == True,
        TaxEntry.valid_until.isnot(None),
        TaxEntry.valid_until <= cutoff,
        TaxEntry.valid_until >= date.today()
    ).all()
    
    for tax in taxes:
        days_left = (tax.valid_until - date.today()).days
        severity = "urgent" if days_left <= 7 else "warning" if days_left <= 14 else "info"
        
        alerts.append({
            'title': "Road Tax Due",
            'subtitle': f"Expires on {tax.valid_until.strftime('%B %d, %Y')}",
            'details': f"{days_left} days remaining",
            'vehicle': tax.vehicle.name if tax.vehicle else None,
            'severity': severity,
            'due_date': tax.valid_until.strftime('%b %d, %Y')
        })
    
    return alerts


def get_service_alerts(user_id: int, days_ahead: int = 30) -> List[Dict]:
    """Get services due within days_ahead based on reminders and predictions."""
    from app.models import Reminder, Vehicle
    
    cutoff = date.today() + timedelta(days=days_ahead)
    alerts = []
    
    # Get service-related reminders
    reminders = Reminder.query.join(Vehicle).filter(
        Reminder.user_id == user_id,
        Vehicle.is_active == True,
        Reminder.completed == False,
        Reminder.dismissed == False,
        Reminder.due_date.isnot(None),
        Reminder.due_date <= cutoff,
        Reminder.category.in_(['service', 'maintenance', 'oil_change', 'inspection'])
    ).all()
    
    for reminder in reminders:
        days_left = (reminder.due_date - date.today()).days
        is_overdue = days_left < 0
        severity = "urgent" if is_overdue or days_left <= 7 else "warning" if days_left <= 14 else "info"
        
        alerts.append({
            'title': reminder.title,
            'subtitle': f"{'OVERDUE - was due' if is_overdue else 'Due on'} {reminder.due_date.strftime('%B %d, %Y')}",
            'details': reminder.description,
            'vehicle': reminder.vehicle.name if reminder.vehicle else None,
            'severity': severity,
            'due_date': reminder.due_date.strftime('%b %d, %Y')
        })
    
    return alerts


def get_all_alerts_for_user(user_id: int, days_ahead: int = 30) -> Dict[str, List[Dict]]:
    """Get all alerts for a user grouped by type."""
    return {
        'insurance': get_insurance_alerts(user_id, days_ahead),
        'tax': get_tax_alerts(user_id, days_ahead),
        'service': get_service_alerts(user_id, days_ahead)
    }


def get_user_weekly_summary(user_id: int) -> Dict:
    """Generate weekly summary data for a user."""
    from app.models import User, Vehicle, FuelEntry, ServiceEntry, RepairEntry
    
    user = User.query.get(user_id)
    if not user:
        return {}
    
    week_ago = date.today() - timedelta(days=7)
    
    # Get vehicles
    vehicles = Vehicle.query.filter_by(user_id=user_id, is_active=True).all()
    vehicle_ids = [v.id for v in vehicles]
    
    # Fuel stats
    fuel_entries = FuelEntry.query.filter(
        FuelEntry.vehicle_id.in_(vehicle_ids),
        FuelEntry.date >= week_ago
    ).all()
    
    fuel_spent = sum(e.total_cost or 0 for e in fuel_entries)
    total_liters = sum(e.liters or 0 for e in fuel_entries)
    
    # Services
    services = ServiceEntry.query.filter(
        ServiceEntry.vehicle_id.in_(vehicle_ids),
        ServiceEntry.date >= week_ago
    ).count()
    
    # Estimate distance (from odometer changes)
    distance = 0
    for v in vehicles:
        latest_fuel = FuelEntry.query.filter_by(vehicle_id=v.id).order_by(FuelEntry.date.desc()).first()
        week_ago_fuel = FuelEntry.query.filter(
            FuelEntry.vehicle_id == v.id,
            FuelEntry.date <= week_ago
        ).order_by(FuelEntry.date.desc()).first()
        
        if latest_fuel and week_ago_fuel and latest_fuel.odometer and week_ago_fuel.odometer:
            distance += (latest_fuel.odometer - week_ago_fuel.odometer)
    
    return {
        'total_vehicles': len(vehicles),
        'fuel_entries': len(fuel_entries),
        'fuel_spent': f"{fuel_spent:.2f}",
        'services': services,
        'distance': f"{distance:,.0f}",
        'distance_unit': user.distance_unit or 'km',
        'currency': user.currency or '£'
    }


def get_user_monthly_summary(user_id: int, month: int, year: int) -> Dict:
    """Generate monthly summary data for a user."""
    from app.models import User, Vehicle, FuelEntry, ServiceEntry, RepairEntry, TaxEntry, ParkingEntry, InsurancePolicy
    
    user = User.query.get(user_id)
    if not user:
        return {}
    
    # Calculate date range
    from calendar import monthrange
    first_day = date(year, month, 1)
    last_day = date(year, month, monthrange(year, month)[1])
    
    vehicles = Vehicle.query.filter_by(user_id=user_id, is_active=True).all()
    vehicle_ids = [v.id for v in vehicles]
    
    # Gather expenses by category
    fuel_total = sum(
        e.total_cost or 0 for e in FuelEntry.query.filter(
            FuelEntry.vehicle_id.in_(vehicle_ids),
            FuelEntry.date >= first_day,
            FuelEntry.date <= last_day
        ).all()
    )
    
    services_total = sum(
        e.cost or 0 for e in ServiceEntry.query.filter(
            ServiceEntry.vehicle_id.in_(vehicle_ids),
            ServiceEntry.date >= first_day,
            ServiceEntry.date <= last_day
        ).all()
    )
    
    repairs_total = sum(
        e.cost or 0 for e in RepairEntry.query.filter(
            RepairEntry.vehicle_id.in_(vehicle_ids),
            RepairEntry.date >= first_day,
            RepairEntry.date <= last_day
        ).all()
    )
    
    parking_total = sum(
        e.cost or 0 for e in ParkingEntry.query.filter(
            ParkingEntry.vehicle_id.in_(vehicle_ids),
            ParkingEntry.date >= first_day,
            ParkingEntry.date <= last_day
        ).all()
    )
    
    taxes_total = sum(
        e.amount or 0 for e in TaxEntry.query.filter(
            TaxEntry.vehicle_id.in_(vehicle_ids),
            TaxEntry.date >= first_day,
            TaxEntry.date <= last_day
        ).all()
    )
    
    insurance_total = sum(
        p.premium or 0 for p in InsurancePolicy.query.filter(
            InsurancePolicy.vehicle_id.in_(vehicle_ids),
            InsurancePolicy.start_date >= first_day,
            InsurancePolicy.start_date <= last_day
        ).all()
    )
    
    grand_total = fuel_total + services_total + repairs_total + parking_total + taxes_total + insurance_total
    
    # Per-vehicle breakdown
    vehicle_breakdown = []
    for v in vehicles:
        v_fuel = sum(e.total_cost or 0 for e in FuelEntry.query.filter(
            FuelEntry.vehicle_id == v.id,
            FuelEntry.date >= first_day,
            FuelEntry.date <= last_day
        ).all())
        
        v_service = sum(e.cost or 0 for e in ServiceEntry.query.filter(
            ServiceEntry.vehicle_id == v.id,
            ServiceEntry.date >= first_day,
            ServiceEntry.date <= last_day
        ).all())
        
        v_total = v_fuel + v_service
        
        if v_total > 0:
            vehicle_breakdown.append({
                'name': v.name,
                'fuel': f"{v_fuel:.2f}",
                'service': f"{v_service:.2f}",
                'total': f"{v_total:.2f}"
            })
    
    currency_symbols = {'GBP': '£', 'EUR': '€', 'USD': '$', 'RON': 'RON '}
    currency = currency_symbols.get(user.currency, '£')
    
    return {
        'fuel_total': f"{fuel_total:.2f}",
        'services_total': f"{services_total:.2f}",
        'repairs_total': f"{repairs_total:.2f}",
        'parking_total': f"{parking_total:.2f}",
        'taxes_insurance_total': f"{taxes_total + insurance_total:.2f}",
        'grand_total': f"{grand_total:.2f}",
        'currency': currency
    }, vehicle_breakdown


# ============================================================
# EMAIL VERIFICATION TEMPLATE
# ============================================================

EMAIL_VERIFICATION_TEMPLATE = """
<div class="header">
    <img src="{{ logo_url }}" alt="GearCargo" class="header-logo">
    <h1>✉️ Verify Your Email</h1>
    <p class="header-subtitle">Welcome to GearCargo</p>
</div>
<div class="content">
    <p>Hi {{ user_name }},</p>
    <p>Thank you for creating a GearCargo account! Please verify your email address to get started.</p>
    
    <div class="alert-card info">
        <div class="alert-title">Verify Your Email Address</div>
        <div class="alert-subtitle">Click the button below to verify your email.</div>
        <div class="alert-detail">This link will expire in 48 hours.</div>
    </div>
    
    <div style="text-align: center;">
        <a href="{{ verify_link }}" class="btn" style="color: white;">Verify Email Address</a>
    </div>
    
    <div class="divider"></div>
    
    <div class="summary-box">
        <p style="font-size: 13px; color: #94a3b8; margin: 0;">
            If you didn't create a GearCargo account, you can safely ignore this email.
        </p>
    </div>
    
    <p style="font-size: 12px; color: #64748b; margin-top: 20px;">
        <strong>Why verify?</strong> Email verification helps us keep your account secure 
        and ensures you receive important notifications about your vehicles.
    </p>
    
    <p style="font-size: 11px; color: #64748b; margin-top: 15px;">
        If the button doesn't work, copy and paste this link into your browser:<br>
        <a href="{{ verify_link }}" style="color: #3b82f6; word-break: break-all;">{{ verify_link }}</a>
    </p>
</div>
"""


class EmailVerificationService:
    """Service for sending email verification emails."""
    
    @staticmethod
    def send_verification_email(user, token: str) -> bool:
        """Send email verification email to user."""
        if not EmailService.is_enabled():
            logger.warning("Email not enabled, skipping verification email")
            return False
        
        try:
            app_url = current_app.config.get('APP_URL', 'https://car.ascunse.uk')
            logo_url = f"{app_url}/icons/logo.png"
            verify_link = f"{app_url}/verify-email?token={token}"
            
            content_html = render_template_string(
                EMAIL_VERIFICATION_TEMPLATE,
                user_name=user.display_name or user.username,
                verify_link=verify_link,
                logo_url=logo_url
            )
            
            return EmailService.send_email(
                to=user.email,
                subject="Verify Your Email Address - GearCargo",
                content_html=content_html
            )
            
        except Exception as e:
            logger.error(f"Failed to send verification email to {user.email}: {e}")
            return False


# Export the verification service
email_verification_service = EmailVerificationService()


# ============================================================
# PASSWORD RESET EMAIL TEMPLATE
# ============================================================

PASSWORD_RESET_TEMPLATE = """
<div class="header">
    <img src="{{ logo_url }}" alt="GearCargo" class="header-logo">
    <h1>🔐 Password Reset Request</h1>
    <p class="header-subtitle">Secure Account Recovery</p>
</div>
<div class="content">
    <p>Hi {{ user_name }},</p>
    <p>We received a request to reset your password for your GearCargo account associated with this email address.</p>
    
    <div class="alert-card info">
        <div class="alert-title">Reset Your Password</div>
        <div class="alert-subtitle">Click the button below to create a new password.</div>
        <div class="alert-detail">This link will expire in 24 hours for security reasons.</div>
    </div>
    
    <div style="text-align: center;">
        <a href="{{ reset_link }}" class="btn" style="color: white;">Reset My Password</a>
    </div>
    
    <div class="divider"></div>
    
    <div class="summary-box">
        <p style="font-size: 13px; color: #94a3b8; margin: 0;">
            If you didn't request this password reset, you can safely ignore this email. 
            Your password will remain unchanged.
        </p>
    </div>
    
    <p style="font-size: 12px; color: #64748b; margin-top: 20px;">
        <strong>Security tip:</strong> Never share your password or reset links with anyone. 
        GearCargo staff will never ask for your password.
    </p>
    
    <p style="font-size: 11px; color: #64748b; margin-top: 15px;">
        If the button doesn't work, copy and paste this link into your browser:<br>
        <a href="{{ reset_link }}" style="color: #3b82f6; word-break: break-all;">{{ reset_link }}</a>
    </p>
</div>
"""


class PasswordResetEmailService:
    """Service for sending password reset emails."""
    
    @staticmethod
    def send_password_reset_email(user, token: str) -> bool:
        """Send password reset email to user."""
        if not EmailService.is_enabled():
            logger.warning("Email not enabled, skipping password reset email")
            return False
        
        try:
            app_url = current_app.config.get('APP_URL', 'https://car.ascunse.uk')
            logo_url = f"{app_url}/icons/logo.png"
            reset_link = f"{app_url}/reset-password?token={token}"
            
            content_html = render_template_string(
                PASSWORD_RESET_TEMPLATE,
                user_name=user.display_name or user.username,
                reset_link=reset_link,
                logo_url=logo_url
            )
            
            return EmailService.send_email(
                to=user.email,
                subject="Password Reset Request",
                content_html=content_html
            )
            
        except Exception as e:
            logger.error(f"Failed to send password reset email to {user.email}: {e}")
            return False


# ============================================================
# NEW DEVICE LOGIN ALERT
# ============================================================

NEW_LOGIN_ALERT_TEMPLATE = """
<div class="header" style="background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);">
    <img src="{{ logo_url }}" alt="GearCargo" class="header-logo">
    <h1>🔐 New Login Detected</h1>
    <p class="header-subtitle">Security Alert for {{ user_name }}</p>
</div>
<div class="content">
    <p style="font-size: 16px; color: #f1f5f9;">Hi <strong>{{ user_name }}</strong>,</p>
    <p style="color: #94a3b8;">We detected a login to your GearCargo account from a new device or browser. If this was you, no action is needed.</p>
    
    <div style="background: linear-gradient(135deg, #1e3a5f 0%, #1e293b 100%); border-radius: 12px; padding: 24px; margin: 24px 0; border: 1px solid #334155;">
        <div style="display: flex; align-items: center; margin-bottom: 16px;">
            <div style="width: 48px; height: 48px; background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); border-radius: 12px; display: flex; align-items: center; justify-content: center; margin-right: 16px;">
                <span style="font-size: 24px;">{{ device_icon }}</span>
            </div>
            <div>
                <div style="color: #f1f5f9; font-weight: 600; font-size: 16px;">{{ device_info }}</div>
                <div style="color: #64748b; font-size: 13px;">{{ browser_version }}</div>
            </div>
        </div>
        
        <div style="background: rgba(0,0,0,0.2); border-radius: 8px; padding: 16px;">
            <table style="width: 100%; border-collapse: collapse;">
                <tr style="border-bottom: 1px solid #334155;">
                    <td style="padding: 12px 0; color: #64748b; font-size: 13px; width: 40%;">📍 Location</td>
                    <td style="padding: 12px 0; color: #f1f5f9; font-size: 14px; font-weight: 500;">{{ location }}</td>
                </tr>
                <tr style="border-bottom: 1px solid #334155;">
                    <td style="padding: 12px 0; color: #64748b; font-size: 13px;">🌐 IP Address</td>
                    <td style="padding: 12px 0; color: #f1f5f9; font-size: 14px; font-family: monospace;">{{ ip_address }}</td>
                </tr>
                <tr style="border-bottom: 1px solid #334155;">
                    <td style="padding: 12px 0; color: #64748b; font-size: 13px;">🕐 Time</td>
                    <td style="padding: 12px 0; color: #f1f5f9; font-size: 14px;">{{ login_time }}</td>
                </tr>
                {% if isp %}
                <tr>
                    <td style="padding: 12px 0; color: #64748b; font-size: 13px;">📡 Network</td>
                    <td style="padding: 12px 0; color: #f1f5f9; font-size: 14px;">{{ isp }}</td>
                </tr>
                {% endif %}
            </table>
        </div>
    </div>
    
    <div style="background-color: #0f172a; border-radius: 8px; padding: 16px; margin: 20px 0; border-left: 4px solid #22c55e;">
        <p style="color: #22c55e; font-weight: 600; margin: 0 0 8px 0;">✅ Was this you?</p>
        <p style="color: #94a3b8; margin: 0; font-size: 14px;">If you just signed in from a new device or browser, you can safely ignore this email. We're just keeping you informed!</p>
    </div>
    
    <div style="background-color: #0f172a; border-radius: 8px; padding: 16px; margin: 20px 0; border-left: 4px solid #ef4444;">
        <p style="color: #ef4444; font-weight: 600; margin: 0 0 8px 0;">⚠️ Wasn't you?</p>
        <p style="color: #94a3b8; margin: 0 0 12px 0; font-size: 14px;">If you didn't make this login, your account may be compromised. Take these steps immediately:</p>
        <ol style="color: #94a3b8; margin: 0; padding-left: 20px; font-size: 14px;">
            <li style="margin-bottom: 6px;">Change your password right away</li>
            <li style="margin-bottom: 6px;">Enable Two-Factor Authentication (2FA)</li>
            <li>Review your recent account activity</li>
        </ol>
    </div>
    
    <div style="text-align: center; margin-top: 28px;">
        <a href="{{ change_password_url }}" style="display: inline-block; background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%); color: white; padding: 14px 28px; text-decoration: none; border-radius: 8px; font-weight: 600; margin-right: 12px; font-size: 14px;">🔒 Change Password</a>
        <a href="{{ settings_url }}" style="display: inline-block; background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%); color: white; padding: 14px 28px; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 14px;">⚙️ Security Settings</a>
    </div>
</div>
"""


def send_new_login_alert(user, device_info: dict) -> bool:
    """Send email alert when login from new device is detected."""
    if not EmailService.is_enabled():
        logger.warning("Email not enabled, skipping new login alert")
        return False
    
    try:
        app_url = current_app.config.get('APP_URL', 'https://car.ascunse.uk')
        logo_url = f"{app_url}/icons/logo.png"
        
        # Parse user agent for friendlier display
        user_agent = device_info.get('user_agent', 'Unknown device')
        browser = 'Unknown browser'
        browser_version = ''
        
        if 'Chrome' in user_agent and 'Edg' not in user_agent:
            browser = 'Chrome'
            # Try to extract version
            match = re.search(r'Chrome/(\d+)', user_agent)
            if match:
                browser_version = f"Version {match.group(1)}"
        elif 'Firefox' in user_agent:
            browser = 'Firefox'
            match = re.search(r'Firefox/(\d+)', user_agent)
            if match:
                browser_version = f"Version {match.group(1)}"
        elif 'Safari' in user_agent and 'Chrome' not in user_agent:
            browser = 'Safari'
            match = re.search(r'Version/(\d+)', user_agent)
            if match:
                browser_version = f"Version {match.group(1)}"
        elif 'Edg' in user_agent:
            browser = 'Microsoft Edge'
            match = re.search(r'Edg/(\d+)', user_agent)
            if match:
                browser_version = f"Version {match.group(1)}"
        
        # Determine OS
        os_name = 'Unknown OS'
        device_icon = '💻'  # Default desktop icon
        
        if 'Windows' in user_agent:
            os_name = 'Windows'
            device_icon = '🪟'
        elif 'Mac' in user_agent:
            os_name = 'macOS'
            device_icon = '🍎'
        elif 'Linux' in user_agent:
            os_name = 'Linux'
            device_icon = '🐧'
        elif 'Android' in user_agent:
            os_name = 'Android'
            device_icon = '📱'
        elif 'iPhone' in user_agent:
            os_name = 'iPhone'
            device_icon = '📱'
        elif 'iPad' in user_agent:
            os_name = 'iPad'
            device_icon = '📱'
        
        device_display = f"{browser} on {os_name}"
        
        # Extract location info
        location_info = device_info.get('location', {}) or {}
        city = location_info.get('city', '')
        country = location_info.get('country', '')
        isp = location_info.get('isp', '')
        
        # Build location string
        if city and country:
            location = f"{city}, {country}"
        elif country:
            location = country
        elif city:
            location = city
        else:
            location = "Unknown location"
        
        # Get IP address
        ip_address = device_info.get('ip', 'Unknown')
        
        # Check if it's a private/local IP
        if ip_address and ip_address.startswith(('127.', '10.', '192.168.', '172.', '::1')):
            location = "Local Network"
            isp = "Private Network"
        
        content_html = render_template_string(
            NEW_LOGIN_ALERT_TEMPLATE,
            user_name=user.display_name or user.username,
            login_time=datetime.now().strftime('%B %d, %Y at %I:%M %p UTC'),
            ip_address=ip_address,
            device_info=device_display,
            device_icon=device_icon,
            browser_version=browser_version,
            location=location,
            isp=isp if isp and isp != 'Private Network' else None,
            logo_url=logo_url,
            change_password_url=f"{app_url}/settings/security",
            settings_url=f"{app_url}/settings/security"
        )
        
        return EmailService.send_email(
            to=user.email,
            subject="⚠️ New Login to Your GearCargo Account",
            content_html=content_html
        )
        
    except Exception as e:
        logger.error(f"Failed to send new login alert to {user.email}: {e}")
        return False


# ============================================================
# SUSPICIOUS LOCATION LOGIN ALERT
# ============================================================

SUSPICIOUS_LOCATION_TEMPLATE = """
<div class="header" style="background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);">
    <img src="{{ logo_url }}" alt="GearCargo" class="header-logo">
    <h1>🚨 Suspicious Login Location</h1>
    <p class="header-subtitle">Security Alert - Unusual Activity Detected</p>
</div>
<div class="content">
    <p>Hi {{ user_name }},</p>
    <p style="color: #ef4444; font-weight: 600;">We detected a login to your GearCargo account from a new geographic location.</p>
    
    <div class="alert-card urgent">
        <div class="alert-title">New Location Detected</div>
        <div class="stat-row">
            <span class="stat-label">Country</span>
            <span class="stat-value">{{ country }} ({{ country_code }})</span>
        </div>
        <div class="stat-row">
            <span class="stat-label">City</span>
            <span class="stat-value">{{ city }}</span>
        </div>
        <div class="stat-row">
            <span class="stat-label">IP Address</span>
            <span class="stat-value">{{ ip_address }}</span>
        </div>
        <div class="stat-row">
            <span class="stat-label">ISP</span>
            <span class="stat-value">{{ isp }}</span>
        </div>
        <div class="stat-row">
            <span class="stat-label">Time</span>
            <span class="stat-value">{{ login_time }}</span>
        </div>
    </div>
    
    <div class="alert-card info">
        <div class="alert-title">Your Known Locations</div>
        <p style="color: #94a3b8; font-size: 14px;">
            Previous logins have been from: <strong>{{ known_locations }}</strong>
        </p>
    </div>
    
    <p style="color: #f1f5f9;">If this was you (e.g., traveling or using VPN), you can safely ignore this email.</p>
    <p style="color: #ef4444; font-weight: 600;">If you did NOT make this login:</p>
    <ol style="color: #94a3b8;">
        <li><strong>Change your password immediately</strong></li>
        <li>Enable 2-Factor Authentication</li>
        <li>Check your account for unauthorized changes</li>
        <li>Review and revoke any active sessions</li>
    </ol>
    
    <a href="{{ change_password_url }}" class="btn" style="background-color: #ef4444;">Change Password Now</a>
    <a href="{{ sessions_url }}" class="btn" style="margin-left: 10px; background-color: #3b82f6;">Review Sessions</a>
</div>
"""


def send_suspicious_location_alert(user, location_info: dict, known_locations: list) -> bool:
    """Send email alert when login from suspicious (new) location is detected."""
    if not EmailService.is_enabled():
        logger.warning("Email not enabled, skipping suspicious location alert")
        return False
    
    try:
        app_url = current_app.config.get('APP_URL', 'https://car.ascunse.uk')
        logo_url = f"{app_url}/icons/logo.png"
        
        # Format known locations for display
        known_locations_display = ', '.join(known_locations) if known_locations else 'None recorded'
        
        content_html = render_template_string(
            SUSPICIOUS_LOCATION_TEMPLATE,
            user_name=user.display_name or user.username,
            country=location_info.get('country', 'Unknown'),
            country_code=location_info.get('country_code', 'XX'),
            city=location_info.get('city', 'Unknown'),
            ip_address=location_info.get('ip', 'Unknown'),
            isp=location_info.get('isp', 'Unknown'),
            login_time=datetime.now().strftime('%B %d, %Y at %I:%M %p UTC'),
            known_locations=known_locations_display,
            logo_url=logo_url,
            change_password_url=f"{app_url}/settings/security",
            sessions_url=f"{app_url}/settings/security"
        )
        
        return EmailService.send_email(
            to=user.email,
            subject="🚨 SECURITY ALERT: Login from New Location Detected",
            content_html=content_html
        )
        
    except Exception as e:
        logger.error(f"Failed to send suspicious location alert to {user.email}: {e}")
        return False


# Export the service
email_service = EmailService()
password_reset_email_service = PasswordResetEmailService()

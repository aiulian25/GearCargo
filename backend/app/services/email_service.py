"""
GearCargo - Email Notification Service
Handles all email notifications: alerts, reminders, reports
"""

from datetime import datetime, date, timedelta, timezone
from flask import current_app, render_template_string
from flask_mail import Message
from app import mail, db
from app.utils.timeutils import utc_today
from typing import List, Dict, Any, Tuple
import logging
import re

logger = logging.getLogger(__name__)


def build_unsubscribe_url(user):
    """One-click unsubscribe URL carrying the RAW token (R4-24).

    The column holds only the token's hash, so the URL is built from
    `generate_unsubscribe_token()` — never from the stored column.
    """
    if not user:
        return None
    raw_token = user.generate_unsubscribe_token()
    return f"{link_domain_for(user)}/api/auth/unsubscribe?token={raw_token}"


def link_domain_for(user=None) -> str:
    """Return the base URL for links emailed to *user*.

    Admins are refused login on USER_DOMAIN by `_enforce_login_domain_policy`,
    so a USER_DOMAIN verify/reset link is a dead end for them — they must land
    on ADMIN_DOMAIN. Everyone else keeps USER_DOMAIN, falling back to APP_URL
    when no split is configured.
    """
    def _configured(key):
        value = (current_app.config.get(key, '') or '').strip()
        # config.py keeps commented-out values ('#...'); treat them as unset.
        return '' if value.startswith('#') else value

    domain = _configured('ADMIN_DOMAIN') if getattr(user, 'is_admin', False) else ''
    domain = domain or _configured('USER_DOMAIN') or current_app.config.get('APP_URL', 'http://localhost:5000')
    return domain if domain.startswith('http') else f'https://{domain}'


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
                {% if unsubscribe_url %}
                <a href="{{ unsubscribe_url }}" style="color: #ef4444;">One-click Unsubscribe</a> |
                {% endif %}
                <a href="{{ app_url }}/settings">Manage Notifications</a>
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
        reply_to: str = None,
        unsubscribe_url: str = None
    ) -> bool:
        """Send an email with the base template."""
        if not EmailService.is_enabled():
            logger.warning("Email not enabled, skipping send")
            return False
        
        try:
            app_url = current_app.config.get('APP_URL', 'http://localhost:5000')
            logo_url = f"{app_url}/icons/logo.png"
            
            # Wrap content in base template
            full_html = render_template_string(
                BASE_TEMPLATE,
                content=content_html,
                year=datetime.now(timezone.utc).year,
                app_url=app_url,
                logo_url=logo_url,
                unsubscribe_url=unsubscribe_url or ''
            )
            
            msg = Message(
                subject=f"GearCargo: {subject}",
                recipients=[to],
                html=full_html,
                reply_to=reply_to
            )
            
            # RFC 8058 one-click unsubscribe header
            if unsubscribe_url:
                msg.extra_headers = {
                    'List-Unsubscribe': f'<{unsubscribe_url}>',
                    'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click'
                }
            
            mail.send(msg)
            logger.info(f"Email sent to {to}: {subject}")
            
            # Log email delivery to NotificationLog
            EmailService._log_email_delivery(to, subject, status='sent')
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email to {to}: {e}")
            EmailService._log_email_delivery(to, subject, status='failed', error=str(e))
            return False
    
    @staticmethod
    def _log_email_delivery(to_email, subject, status='sent', error=None):
        """Log email delivery to NotificationLog for tracking."""
        try:
            from app.models import User, NotificationLog
            user = User.query.filter_by(email=to_email).first()
            if not user:
                # Check by notification_email_hash
                from app.utils.encryption import hash_email
                email_h = hash_email(to_email)
                user = User.query.filter_by(notification_email_hash=email_h).first()
            
            if user:
                log_entry = NotificationLog(
                    user_id=user.id,
                    notification_type='email',
                    title=subject,
                    body=f'Email to {to_email}',
                    channel='email',
                    status=status,
                    error_message=error,
                    sent_at=datetime.now(timezone.utc) if status == 'sent' else None,
                )
                db.session.add(log_entry)
                
                # Bounce tracking: increment on failure, reset on success
                if status == 'failed' and user.notification_email_hash:
                    from app.utils.encryption import hash_email
                    if hash_email(to_email) == user.notification_email_hash:
                        user.notification_email_bounce_count = (user.notification_email_bounce_count or 0) + 1
                        if user.notification_email_bounce_count >= 5:
                            user.notification_email_verified = False
                            logger.warning(f"Auto-disabled notification email for user {user.id} after 5 bounces")
                elif status == 'sent' and user.notification_email_hash:
                    from app.utils.encryption import hash_email
                    if hash_email(to_email) == user.notification_email_hash:
                        user.notification_email_bounce_count = 0
                
                db.session.commit()
        except Exception as log_err:
            logger.error(f"Failed to log email delivery: {log_err}")
    
    @staticmethod
    def send_alert_notification(
        user,
        alerts: List[Dict[str, Any]],
        alert_type: str = "reminder"
    ) -> bool:
        """Send alert/reminder notification email."""
        to_email = user.get_effective_notification_email()
        if not to_email:
            return False
        
        user_domain = link_domain_for(user)
        logo_url = f"{user_domain}/icons/logo.png"
        unsubscribe_url = build_unsubscribe_url(user)
        
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
            app_url=user_domain,
            logo_url=logo_url
        )
        
        return EmailService.send_email(
            to=to_email,
            subject=titles.get(alert_type, "Alert"),
            content_html=content_html,
            unsubscribe_url=unsubscribe_url
        )
    
    @staticmethod
    def send_weekly_report(user, summary: Dict, upcoming_alerts: List[Dict]) -> bool:
        """Send weekly summary report."""
        to_email = user.get_effective_notification_email()
        if not to_email:
            return False
        
        user_domain = link_domain_for(user)
        logo_url = f"{user_domain}/icons/logo.png"
        unsubscribe_url = build_unsubscribe_url(user)
        
        # Calculate period (UTC, matching get_user_weekly_summary's window)
        today = utc_today()
        week_ago = today - timedelta(days=7)
        period = f"{week_ago.strftime('%d %b')} - {today.strftime('%d %b %Y')}"
        
        content_html = render_template_string(
            WEEKLY_REPORT_TEMPLATE,
            user_name=user.display_name or user.username,
            period=period,
            summary=summary,
            upcoming_alerts=upcoming_alerts,
            app_url=user_domain,
            logo_url=logo_url
        )
        
        return EmailService.send_email(
            to=to_email,
            subject=f"Weekly Report ({period})",
            content_html=content_html,
            unsubscribe_url=unsubscribe_url
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
        to_email = user.get_effective_notification_email()
        if not to_email:
            return False
        
        user_domain = link_domain_for(user)
        logo_url = f"{user_domain}/icons/logo.png"
        unsubscribe_url = build_unsubscribe_url(user)
        
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
            app_url=user_domain,
            logo_url=logo_url
        )
        
        return EmailService.send_email(
            to=to_email,
            subject=f"Monthly Report - {month_name} {year}",
            content_html=content_html,
            unsubscribe_url=unsubscribe_url
        )
    
    @staticmethod
    def send_test_email(user) -> bool:
        """Send a test email to verify settings."""
        to_email = user.get_effective_notification_email()
        if not to_email:
            return False
        
        user_domain = link_domain_for(user)
        logo_url = f"{user_domain}/icons/logo.png"
        
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
            app_url=user_domain,
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
    
    cutoff = utc_today() + timedelta(days=days_ahead)
    alerts = []
    
    policies = InsurancePolicy.query.join(Vehicle).filter(
        Vehicle.user_id == user_id,
        Vehicle.archived == False,
        InsurancePolicy.end_date.isnot(None),
        InsurancePolicy.end_date <= cutoff,
        InsurancePolicy.end_date >= utc_today()
    ).all()
    
    for policy in policies:
        days_left = (policy.end_date - utc_today()).days
        severity = "urgent" if days_left <= 7 else "warning" if days_left <= 14 else "info"
        
        alerts.append({
            'title': f"Insurance Expiring: {policy.provider}",
            'subtitle': f"Expires on {policy.end_date.strftime('%d %B %Y')}",
            'details': f"{days_left} days remaining • Policy: {policy.policy_number or 'N/A'}",
            'vehicle': policy.vehicle.name if policy.vehicle else None,
            'severity': severity,
            'due_date': policy.end_date.strftime('%d %b %Y')
        })
    
    return alerts


def get_tax_alerts(user_id: int, days_ahead: int = 30) -> List[Dict]:
    """Get road taxes expiring within days_ahead."""
    from app.models import TaxEntry, Vehicle
    
    today = utc_today()
    cutoff = today + timedelta(days=days_ahead)
    alerts = []

    # R4-23: a recurring tax carries the ORIGINAL date in due_date and the next
    # occurrence in next_due_date, so filtering on due_date alone hid exactly
    # the taxes this digest exists for — the repeating ones. Either column may
    # put the row in range; the loop then reports whichever date is actually
    # next, and drops rows whose real date falls outside the horizon.
    taxes = db.session.query(TaxEntry).join(Vehicle, Vehicle.id == TaxEntry.vehicle_id).filter(
        TaxEntry.user_id == user_id,
        Vehicle.archived == False,
        db.or_(
            TaxEntry.due_date.between(today, cutoff),
            TaxEntry.next_due_date.between(today, cutoff),
        ),
    ).all()

    for tax in taxes:
        alert_date = tax.next_due_date or tax.due_date
        if not alert_date or not (today <= alert_date <= cutoff):
            continue

        days_left = (alert_date - today).days
        severity = "urgent" if days_left <= 7 else "warning" if days_left <= 14 else "info"

        alerts.append({
            'title': "Road Tax Due",
            'subtitle': f"Due on {alert_date.strftime('%d %B %Y')}",
            'details': f"{days_left} days remaining",
            'vehicle': tax.vehicle.name if tax.vehicle else None,
            'severity': severity,
            'due_date': alert_date.strftime('%d %b %Y')
        })
    
    return alerts


def get_service_alerts(user_id: int, days_ahead: int = 30) -> List[Dict]:
    """Get service/maintenance reminders due within days_ahead."""
    from app.models import Reminder, Vehicle

    cutoff = utc_today() + timedelta(days=days_ahead)
    alerts = []

    SERVICE_TYPES = ['service', 'maintenance', 'oil_change', 'inspection', 'mot']

    reminders = Reminder.query.join(Vehicle).filter(
        Reminder.user_id == user_id,
        Vehicle.archived == False,
        Reminder.completed == False,
        Reminder.dismissed == False,
        Reminder.due_date.isnot(None),
        Reminder.due_date >= utc_today(),
        Reminder.due_date <= cutoff,
        Reminder.reminder_type.in_(SERVICE_TYPES)
    ).all()

    for reminder in reminders:
        days_left = (reminder.due_date - utc_today()).days
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


def get_reminder_alerts(user_id: int, days_ahead: int = 30) -> List[Dict]:
    """Get all due/upcoming reminders (any type) with notify_email=True."""
    from app.models import Reminder, Vehicle

    cutoff = utc_today() + timedelta(days=days_ahead)
    alerts = []

    reminders = Reminder.query.join(Vehicle).filter(
        Reminder.user_id == user_id,
        Vehicle.archived == False,
        Reminder.completed == False,
        Reminder.dismissed == False,
        Reminder.notify_email == True,
        # F52 — snoozed reminders stay out of the digest until snoozed_until passes.
        db.or_(Reminder.snoozed_until.is_(None),
               Reminder.snoozed_until <= datetime.now(timezone.utc)),
        Reminder.due_date.isnot(None),
        Reminder.due_date >= utc_today(),
        Reminder.due_date <= cutoff,
    ).all()

    for reminder in reminders:
        days_left = (reminder.due_date - utc_today()).days
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
        'service': get_service_alerts(user_id, days_ahead),
        'reminder': get_reminder_alerts(user_id, days_ahead),
    }


# ── Money formatting / currency normalization (F1/F28) ───────────────────────

# Symbols for the currencies the app offers. Anything else renders as its own
# code — labelling a CHF total with '£' is worse than showing "CHF".
CURRENCY_SYMBOLS = {'GBP': '£', 'EUR': '€', 'USD': '$', 'RON': 'RON '}


def _currency_symbol(currency_code: str) -> str:
    """Prefix rendered in front of an amount in the report e-mails."""
    code = (currency_code or 'GBP').upper()
    return CURRENCY_SYMBOLS.get(code, f'{code} ')


def _sum_in_display_currency(amounts, display_currency: str) -> float:
    """Sum ``(currency, amount)`` pairs into ``display_currency``.

    Each entry stores the currency it was logged in (``Entry.currency`` defaults
    to EUR, ``InsurancePolicy.currency`` to USD) while the user reads one display
    currency, so a report must convert BEFORE adding — the same F1/F28 rule the
    dashboard, vehicle stats and the PDF report already follow.

    The FX lookup is skipped entirely when every amount is already in the display
    currency: that is the common case, and these builders run inside a scheduled
    job where an avoidable outbound call is pure cost.
    """
    pairs = [((currency or 'EUR').upper(), float(amount or 0))
             for currency, amount in amounts]
    if not pairs:
        return 0.0
    if all(currency == display_currency for currency, _ in pairs):
        return sum(amount for _, amount in pairs)

    from app.services import currency as currency_service
    rates = currency_service.get_rates_cached(current_app._get_current_object())
    total, _converted, _fx_applied = currency_service.sum_to_display(
        pairs, display_currency, rates)
    return total


def get_user_weekly_summary(user_id: int) -> Dict:
    """Generate weekly summary data for a user."""
    from app.models import User, Vehicle, FuelEntry, ServiceEntry

    user = db.session.get(User, user_id)
    if not user:
        return {}

    # R6: UTC "today", matching the rest of the API and the period label the
    # e-mail prints, so the window and the label can never disagree by a day.
    week_ago = utc_today() - timedelta(days=7)
    display_currency = (user.currency or 'GBP').upper()

    # R4-02: Vehicle has no `is_active` column — "active" means NOT archived.
    vehicles = Vehicle.query.filter_by(user_id=user_id, archived=False).all()
    vehicle_ids = [v.id for v in vehicles]

    # Fuel stats. R4-02: the column is `total_price`, not `total_cost`.
    fuel_entries = FuelEntry.query.filter(
        FuelEntry.vehicle_id.in_(vehicle_ids),
        FuelEntry.date >= week_ago
    ).all()

    fuel_spent = _sum_in_display_currency(
        ((e.currency, e.total_price or e.amount) for e in fuel_entries),
        display_currency,
    )

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
        # The template renders "{{ currency }}{{ amount }}", so this must be the
        # SYMBOL — the raw code rendered as "GBP40.00".
        'currency': _currency_symbol(display_currency),
    }


def get_user_monthly_summary(user_id: int, month: int, year: int) -> Tuple[Dict, List[Dict]]:
    """Generate monthly summary data for a user.

    Always returns a ``(summary, per-vehicle breakdown)`` tuple — its caller in
    ``send_monthly_reports`` unpacks two values, so a bare dict on the
    missing-user path would raise inside the scheduled job.
    """
    from app.models import (User, Vehicle, FuelEntry, ServiceEntry, RepairEntry,
                            TaxEntry, ParkingEntry, InsurancePolicy)

    user = db.session.get(User, user_id)
    if not user:
        return {}, []

    # Calculate date range (explicit year/month/day — no local-time dependency)
    from calendar import monthrange
    first_day = date(year, month, 1)
    last_day = date(year, month, monthrange(year, month)[1])

    display_currency = (user.currency or 'GBP').upper()

    # R4-02: "active" means NOT archived (there is no `is_active` column).
    vehicles = Vehicle.query.filter_by(user_id=user_id, archived=False).all()
    vehicle_ids = [v.id for v in vehicles]

    def _in_period(model, date_column):
        return model.query.filter(
            model.vehicle_id.in_(vehicle_ids),
            date_column >= first_day,
            date_column <= last_day,
        ).all()

    # Fetched once and reused for the per-vehicle breakdown below — the previous
    # code re-queried fuel and service once PER VEHICLE.
    fuel_entries = _in_period(FuelEntry, FuelEntry.date)
    service_entries = _in_period(ServiceEntry, ServiceEntry.date)
    repair_entries = _in_period(RepairEntry, RepairEntry.date)
    parking_entries = _in_period(ParkingEntry, ParkingEntry.date)
    tax_entries = _in_period(TaxEntry, TaxEntry.date)
    policies = _in_period(InsurancePolicy, InsurancePolicy.start_date)

    # R4-02: fuel books its total in `total_price`; every other entry type uses
    # the shared `amount` column (`cost` exists only as a to_dict alias).
    def _fuel_amounts(entries):
        return ((e.currency, e.total_price or e.amount) for e in entries)

    def _entry_amounts(entries):
        return ((e.currency, e.amount) for e in entries)

    fuel_total = _sum_in_display_currency(_fuel_amounts(fuel_entries), display_currency)
    services_total = _sum_in_display_currency(_entry_amounts(service_entries), display_currency)
    repairs_total = _sum_in_display_currency(_entry_amounts(repair_entries), display_currency)
    parking_total = _sum_in_display_currency(_entry_amounts(parking_entries), display_currency)
    taxes_total = _sum_in_display_currency(_entry_amounts(tax_entries), display_currency)
    insurance_total = _sum_in_display_currency(
        ((p.currency, p.premium) for p in policies), display_currency)

    grand_total = (fuel_total + services_total + repairs_total
                   + parking_total + taxes_total + insurance_total)

    # Per-vehicle breakdown, grouped from the rows already fetched above.
    vehicle_breakdown = []
    for v in vehicles:
        v_fuel = _sum_in_display_currency(
            _fuel_amounts(e for e in fuel_entries if e.vehicle_id == v.id),
            display_currency,
        )
        v_service = _sum_in_display_currency(
            _entry_amounts(e for e in service_entries if e.vehicle_id == v.id),
            display_currency,
        )
        v_total = v_fuel + v_service

        if v_total > 0:
            vehicle_breakdown.append({
                'name': v.name,
                'fuel': f"{v_fuel:.2f}",
                'service': f"{v_service:.2f}",
                'total': f"{v_total:.2f}"
            })

    return {
        'fuel_total': f"{fuel_total:.2f}",
        'services_total': f"{services_total:.2f}",
        'repairs_total': f"{repairs_total:.2f}",
        'parking_total': f"{parking_total:.2f}",
        'taxes_insurance_total': f"{taxes_total + insurance_total:.2f}",
        'grand_total': f"{grand_total:.2f}",
        'currency': _currency_symbol(display_currency),
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
            user_domain = link_domain_for(user)
            
            logo_url = f"{user_domain}/icons/logo.png"
            verify_link = f"{user_domain}/verify-email?token={token}"
            
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
            user_domain = link_domain_for(user)
            logo_url = f"{user_domain}/icons/logo.png"
            reset_link = f"{user_domain}/reset-password?token={token}"
            
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
        user_domain = link_domain_for(user)
        logo_url = f"{user_domain}/icons/logo.png"
        
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
        
        # M10 audit: rendered via Jinja render_template_string, so every {{ }}
        # value below (UA-derived device/browser, GeoIP city/country/ISP, IP)
        # is auto-escaped. Do NOT wrap these in markupsafe.escape() — passing a
        # Markup('None') for the nullable `isp` would defeat the template's
        # {% if isp %} guard — and do NOT switch this body to an f-string.
        content_html = render_template_string(
            NEW_LOGIN_ALERT_TEMPLATE,
            user_name=user.display_name or user.username,
            login_time=datetime.now(timezone.utc).strftime('%B %d, %Y at %I:%M %p UTC'),
            ip_address=ip_address,
            device_info=device_display,
            device_icon=device_icon,
            browser_version=browser_version,
            location=location,
            isp=isp if isp and isp != 'Private Network' else None,
            logo_url=logo_url,
            change_password_url=f"{user_domain}/settings/security",
            settings_url=f"{user_domain}/settings/security"
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
        user_domain = link_domain_for(user)
        logo_url = f"{user_domain}/icons/logo.png"
        
        # Format known locations for display
        known_locations_display = ', '.join(known_locations) if known_locations else 'None recorded'
        
        # M10 audit: same as send_new_login_alert — every {{ }} value below
        # (GeoIP country/city/ISP/IP, known-location names) is Jinja
        # auto-escaped here. Do NOT wrap in escape() or switch to an f-string.
        content_html = render_template_string(
            SUSPICIOUS_LOCATION_TEMPLATE,
            user_name=user.display_name or user.username,
            country=location_info.get('country', 'Unknown'),
            country_code=location_info.get('country_code', 'XX'),
            city=location_info.get('city', 'Unknown'),
            ip_address=location_info.get('ip', 'Unknown'),
            isp=location_info.get('isp', 'Unknown'),
            login_time=datetime.now(timezone.utc).strftime('%B %d, %Y at %I:%M %p UTC'),
            known_locations=known_locations_display,
            logo_url=logo_url,
            change_password_url=f"{user_domain}/settings/security",
            sessions_url=f"{user_domain}/settings/security"
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

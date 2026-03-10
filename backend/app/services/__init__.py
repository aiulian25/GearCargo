"""
GearCargo - Background Task Scheduler Service
"""

from datetime import datetime, date, timedelta
from flask_apscheduler import APScheduler

scheduler = APScheduler()


def init_scheduler(app):
    """Initialize the background task scheduler."""
    scheduler.init_app(app)
    
    # Add scheduled jobs
    scheduler.add_job(
        id='check_reminders',
        func=check_due_reminders,
        trigger='interval',
        hours=1,
        args=[app]
    )
    
    scheduler.add_job(
        id='check_predictions',
        func=generate_auto_predictions,
        trigger='cron',
        hour=3,  # Run at 3 AM
        args=[app]
    )
    
    scheduler.add_job(
        id='cleanup_old_data',
        func=cleanup_old_data,
        trigger='cron',
        hour=4,  # Run at 4 AM
        args=[app]
    )
    
    scheduler.add_job(
        id='send_scheduled_backups',
        func=process_scheduled_backups,
        trigger='cron',
        hour='*',  # Every hour
        args=[app]
    )
    
    # Email notification jobs
    scheduler.add_job(
        id='send_daily_alerts',
        func=send_daily_email_alerts,
        trigger='cron',
        hour=8,  # Run at 8 AM
        args=[app]
    )
    
    scheduler.add_job(
        id='send_weekly_reports',
        func=send_weekly_reports,
        trigger='cron',
        day_of_week='mon',  # Every Monday
        hour=9,
        args=[app]
    )
    
    scheduler.add_job(
        id='send_monthly_reports',
        func=send_monthly_reports,
        trigger='cron',
        day=1,  # First of month
        hour=9,
        args=[app]
    )
    
    # Fuel price auto-refresh — every Monday at 10 AM UTC
    # (after UK Gov & EU Oil Bulletin publish their weekly updates)
    scheduler.add_job(
        id='refresh_fuel_prices',
        func=refresh_fuel_prices,
        trigger='cron',
        day_of_week='mon',
        hour=10,
        args=[app]
    )
    
    scheduler.start()
    app.logger.info('Scheduler initialized')


def check_due_reminders(app):
    """Check for due reminders and send notifications."""
    with app.app_context():
        from app.models import Reminder, User
        from app import db
        
        today = date.today()
        
        # Get reminders due today or overdue (not completed, not dismissed)
        due_reminders = Reminder.query.filter(
            Reminder.completed == False,
            Reminder.dismissed == False,
            Reminder.due_date.isnot(None),
            Reminder.due_date <= today
        ).all()
        
        for reminder in due_reminders:
            # Check notification settings
            user = User.query.get(reminder.user_id)
            
            if user and user.notifications_enabled:
                # Check if we should notify
                should_notify = False
                
                if reminder.due_date == today:
                    should_notify = True
                elif reminder.due_date < today:
                    # Overdue - notify if not already notified today
                    if not reminder.last_notified_at or \
                       reminder.last_notified_at.date() < today:
                        should_notify = True
                
                if should_notify and reminder.notify_push:
                    # Send push notification
                    from app.routes.push import send_push_to_user
                    
                    title = f"Reminder: {reminder.title}"
                    body = reminder.description or "This reminder is due"
                    
                    if reminder.vehicle:
                        body = f"{body} - {reminder.vehicle.name}"
                    
                    send_push_to_user(
                        user.id,
                        title,
                        body,
                        data={
                            'type': 'reminder',
                            'reminder_id': reminder.id,
                            'vehicle_id': reminder.vehicle_id,
                            'url': f'/reminders/{reminder.id}'
                        },
                        tag=f'reminder-{reminder.id}'
                    )
                    
                    reminder.last_notified_at = datetime.utcnow()
        
        db.session.commit()
        app.logger.info(f'Checked {len(due_reminders)} due reminders')


def generate_auto_predictions(app):
    """Generate AI predictions for vehicles (if Ollama enabled)."""
    with app.app_context():
        if not app.config.get('OLLAMA_ENABLED'):
            return
        
        from app.models import Vehicle, User
        from app import db
        
        # Get vehicles that haven't had predictions recently
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(days=7)
        
        vehicles = Vehicle.query.filter(
            Vehicle.is_active == True,
            (Vehicle.last_prediction_at.is_(None)) |
            (Vehicle.last_prediction_at < cutoff)
        ).limit(10).all()  # Process 10 vehicles at a time
        
        for vehicle in vehicles:
            try:
                # Generate predictions via Ollama
                # This would call the predictions service
                vehicle.last_prediction_at = datetime.utcnow()
            except Exception as e:
                app.logger.error(f'Prediction generation failed for vehicle {vehicle.id}: {e}')
        
        db.session.commit()
        app.logger.info(f'Generated predictions for {len(vehicles)} vehicles')


def cleanup_old_data(app):
    """Clean up old data (logs, expired sessions, etc.)."""
    with app.app_context():
        from app.models import NotificationLog, Backup
        from app import db
        
        # Delete old notification logs (older than 90 days)
        cutoff = datetime.utcnow() - timedelta(days=90)
        
        deleted_logs = NotificationLog.query.filter(
            NotificationLog.created_at < cutoff
        ).delete()
        
        # Delete old backups based on retention settings
        # This is simplified - in production, check per-user retention
        deleted_backups = Backup.query.filter(
            Backup.created_at < cutoff,
            Backup.cloud_file_id.is_(None)  # Only local backups
        ).delete()
        
        db.session.commit()
        app.logger.info(f'Cleanup: deleted {deleted_logs} logs, {deleted_backups} backups')


def process_scheduled_backups(app):
    """Process scheduled backups with weekly, monthly, and quarterly frequencies."""
    with app.app_context():
        from app.models import BackupSchedule, Backup, User, Vehicle, FuelEntry, ServiceEntry
        from app.models import RepairEntry, TaxEntry, ParkingEntry, Reminder, InsurancePolicy, Attachment
        from app import db
        import os
        import json
        import zipfile
        from io import BytesIO
        import hashlib
        
        now = datetime.utcnow()
        current_hour = now.hour
        
        # Get schedules that should run this hour
        schedules = BackupSchedule.query.filter(
            BackupSchedule.enabled == True,
            BackupSchedule.hour == current_hour
        ).all()
        
        for schedule in schedules:
            should_run = False
            
            if schedule.frequency == 'weekly':
                # Run on specific day of week (0=Monday, 6=Sunday)
                if now.weekday() == (schedule.day_of_week or 0):
                    should_run = True
            elif schedule.frequency == 'monthly':
                # Run on specific day of month
                if now.day == (schedule.day_of_month or 1):
                    should_run = True
            elif schedule.frequency == 'quarterly':
                # Run every 3 months on specific day
                quarter_months = [1, 4, 7, 10]  # Jan, Apr, Jul, Oct
                if now.month in quarter_months and now.day == (schedule.day_of_month or 1):
                    should_run = True
            
            # Check if already ran today
            if should_run and schedule.last_run_at:
                if schedule.last_run_at.date() == now.date():
                    should_run = False
            
            if should_run:
                try:
                    user = User.query.get(schedule.user_id)
                    if not user:
                        continue
                    
                    # Create backup record
                    backup = Backup(
                        user_id=schedule.user_id,
                        backup_type='scheduled',
                        format='zip',
                        status='in_progress',
                        started_at=now,
                    )
                    db.session.add(backup)
                    db.session.flush()
                    
                    # Gather user data
                    export_data = {
                        'version': '2.0',
                        'exported_at': now.isoformat(),
                        'backup_type': 'scheduled',
                        'frequency': schedule.frequency,
                        'user': {
                            'email': user.email,
                            'name': user.name,
                        },
                        'vehicles': [],
                        'reminders': [],
                        'insurance_policies': [],
                        'attachments': [],
                    }
                    
                    # Get vehicles and their entries
                    vehicles = Vehicle.query.filter_by(user_id=user.id).all()
                    for vehicle in vehicles:
                        vehicle_data = vehicle.to_dict()
                        vehicle_data['fuel_entries'] = [e.to_dict() for e in FuelEntry.query.filter_by(vehicle_id=vehicle.id).all()]
                        vehicle_data['service_entries'] = [e.to_dict() for e in ServiceEntry.query.filter_by(vehicle_id=vehicle.id).all()]
                        vehicle_data['repair_entries'] = [e.to_dict() for e in RepairEntry.query.filter_by(vehicle_id=vehicle.id).all()]
                        vehicle_data['tax_entries'] = [e.to_dict() for e in TaxEntry.query.filter_by(vehicle_id=vehicle.id).all()]
                        vehicle_data['parking_entries'] = [e.to_dict() for e in ParkingEntry.query.filter_by(vehicle_id=vehicle.id).all()]
                        export_data['vehicles'].append(vehicle_data)
                    
                    export_data['reminders'] = [r.to_dict() for r in Reminder.query.filter_by(user_id=user.id).all()]
                    export_data['insurance_policies'] = [p.to_dict() for p in InsurancePolicy.query.filter_by(user_id=user.id).all()]
                    
                    # Get attachments
                    attachments = []
                    if schedule.include_attachments:
                        attachments = Attachment.query.filter_by(user_id=user.id).all()
                        export_data['attachments'] = [a.to_dict() for a in attachments]
                    
                    # Create ZIP backup
                    zip_buffer = BytesIO()
                    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                        data_json = json.dumps(export_data, indent=2, default=str)
                        zf.writestr('backup_data.json', data_json)
                        
                        # Add manifest
                        manifest = {
                            'version': '2.0',
                            'created_at': now.isoformat(),
                            'backup_type': 'scheduled',
                            'frequency': schedule.frequency,
                            'user_email': user.email,
                            'include_attachments': schedule.include_attachments,
                            'checksum': hashlib.sha256(data_json.encode()).hexdigest(),
                        }
                        zf.writestr('manifest.json', json.dumps(manifest, indent=2))
                        
                        # Add attachments
                        if schedule.include_attachments:
                            for attachment in attachments:
                                if attachment.filepath and os.path.exists(attachment.filepath):
                                    arcname = f'attachments/{attachment.id}/{attachment.filename}'
                                    zf.write(attachment.filepath, arcname)
                    
                    # Save to disk
                    backup_folder = app.config.get('BACKUP_FOLDER', '/app/volumes/backups')
                    user_folder = os.path.join(backup_folder, str(user.id))
                    os.makedirs(user_folder, exist_ok=True)
                    
                    timestamp = now.strftime('%Y%m%d_%H%M%S')
                    filename = f'backup_{timestamp}.zip'
                    filepath = os.path.join(user_folder, filename)
                    
                    zip_buffer.seek(0)
                    with open(filepath, 'wb') as f:
                        f.write(zip_buffer.read())
                    
                    file_size = os.path.getsize(filepath)
                    
                    # Update backup record
                    backup.filename = filename
                    backup.filepath = filepath
                    backup.file_size = file_size
                    backup.vehicles_count = len(export_data['vehicles'])
                    backup.entries_count = sum(
                        len(v.get('fuel_entries', [])) +
                        len(v.get('service_entries', [])) +
                        len(v.get('repair_entries', [])) +
                        len(v.get('tax_entries', [])) +
                        len(v.get('parking_entries', []))
                        for v in export_data['vehicles']
                    )
                    backup.reminders_count = len(export_data['reminders'])
                    backup.attachments_count = len(export_data.get('attachments', []))
                    backup.status = 'completed'
                    backup.completed_at = datetime.utcnow()
                    
                    # Send to external server if configured
                    if schedule.external_enabled and schedule.external_url:
                        try:
                            import requests
                            zip_buffer.seek(0)
                            headers = {
                                'Content-Type': 'application/octet-stream',
                                'X-API-Key': schedule.external_api_key or '',
                                'X-Backup-Path': schedule.external_path or '/backups',
                            }
                            response = requests.put(
                                schedule.external_url,
                                data=zip_buffer.read(),
                                headers=headers,
                                timeout=300,
                                verify=True
                            )
                            if response.status_code not in [200, 201]:
                                backup.error_message = f"External upload returned {response.status_code}"
                        except Exception as ext_error:
                            backup.error_message = f"External upload failed: {str(ext_error)}"
                    
                    # Update schedule
                    schedule.last_run_at = now
                    schedule.last_status = 'completed'
                    schedule.last_error = None
                    schedule.calculate_next_run()
                    
                    # Cleanup old backups
                    cleanup_user_backups(user.id, schedule.max_backups, schedule.retention_days, user_folder, db)
                    
                    # Send notification if enabled
                    if schedule.notify_on_success:
                        send_backup_notification(user, backup, 'success', app)
                    
                    app.logger.info(f'Scheduled backup completed for user {user.id}: {filename}')
                    
                except Exception as e:
                    if backup:
                        backup.status = 'failed'
                        backup.error_message = str(e)
                        backup.completed_at = datetime.utcnow()
                    
                    schedule.last_status = 'failed'
                    schedule.last_error = str(e)
                    
                    if schedule.notify_on_failure:
                        send_backup_notification(user, None, 'failure', app, str(e))
                    
                    app.logger.error(f'Scheduled backup failed for user {schedule.user_id}: {e}')
        
        db.session.commit()


def cleanup_user_backups(user_id, max_backups, retention_days, user_folder, db):
    """Clean up old backups for a user."""
    import os
    from app.models import Backup
    
    if not os.path.exists(user_folder):
        return
    
    # Get all backup files
    files = []
    for f in os.listdir(user_folder):
        if f.startswith('backup_') and f.endswith('.zip'):
            filepath = os.path.join(user_folder, f)
            mtime = os.path.getmtime(filepath)
            files.append((filepath, mtime))
    
    # Sort by modification time (newest first)
    files.sort(key=lambda x: x[1], reverse=True)
    
    cutoff_time = datetime.utcnow() - timedelta(days=retention_days or 90)
    cutoff_timestamp = cutoff_time.timestamp()
    
    for i, (filepath, mtime) in enumerate(files):
        should_delete = False
        
        if i >= (max_backups or 10):
            should_delete = True
        
        if mtime < cutoff_timestamp:
            should_delete = True
        
        if should_delete:
            try:
                os.remove(filepath)
            except:
                pass
    
    # Clean up old database records
    old_backups = Backup.query.filter(
        Backup.user_id == user_id,
        Backup.created_at < cutoff_time,
        Backup.cloud_file_id.is_(None)
    ).all()
    
    for backup in old_backups:
        db.session.delete(backup)


def send_backup_notification(user, backup, status, app, error_message=None):
    """Send backup completion notification."""
    try:
        from app.routes.push import send_push_to_user
        
        if status == 'success':
            title = 'Backup Completed'
            body = f'Your scheduled backup has completed successfully.'
            if backup:
                body += f' Size: {format_size(backup.file_size)}'
        else:
            title = 'Backup Failed'
            body = f'Your scheduled backup failed.'
            if error_message:
                body += f' Error: {error_message[:100]}'
        
        send_push_to_user(
            user.id,
            title,
            body,
            data={
                'type': 'backup',
                'status': status,
                'url': '/settings'
            },
            tag='backup-notification'
        )
    except Exception as e:
        app.logger.error(f'Failed to send backup notification: {e}')


def format_size(size):
    """Format file size."""
    if not size:
        return '0 B'
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


# ============================================================
# EMAIL NOTIFICATION JOBS
# ============================================================

def send_daily_email_alerts(app):
    """Send daily email alerts for insurance, tax, service due dates."""
    with app.app_context():
        if not app.config.get('MAIL_ENABLED'):
            app.logger.info('Email not enabled, skipping daily alerts')
            return
        
        from app.models import User
        from app.services.email_service import (
            EmailService, get_insurance_alerts, get_tax_alerts, 
            get_service_alerts
        )
        
        # Get all users with email notifications enabled
        users = User.query.filter(
            User.is_active == True,
            User.notifications_enabled == True
        ).all()
        
        sent_count = 0
        
        for user in users:
            try:
                alerts_to_send = []
                days_before = user.alert_days_before or 14
                
                # Gather alerts based on user preferences
                if user.email_insurance_alerts:
                    alerts_to_send.extend(get_insurance_alerts(user.id, days_before))
                
                if user.email_tax_alerts:
                    alerts_to_send.extend(get_tax_alerts(user.id, days_before))
                
                if user.email_service_alerts or user.email_reminder_alerts:
                    alerts_to_send.extend(get_service_alerts(user.id, days_before))
                
                # Only send if there are urgent or warning alerts
                urgent_alerts = [a for a in alerts_to_send if a['severity'] in ['urgent', 'warning']]
                
                if urgent_alerts:
                    # Determine primary alert type
                    if any('Insurance' in a['title'] for a in urgent_alerts):
                        alert_type = 'insurance'
                    elif any('Tax' in a['title'] for a in urgent_alerts):
                        alert_type = 'tax'
                    else:
                        alert_type = 'reminder'
                    
                    if EmailService.send_alert_notification(user, urgent_alerts, alert_type):
                        sent_count += 1
                        
            except Exception as e:
                app.logger.error(f'Failed to send daily alerts to user {user.id}: {e}')
        
        app.logger.info(f'Daily alerts: sent to {sent_count} users')


def send_weekly_reports(app):
    """Send weekly summary reports to users who opted in."""
    with app.app_context():
        if not app.config.get('MAIL_ENABLED'):
            return
        
        from app.models import User
        from app import db
        from app.services.email_service import (
            EmailService, get_user_weekly_summary, get_all_alerts_for_user
        )
        
        users = User.query.filter(
            User.is_active == True,
            User.weekly_report_enabled == True
        ).all()
        
        sent_count = 0
        
        for user in users:
            try:
                summary = get_user_weekly_summary(user.id)
                all_alerts = get_all_alerts_for_user(user.id, 14)
                
                # Combine all upcoming alerts
                upcoming = []
                for alert_type, alerts in all_alerts.items():
                    upcoming.extend(alerts[:3])  # Max 3 per type
                
                if EmailService.send_weekly_report(user, summary, upcoming[:5]):
                    user.last_weekly_report = datetime.utcnow()
                    sent_count += 1
                    
            except Exception as e:
                app.logger.error(f'Failed to send weekly report to user {user.id}: {e}')
        
        db.session.commit()
        app.logger.info(f'Weekly reports: sent to {sent_count} users')


def send_monthly_reports(app):
    """Send monthly summary reports to users who opted in."""
    with app.app_context():
        if not app.config.get('MAIL_ENABLED'):
            return
        
        from app.models import User
        from app import db
        from app.services.email_service import EmailService, get_user_monthly_summary
        
        users = User.query.filter(
            User.is_active == True,
            User.monthly_report_enabled == True
        ).all()
        
        sent_count = 0
        
        # Get last month
        today = date.today()
        if today.month == 1:
            month = 12
            year = today.year - 1
        else:
            month = today.month - 1
            year = today.year
        
        for user in users:
            try:
                summary, vehicles = get_user_monthly_summary(user.id, month, year)
                
                # Generate insights
                insights = []
                if summary:
                    total = float(summary.get('grand_total', '0').replace(',', ''))
                    fuel = float(summary.get('fuel_total', '0').replace(',', ''))
                    
                    if total > 0:
                        fuel_pct = (fuel / total) * 100
                        insights.append(f"Fuel accounted for {fuel_pct:.0f}% of your expenses this month.")
                    
                    if len(vehicles) > 1:
                        most_expensive = max(vehicles, key=lambda v: float(v['total'].replace(',', '')))
                        insights.append(f"{most_expensive['name']} was your most expensive vehicle this month.")
                
                if EmailService.send_monthly_report(user, month, year, summary, vehicles, insights):
                    user.last_monthly_report = datetime.utcnow()
                    sent_count += 1
                    
            except Exception as e:
                app.logger.error(f'Failed to send monthly report to user {user.id}: {e}')
        
        db.session.commit()
        app.logger.info(f'Monthly reports: sent to {sent_count} users')


def refresh_fuel_prices(app):
    """Refresh fuel prices for all supported countries from live APIs.
    
    Called weekly by scheduler (Monday 10 AM) and can be triggered manually.
    """
    with app.app_context():
        from app.services.fuel_price_service import refresh_all_prices
        try:
            updated, failed = refresh_all_prices(app)
            app.logger.info(f'Fuel price refresh: {updated} countries updated, {failed} failed')
        except Exception as e:
            app.logger.error(f'Fuel price refresh job failed: {e}')

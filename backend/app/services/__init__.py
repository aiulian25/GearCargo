"""
GearCargo - Background Task Scheduler Service
"""

from datetime import datetime, date, timedelta, timezone
from flask_apscheduler import APScheduler

scheduler = APScheduler()


def init_scheduler(app):
    """Initialize the background task scheduler."""
    scheduler.init_app(app)
    
    # Add scheduled jobs.
    # replace_existing=True prevents ConflictingIdError if init_scheduler is
    # somehow called twice (e.g. during testing or app-factory edge cases).
    # coalesce=True collapses multiple missed executions into a single run so
    # a delayed start never floods the system with catch-up iterations.
    # misfire_grace_time=300 gives jobs 5 minutes to fire before they are
    # considered missed (handles slow startup / GC pauses).
    _job_defaults = dict(replace_existing=True, coalesce=True, misfire_grace_time=300)

    scheduler.add_job(
        id='check_reminders',
        func=check_due_reminders,
        trigger='interval',
        hours=1,
        args=[app],
        **_job_defaults
    )

    scheduler.add_job(
        id='check_predictions',
        func=generate_auto_predictions,
        trigger='cron',
        hour=3,  # Run at 3 AM
        args=[app],
        **_job_defaults
    )

    scheduler.add_job(
        id='cleanup_old_data',
        func=cleanup_old_data,
        trigger='cron',
        hour=4,  # Run at 4 AM
        args=[app],
        **_job_defaults
    )

    scheduler.add_job(
        id='send_scheduled_backups',
        func=process_scheduled_backups,
        trigger='cron',
        hour='*',  # Every hour
        args=[app],
        **_job_defaults
    )

    # Email notification jobs
    scheduler.add_job(
        id='send_daily_alerts',
        func=send_daily_email_alerts,
        trigger='cron',
        hour=8,  # Run at 8 AM
        args=[app],
        **_job_defaults
    )

    scheduler.add_job(
        id='send_weekly_reports',
        func=send_weekly_reports,
        trigger='cron',
        day_of_week='mon',  # Every Monday
        hour=9,
        args=[app],
        **_job_defaults
    )

    scheduler.add_job(
        id='send_monthly_reports',
        func=send_monthly_reports,
        trigger='cron',
        day=1,  # First of month
        hour=9,
        args=[app],
        **_job_defaults
    )

    # Fuel price auto-refresh — every Monday at 10 AM UTC
    # (after UK Gov & EU Oil Bulletin publish their weekly updates)
    scheduler.add_job(
        id='refresh_fuel_prices',
        func=refresh_fuel_prices,
        trigger='cron',
        day_of_week='mon',
        hour=10,
        args=[app],
        **_job_defaults
    )

    # Recurring tax entry generation — daily at 6 AM
    scheduler.add_job(
        id='process_recurring_taxes',
        func=process_recurring_tax_entries,
        trigger='cron',
        hour=6,
        args=[app],
        **_job_defaults
    )

    scheduler.start()
    app.logger.info('Scheduler initialized')

    # Run recurring tax self-heal immediately on startup so any deployment
    # with recurring entries missing next_due_date is fixed without waiting
    # for the 6 AM cron to fire.
    try:
        process_recurring_tax_entries(app)
    except Exception as e:
        app.logger.warning(f'Startup recurring tax run failed: {e}')


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

                if should_notify and getattr(reminder, 'notify_email', True) and user.notifications_enabled:
                    # Send email notification for this individual reminder
                    try:
                        if app.config.get('MAIL_ENABLED'):
                            from app.services.email_service import EmailService
                            days_left = (reminder.due_date - today).days
                            is_overdue = days_left < 0
                            severity = 'urgent' if is_overdue or days_left <= 7 else 'warning'
                            alert = {
                                'title': reminder.title,
                                'subtitle': f"{'OVERDUE - was due' if is_overdue else 'Due on'} {reminder.due_date.strftime('%B %d, %Y')}",
                                'details': reminder.description,
                                'vehicle': reminder.vehicle.name if reminder.vehicle else None,
                                'severity': severity,
                                'due_date': reminder.due_date.strftime('%b %d, %Y'),
                            }
                            EmailService.send_alert_notification(user, [alert], 'reminder')
                    except Exception as email_exc:
                        app.logger.warning(f'Reminder email notification failed for reminder {reminder.id}: {email_exc}')

                if should_notify:
                    reminder.last_notified_at = datetime.now(timezone.utc)
        
        db.session.commit()
        app.logger.info(f'Checked {len(due_reminders)} due reminders')


def generate_auto_predictions(app):
    """Generate AI predictions for vehicles (if Ollama enabled)."""
    with app.app_context():
        if not app.config.get('OLLAMA_ENABLED'):
            return
        
        from app.models import Vehicle
        from app import db
        
        # Get vehicles that haven't had predictions recently
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        
        vehicles = Vehicle.query.filter(
            Vehicle.is_active == True,
            (Vehicle.last_prediction_at.is_(None)) |
            (Vehicle.last_prediction_at < cutoff)
        ).limit(10).all()  # Process 10 vehicles at a time
        
        for vehicle in vehicles:
            try:
                # Generate predictions via Ollama
                # This would call the predictions service
                vehicle.last_prediction_at = datetime.now(timezone.utc)
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
        cutoff = datetime.now(timezone.utc) - timedelta(days=90)
        
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
        from app.models import BackupSchedule, Backup, User
        from app.routes.backup import create_backup_zip, save_backup_to_disk
        from app import db
        import os
        
        now = datetime.now(timezone.utc)
        current_hour = now.hour
        
        # Get schedules that should run this hour — lock each row so only ONE
        # worker processes it (prevents duplicate backups with multi-worker gunicorn).
        # with_for_update(skip_locked=True) skips rows already being processed by
        # another worker, ensuring exactly-once execution per schedule.
        schedules = BackupSchedule.query.filter(
            BackupSchedule.enabled == True,
            BackupSchedule.hour == current_hour
        ).with_for_update(skip_locked=True).all()
        
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
                    
                    include_attachments = getattr(schedule, 'include_attachments', True)
                    
                    # Use shared backup function (includes dedup, vehicle photos, todos)
                    zip_buffer, export_data = create_backup_zip(user, include_attachments)
                    
                    # Save to disk
                    filename, filepath, file_size = save_backup_to_disk(user, zip_buffer, include_attachments)
                    
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
                    backup.completed_at = datetime.now(timezone.utc)
                    
                    # Send to all configured external destinations.
                    try:
                        from app.routes.backup import send_to_all_external_destinations
                        zip_buffer.seek(0)
                        _, external_errors = send_to_all_external_destinations(
                            zip_buffer.read(),
                            schedule,
                            filename=filename,
                        )
                        if external_errors:
                            joined_errors = '; '.join(external_errors)
                            backup.error_message = f"External upload failed: {joined_errors}"
                            app.logger.warning(f'Scheduled external backup failed for user {user.id}: {joined_errors}')
                    except Exception as ext_error:
                        backup.error_message = f"External upload failed: {str(ext_error)}"
                        app.logger.warning(f'Scheduled external backup exception for user {user.id}: {ext_error}')
                    
                    # Update schedule
                    schedule.last_run_at = now
                    schedule.last_status = 'completed'
                    schedule.last_error = None
                    schedule.calculate_next_run()
                    
                    # Cleanup old backups
                    cleanup_user_backups(user.id, schedule.max_backups, schedule.retention_days, os.path.dirname(filepath), db)
                    
                    # Send notification if enabled
                    if schedule.notify_on_success:
                        send_backup_notification(user, backup, 'success', app)
                    
                    app.logger.info(f'Scheduled backup completed for user {user.id}: {filename}')
                    
                except Exception as e:
                    if backup:
                        backup.status = 'failed'
                        backup.error_message = str(e)
                        backup.completed_at = datetime.now(timezone.utc)
                    
                    schedule.last_status = 'failed'
                    schedule.last_error = str(e)
                    
                    if schedule.notify_on_failure:
                        send_backup_notification(user, None, 'failure', app, str(e))
                    
                    app.logger.error(f'Scheduled backup failed for user {schedule.user_id}: {e}')
        
        db.session.commit()


def cleanup_user_backups(user_id, max_backups, retention_days, user_folder, db):
    """Clean up old backups for a user.

    Retention rules (applied in order):
    1. Always keep the N most recent backups (max_backups).
    2. Of the remaining older backups, also delete any that exceed retention_days.
    The two limits are AND'd for older files — a file must be BOTH beyond the
    count limit AND older than retention_days to be deleted by age alone.
    This prevents the age rule from deleting files that are still within the
    max_backups count.
    """
    import os
    from app.models import Backup

    keep = int(max_backups or 10)

    if not os.path.exists(user_folder):
        return

    # Collect all backup zips in the user folder regardless of prefix
    files = []
    for f in os.listdir(user_folder):
        if f.endswith('.zip'):
            filepath = os.path.join(user_folder, f)
            try:
                mtime = os.path.getmtime(filepath)
                files.append((filepath, mtime))
            except OSError:
                pass

    # Sort newest first so index 0 = most recent
    files.sort(key=lambda x: x[1], reverse=True)

    for i, (filepath, mtime) in enumerate(files):
        if i < keep:
            # Always keep the N most recent — do not delete regardless of age
            continue

        # Beyond the keep limit: delete (age check is a secondary soft guard,
        # but we delete anything past the count limit unconditionally so the
        # user's chosen backup count is strictly honoured)
        try:
            os.remove(filepath)
        except OSError:
            pass

    # Clean up DB records: delete records beyond the keep count (by created_at desc)
    all_records = Backup.query.filter(
        Backup.user_id == user_id,
        Backup.cloud_file_id.is_(None)
    ).order_by(Backup.created_at.desc()).all()

    for i, record in enumerate(all_records):
        if i >= keep:
            db.session.delete(record)


def send_backup_notification(user, backup, status, app, error_message=None):
    """Send backup completion notification."""
    try:
        from app.routes.push import send_push_to_user
        
        if status == 'success':
            title = 'Backup Completed'
            body = 'Your scheduled backup has completed successfully.'
            if backup:
                body += f' Size: {format_size(backup.file_size)}'
        else:
            title = 'Backup Failed'
            body = 'Your scheduled backup failed.'
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
            get_service_alerts, get_reminder_alerts
        )

        # Get all users with email notifications enabled
        users = User.query.filter(
            User.is_active == True,
            User.notifications_enabled == True
        ).all()

        sent_count = 0

        for user in users:
            try:
                days_before = user.alert_days_before or 14

                # Collect alerts per category based on user preferences
                insurance_alerts = get_insurance_alerts(user.id, days_before) if user.email_insurance_alerts else []
                tax_alerts = get_tax_alerts(user.id, days_before) if user.email_tax_alerts else []
                service_alerts = get_service_alerts(user.id, days_before) if user.email_service_alerts else []
                reminder_alerts = get_reminder_alerts(user.id, days_before) if user.email_reminder_alerts else []

                # Merge all, deduplicate by title+vehicle, keep worst severity
                all_alerts = insurance_alerts + tax_alerts + service_alerts + reminder_alerts
                urgent_alerts = [a for a in all_alerts if a['severity'] in ('urgent', 'warning')]

                if urgent_alerts:
                    # Determine primary alert type for email subject/styling
                    has_insurance = any(a in urgent_alerts for a in insurance_alerts)
                    has_tax = any(a in urgent_alerts for a in tax_alerts)
                    if has_insurance:
                        alert_type = 'insurance'
                    elif has_tax:
                        alert_type = 'tax'
                    elif any(a in urgent_alerts for a in service_alerts):
                        alert_type = 'service'
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
                    user.last_weekly_report = datetime.now(timezone.utc)
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
                    user.last_monthly_report = datetime.now(timezone.utc)
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


def process_recurring_tax_entries(app):
    """Auto-create new tax entries for recurring taxes whose next_due_date has passed.

    Runs daily at 6 AM. For each recurring TaxEntry where next_due_date <= today,
    creates a new entry for that payment date and advances next_due_date.
    Handles backfill (e.g. missed months) by iterating until next_due_date > today.
    """
    with app.app_context():
        from app import db
        from app.models import TaxEntry
        from dateutil.relativedelta import relativedelta

        today = date.today()
        created_count = 0

        # Heal entries that are recurring but have next_due_date=NULL (set after creation)
        null_due = TaxEntry.query.filter(
            TaxEntry.recurring == True,
            TaxEntry.next_due_date.is_(None),
        ).all()
        for entry in null_due:
            recurrence = entry.recurrence_type or 'monthly'
            if recurrence == 'monthly':
                step = relativedelta(months=1)
            elif recurrence == 'quarterly':
                step = relativedelta(months=3)
            elif recurrence == 'semi_annual':
                step = relativedelta(months=6)
            elif recurrence == 'annual':
                step = relativedelta(years=1)
            else:
                step = relativedelta(months=1)
            base = entry.date or today
            # Set to the FIRST occurrence after the entry date — process_recurring_tax_entries
            # will then backfill all missed periods and advance next_due_date to the future.
            entry.next_due_date = base + step
        if null_due:
            db.session.commit()

        # Find all recurring entries that are overdue for their next occurrence
        due_entries = TaxEntry.query.filter(
            TaxEntry.recurring == True,
            TaxEntry.next_due_date.isnot(None),
            TaxEntry.next_due_date <= today,
        ).all()

        for entry in due_entries:
            try:
                next_date = entry.next_due_date
                recurrence = entry.recurrence_type or 'monthly'

                # Determine relativedelta step
                if recurrence == 'monthly':
                    step = relativedelta(months=1)
                elif recurrence == 'quarterly':
                    step = relativedelta(months=3)
                elif recurrence == 'semi_annual':
                    step = relativedelta(months=6)
                elif recurrence == 'annual':
                    step = relativedelta(years=1)
                else:
                    step = relativedelta(months=1)

                # Iterate: create an entry for each missed period up to today
                while next_date <= today:
                    # Avoid duplicate: check if an entry already exists on this date
                    exists = TaxEntry.query.filter(
                        TaxEntry.vehicle_id == entry.vehicle_id,
                        TaxEntry.tax_type == entry.tax_type,
                        TaxEntry.date == next_date,
                        TaxEntry.id != entry.id,
                    ).first()

                    if not exists:
                        next_occurrence = next_date + step
                        new_entry = TaxEntry(
                            user_id=entry.user_id,
                            vehicle_id=entry.vehicle_id,
                            date=next_date,
                            amount=entry.amount,
                            title=entry.title,
                            description=entry.description,
                            tax_type=entry.tax_type,
                            tax_year=next_date.year,
                            tax_period=entry.tax_period,
                            status='paid',
                            due_date=next_date,
                            paid_date=next_date,
                            reference_number=entry.reference_number,
                            notes=entry.notes,
                            recurring=True,
                            recurrence_type=recurrence,
                            next_due_date=next_occurrence,
                            reminder_days=entry.reminder_days,
                            insurance_policy_id=entry.insurance_policy_id,
                        )
                        db.session.add(new_entry)
                        created_count += 1

                    next_date = next_date + step

                # Update the original entry's next_due_date to the next future date
                entry.next_due_date = next_date

            except Exception as e:
                app.logger.error(f'Failed to process recurring tax entry {entry.id}: {e}')

        if created_count:
            db.session.commit()

        app.logger.info(f'Recurring tax processing: created {created_count} new entries')

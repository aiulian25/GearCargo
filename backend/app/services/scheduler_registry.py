"""UTC schedule definitions; durable cursors coalesce downtime without replay."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from apscheduler.triggers.cron import CronTrigger


@dataclass
class JobDefinition:
    name: str
    function: object
    seconds: int = None
    cron: dict = None
    start_after: int = None

    def next_time(self, now):
        aware = now.replace(tzinfo=timezone.utc)
        if self.seconds:
            slot = int(aware.timestamp()) // self.seconds + 1
            return datetime.fromtimestamp(slot * self.seconds, timezone.utc).replace(tzinfo=None)
        if self.cron is not None:
            return CronTrigger(timezone=timezone.utc, **self.cron).get_next_fire_time(
                None, aware + timedelta(microseconds=1)).replace(tzinfo=None)
        return None  # A one-time maintenance occurrence, retained after completion.


def readiness_heartbeat(app):
    """The durable scheduler wrapper records completion after this poll runs."""


def job_definitions(app):
    from app import services as jobs
    from app.services.calendar_outbox import process_calendar_outbox
    from app.services.deletion import scheduled_cleanup
    from app.services.scheduled_effects import process_scheduled_effects
    from app.services.startup_jobs import probe_ollama, backfill_ocr
    from app.services.system_backup import daily_backup, weekly_backup
    definitions = [
        JobDefinition('readiness_heartbeat', readiness_heartbeat, seconds=15, start_after=0),
        JobDefinition('calendar_outbox', process_calendar_outbox, seconds=60),
        JobDefinition('scheduled_deliveries', process_scheduled_effects, seconds=60),
        JobDefinition('cleanup_deleted_files', scheduled_cleanup, seconds=300),
        JobDefinition('check_reminders', jobs.check_due_reminders, seconds=3600),
        JobDefinition('check_predictions', jobs.generate_auto_predictions, cron={'hour': 3}),
        JobDefinition('cleanup_old_data', jobs.cleanup_old_data, cron={'hour': 4}),
        JobDefinition('send_scheduled_backups', jobs.process_scheduled_backups, seconds=3600),
        JobDefinition('send_daily_alerts', jobs.send_daily_email_alerts, cron={'hour': 8}),
        JobDefinition('send_weekly_reports', jobs.send_weekly_reports, cron={'day_of_week': 'mon', 'hour': 9}),
        JobDefinition('send_monthly_reports', jobs.send_monthly_reports, cron={'day': 1, 'hour': 9}),
        JobDefinition('refresh_fuel_prices', jobs.refresh_fuel_prices, cron={'day_of_week': 'mon', 'hour': 10}, start_after=60),
        JobDefinition('process_recurring_taxes', jobs.process_recurring_tax_entries, cron={'hour': 6}, start_after=30),
        JobDefinition('process_recurring_parking', jobs.process_recurring_parking_entries, cron={'hour': 6}, start_after=30),
        JobDefinition('process_due_services', jobs.process_due_services, cron={'hour': 6}, start_after=30),
        JobDefinition('process_auto_renew_insurance', jobs.process_auto_renew_insurance, cron={'hour': 6}, start_after=30),
        JobDefinition('check_consumables_due', jobs.check_consumables_due, cron={'hour': 7}),
        JobDefinition('check_warranty_expiry', jobs.check_warranty_expiry, cron={'hour': 7}),
        JobDefinition('check_document_expiry', jobs.check_document_expiry, cron={'hour': 7}),
        JobDefinition('dedupe_reminders', jobs.dedupe_duplicate_reminders, start_after=30),
        JobDefinition('ocr_backfill', backfill_ocr, seconds=900, start_after=15),
    ]
    if app.config.get('OLLAMA_ENABLED', True):
        definitions.append(JobDefinition('ollama_probe', probe_ollama, seconds=3600, start_after=5))
    if app.config.get('SYSTEM_BACKUP_ENABLED', True):
        definitions.extend([
            JobDefinition('system_backup_daily', daily_backup, cron={'hour': 3}),
            JobDefinition('system_backup_weekly', weekly_backup, cron={'day_of_week': 'sun', 'hour': 3, 'minute': 30}),
        ])
    return {definition.name: definition for definition in definitions}

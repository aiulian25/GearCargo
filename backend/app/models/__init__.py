"""
GearCargo - Database Models Package
"""

from app.models.user import User
from app.models.vehicle import Vehicle
from app.models.entry import Entry
from app.models.fuel import FuelEntry
from app.models.service import ServiceEntry
from app.models.repair import RepairEntry
from app.models.tax import TaxEntry
from app.models.parking import ParkingEntry
from app.models.consumable import ConsumableEntry
from app.models.reminder import Reminder
from app.models.prediction import PredictionAlert
from app.models.attachment import Attachment, OcrSlot
from app.models.insurance import InsurancePolicy
from app.models.backup import Backup, BackupSchedule
from app.models.push_subscription import PushSubscription, NotificationLog
from app.models.todo import Todo
from app.models.reconciliation import StatementBatch, StatementTransaction, StatementMatch
from app.models.appointment import Appointment, AppointmentTask, AppointmentExpense
from app.models.tire import TireSet, Tire, FitmentEvent, TreadReading
from app.models.activity_log import ActivityLog
from app.models.blocked_entity import BlockedIP, BlockedDevice
from app.models.email_consent_log import EmailConsentLog
from app.models.app_setting import AppSetting
from app.models.user_session import UserSession
from app.models.passkey import Passkey
from app.models.report_share import ReportShare
from app.models.due_dismissal import DueDismissal
from app.models.fuel_price_history import FuelPriceHistory
from app.models.deletion_task import DeletionTask
from app.models.mutation import MutationOperation
from app.models.calendar_outbox import CalendarOutbox
from app.models.job_run import JobRun, ScheduledEffect

from app.models.import_identity import ImportBatch, ImportIdentity

__all__ = [
    'User',
    'Vehicle',
    'Entry',
    'FuelEntry',
    'ServiceEntry',
    'RepairEntry',
    'TaxEntry',
    'ParkingEntry',
    'ConsumableEntry',
    'Reminder',
    'PredictionAlert',
    'Attachment',
    'OcrSlot',
    'InsurancePolicy',
    'Backup',
    'BackupSchedule',
    'PushSubscription',
    'NotificationLog',
    'Todo',
    'StatementBatch', 'StatementTransaction', 'StatementMatch',
    'Appointment', 'AppointmentTask', 'AppointmentExpense',
    'TireSet', 'Tire', 'FitmentEvent', 'TreadReading',
    'ActivityLog',
    'BlockedIP',
    'BlockedDevice',
    'EmailConsentLog',
    'AppSetting',
    'UserSession',
    'Passkey',
    'ReportShare',
    'DueDismissal',
    'FuelPriceHistory',
    'DeletionTask',
    'MutationOperation',
    'CalendarOutbox',
    'JobRun',
    'ScheduledEffect',
    'ImportBatch',
    'ImportIdentity',
]

# Register cross-model relationship constraints after every model is available.
from app.services import attachment_consistency as _attachment_consistency
from app.services import calendar_outbox as _calendar_outbox
from app.services import scheduler_ownership as _scheduler_ownership

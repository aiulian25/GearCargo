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
from app.models.reminder import Reminder
from app.models.prediction import PredictionAlert
from app.models.attachment import Attachment
from app.models.insurance import InsurancePolicy
from app.models.backup import Backup, BackupSchedule
from app.models.push_subscription import PushSubscription, NotificationLog
from app.models.todo import Todo
from app.models.activity_log import ActivityLog
from app.models.blocked_entity import BlockedIP, BlockedDevice
from app.models.email_consent_log import EmailConsentLog

__all__ = [
    'User',
    'Vehicle',
    'Entry',
    'FuelEntry',
    'ServiceEntry',
    'RepairEntry',
    'TaxEntry',
    'ParkingEntry',
    'Reminder',
    'PredictionAlert',
    'Attachment',
    'InsurancePolicy',
    'Backup',
    'BackupSchedule',
    'PushSubscription',
    'NotificationLog',
    'Todo',
    'ActivityLog',
    'BlockedIP',
    'BlockedDevice',
    'EmailConsentLog',
]

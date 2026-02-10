"""
GearCargo - Scheduler Service
Wrapper for backward compatibility
"""

from app.services import init_scheduler, scheduler

__all__ = ['init_scheduler', 'scheduler']

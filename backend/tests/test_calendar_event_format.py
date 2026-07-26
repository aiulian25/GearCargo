"""Parking calendar events show their cost in the title, like fuel events.

`get_event_data_for_entry` is a pure formatter (attribute access via getattr),
so a lightweight stub entry is enough — no DB needed.
"""

from datetime import date
from types import SimpleNamespace

from app.services.calendar_service import get_event_data_for_entry


def test_parking_event_title_includes_cost():
    entry = SimpleNamespace(
        amount=70.0, location='NCP Reading', parking_type='hourly',
        date=date(2026, 7, 10), notes=None)
    ev = get_event_data_for_entry('parking', entry, 'Nissan Qashqai')
    assert ev is not None
    # Cost shown in the title, mirroring the fuel event convention.
    assert '(70.00)' in ev['title']
    assert 'Parking: Nissan Qashqai @ NCP Reading' in ev['title']


def test_parking_event_title_without_cost_is_unchanged():
    entry = SimpleNamespace(
        amount=None, location='Driveway', parking_type=None,
        date=date(2026, 7, 10), notes=None)
    ev = get_event_data_for_entry('parking', entry, 'Focus')
    assert ev['title'] == '🅿️ Parking: Focus @ Driveway'


def test_fuel_event_title_still_includes_volume_and_cost():
    entry = SimpleNamespace(
        liters=46.1, total_price=70.0, amount=70.0, fuel_type='diesel',
        station='Costco', date=date(2026, 7, 10), notes=None)
    ev = get_event_data_for_entry('fuel', entry, 'Nissan Qashqai')
    assert '46.1L' in ev['title']
    assert '70.00' in ev['title']

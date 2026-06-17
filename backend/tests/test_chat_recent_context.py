"""Unit tests for the chat 'recent entries' context projections.

See app/routes/vehicles.py (_entry_brief / _consumable_brief / _insurance_brief).
These let the assistant answer "when did I last change X, what did it cost,
where?". Pure functions tested with lightweight stand-ins (no DB).
"""

from datetime import date
from types import SimpleNamespace as NS

from app.routes.vehicles import _entry_brief, _consumable_brief, _insurance_brief, _clip


def _svc(**kw):
    base = dict(type='service', date=date(2025, 3, 11), amount=240.0, odometer=85000,
                title=None, service_type='Brake pads', repair_type=None, tax_type=None,
                parking_type=None, garage_name='QuickFit Reading', provider=None,
                station=None, location=None, parts_used=[{'name': 'Front brake pads'}],
                parts_replaced=None, notes='Replaced front pads', description=None, diagnosis=None)
    base.update(kw)
    return NS(**base)


def test_service_brief_has_when_cost_where_parts():
    b = _entry_brief(_svc())
    assert b['date'] == '2025-03-11'
    assert b['cost'] == 240.0
    assert b['where'] == 'QuickFit Reading'
    assert b['label'] == 'Brake pads'
    assert 'Front brake pads' in b['parts']
    assert b['odometer'] == 85000


def test_fuel_brief_includes_station_and_liters():
    f = _svc(type='fuel', service_type=None, station='Shell M4', garage_name=None,
             liters=48.2, fuel_type='diesel', amount=70.5)
    b = _entry_brief(f)
    assert b['where'] == 'Shell M4' and b['liters'] == 48.2 and b['fuel_type'] == 'diesel'


def test_brief_drops_empty_fields_and_caps_text():
    b = _entry_brief(_svc(notes=None, parts_used=None, garage_name=None, provider=None))
    assert 'notes' not in b and 'parts' not in b and 'where' not in b
    long = _svc(notes='x' * 500)
    assert len(_entry_brief(long)['notes']) == 200


def test_consumable_brief():
    c = NS(consumable_type='tyres', brand='Michelin', install_date=date(2024, 10, 1),
           install_odometer=80000, amount=480.0, quantity=4, date=date(2024, 10, 1), odometer=80000)
    b = _consumable_brief(c)
    assert b['item'] == 'tyres' and b['brand'] == 'Michelin'
    assert b['installed_date'] == '2024-10-01' and b['cost'] == 480.0 and b['quantity'] == 4


def test_insurance_brief():
    p = NS(provider='Aviva', policy_type='comprehensive', premium=620.0,
           start_date=date(2025, 1, 1), end_date=date(2025, 12, 31), status='active')
    b = _insurance_brief(p)
    assert b['provider'] == 'Aviva' and b['premium'] == 620.0 and b['status'] == 'active'


def test_clip_handles_none_and_caps():
    assert _clip(None) is None
    assert _clip('  hi  ') == 'hi'
    assert len(_clip('a' * 300, 140)) == 140

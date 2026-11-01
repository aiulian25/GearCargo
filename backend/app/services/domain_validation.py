"""Shared write-domain rules. No repairs or guesses are made for stored data.

API/CSV numbers accept decimal strings (dot separator), round HALF_UP to the
column scale, and reject overflow before and after rounding. Recovery archives
use exact=True: a value needing rounding or normalization must be reviewed.
Negative ledger amounts/costs are refunds or credits; quantities are not signed.
"""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
import math

from flask import g, has_request_context
from sqlalchemy import Boolean, Date, DateTime, Float, Integer, JSON, Numeric, String, event, inspect
from sqlalchemy.orm import Session

from app.utils.entryparse import (
    InvalidFieldError, INVALID_NUMBER_KEY, INVALID_DATE_KEY, REQUIRED_FIELD_KEY,
    parse_amount, parse_optional_int, parse_currency_code, parse_iso_date,
)

INVALID_VALUE_KEY = 'validation.invalidValue'
# Includes UI options and documented legacy model values.
ENUMS = {
    'fuel_type': set('petrol gasoline regular premium diesel e85 lpg cng electric hybrid plugin_hybrid other'.split()),
    'distance_unit': {'km', 'miles', 'mi'},
    'transmission': {'manual', 'automatic', 'cvt', 'semi_automatic', 'other'},
    'drivetrain': {'fwd', 'rwd', 'awd', '4wd'},
    'severity': {'minor', 'moderate', 'major', 'critical', 'low', 'medium', 'high'},
    'tax_type': {'road_tax', 'registration', 'inspection', 'emissions', 'toll', 'insurance', 'other'},
    'tax_period': {'annual', 'semi_annual', 'quarterly', 'monthly', 'one_time'},
    'parking_type': {'street', 'garage', 'lot', 'permit', 'fine', 'hourly', 'daily', 'monthly', 'airport', 'other'},
    'fine_status': {'pending', 'paid', 'contested'},
    'policy_type': {'comprehensive', 'third_party', 'collision', 'liability', 'casco', 'rca', 'other'},
    'payment_frequency': {'monthly', 'quarterly', 'semi_annual', 'semi-annual', 'annual', 'yearly', 'one_time'},
    'recurrence_type': {'daily', 'weekly', 'monthly', 'quarterly', 'semi_annual', 'annual', 'yearly'},
    'priority': {'low', 'medium', 'high'},
    'frequency': {'daily', 'weekly', 'monthly', 'yearly'},
    'reminder_type': set('maintenance insurance inspection custom oil_change tire_rotation brake_inspection air_filter timing_belt mot_inspection road_tax service workshop_preparation'.split()),
}
REPAIR_TYPES = set('engine transmission brakes suspension electrical exhaust cooling fuel_system steering body interior ac_heating tires_wheels clutch drivetrain windshield lights oil_change filters battery turbo timing_belt differential other'.split())
REFUND_FIELDS = {'amount', 'total_price', 'price_per_liter', 'labor_cost', 'parts_cost', 'premium'}
POSITIVE_FIELDS = {'quantity', 'frequency_value', 'expected_lifespan_km', 'expected_lifespan_months', 'repeat_mileage'}
ALIASES = {
    'entry_date': 'date', 'mileage': 'odometer', 'volume': 'liters',
    'price_per_unit': 'price_per_liter', 'total_cost': 'amount', 'cost': 'amount',
    'is_full_tank': 'full_tank', 'station_name': 'station', 'station_location': 'station_address',
    'next_service_date': 'next_due_date', 'next_service_mileage': 'next_due_mileage',
    'warranty_until': 'warranty_expires', 'warranty_covered': 'under_warranty',
    'shop_name': 'garage_name', 'provider_name': 'provider', 'provider_location': 'garage_address',
    'provider_phone': 'garage_phone', 'location_name': 'location',
    'start_time': 'start_datetime', 'end_time': 'end_datetime',
    'is_recurring': 'recurring', 'recurrence_pattern': 'frequency',
    'recurrence_interval': 'frequency_value', 'notify_via_push': 'notify_push',
    'notify_via_email': 'notify_email', 'sync_to_calendar': 'calendar_sync',
}


def models():
    from app.models import (Vehicle, FuelEntry, ServiceEntry, RepairEntry, TaxEntry,
                            ParkingEntry, ConsumableEntry, InsurancePolicy, Reminder, Todo)
    return (Vehicle, FuelEntry, ServiceEntry, RepairEntry, TaxEntry, ParkingEntry,
            ConsumableEntry, InsurancePolicy, Reminder, Todo)


def _fail(field, key=INVALID_VALUE_KEY, message='Invalid value for this field'):
    raise InvalidFieldError(key, message, field)


def validate_field(model, field, value, *, exact=False):
    """Return a typed value using mapped storage limits and explicit domain rules."""
    column = inspect(model).columns.get(field)
    if column is None:
        return value
    typ = column.type
    if value is None:
        if not column.nullable and not column.primary_key:
            _fail(field, INVALID_NUMBER_KEY if isinstance(typ, Numeric) else REQUIRED_FIELD_KEY, 'This field cannot be empty')
        return None
    try:
        if isinstance(typ, Boolean):
            if not isinstance(value, bool):
                _fail(field)
        elif isinstance(typ, Integer):
            value = parse_optional_int(value)
            if value is None:
                return validate_field(model, field, None, exact=exact)
            # Archive-local identifiers may be negative in legacy backups.
            if not column.primary_key and not column.foreign_keys and field != 'display_order':
                if value < (1 if field in POSITIVE_FIELDS else 0):
                    _fail(field, INVALID_NUMBER_KEY, 'Value is outside the allowed range')
            if field in {'year', 'tax_year'} and not 1 <= value <= 9999:
                _fail(field, INVALID_NUMBER_KEY, 'Year must be between 1 and 9999')
            if field == 'repeat_mileage' and value > 2147483647:
                _fail(field, INVALID_NUMBER_KEY, 'Mileage interval exceeds the supported range')
            if field in {'city_driving_percentage', 'highway_driving_percentage', 'maintenance_score', 'health_score'} and value > 100:
                _fail(field, INVALID_NUMBER_KEY, 'Percentage must be between 0 and 100')
        elif isinstance(typ, Float):
            value = float(parse_amount(value))
            if not math.isfinite(value):
                _fail(field, INVALID_NUMBER_KEY)
        elif isinstance(typ, Numeric):
            if value == '' and not exact:
                return validate_field(model, field, None)
            value = parse_amount(value)
            limit = Decimal(10) ** (typ.precision - typ.scale)
            if abs(value) >= limit or (field not in REFUND_FIELDS and value < 0):
                _fail(field, INVALID_NUMBER_KEY, 'Value is outside the allowed range')
            rounded = value.quantize(Decimal(1).scaleb(-typ.scale), rounding=ROUND_HALF_UP)
            if abs(rounded) >= limit or (exact and rounded != value):
                _fail(field, INVALID_NUMBER_KEY, 'Value exceeds the stored precision')
            value = rounded
        elif isinstance(typ, DateTime):
            if not isinstance(value, datetime):
                value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        elif isinstance(typ, Date):
            if not isinstance(value, date):
                value = parse_iso_date(value)
        elif isinstance(typ, JSON):
            json.dumps(value, allow_nan=False)
            if field in {'service_types', 'repair_types'}:
                if not isinstance(value, list):
                    _fail(field)
                for item in value:
                    validate_field(model, field[:-1], item, exact=exact)
            if field == 'maintenance_intervals':
                from app.routes.vehicles import MAINTENANCE_INTERVALS
                if not isinstance(value, dict):
                    _fail(field)
                normalized = {}
                for key, interval in value.items():
                    parsed = parse_optional_int(interval)
                    if key not in MAINTENANCE_INTERVALS or parsed is None or not 0 < parsed <= 500000:
                        _fail(field, INVALID_NUMBER_KEY, 'Invalid maintenance interval')
                    normalized[key] = parsed
                if not exact:
                    value = normalized
        elif isinstance(typ, String):
            if field in ('currency', 'purchase_currency'):
                # Preserve the existing currency-specific error key even when
                # the submitted code exceeds the column length.
                normalized = parse_currency_code(value)
                if exact and normalized != value:
                    _fail(field, 'validation.invalidCurrency', 'Currency must use a recognized uppercase code')
                value = normalized
            if not isinstance(value, str) or (typ.length and len(value) > typ.length):
                _fail(field, 'validation.invalidText', 'Text is invalid or exceeds the field length')
            if not column.nullable and not value.strip():
                _fail(field, REQUIRED_FIELD_KEY, 'This field cannot be empty')
            options = ENUMS.get(field)
            if field == 'service_type':
                from app.models.service import VALID_SERVICE_TYPES
                options = VALID_SERVICE_TYPES
            elif field == 'repair_type':
                options = REPAIR_TYPES
            elif field == 'consumable_type':
                from app.models.consumable import CONSUMABLE_TYPES
                options = CONSUMABLE_TYPES
            elif field == 'status':
                options = ({'requested', 'confirmed', 'completed', 'cancelled'} if model.__tablename__ == 'appointments'
                           else {'paid', 'pending', 'overdue'} if model.__tablename__ == 'tax_entries' else {'active', 'expired', 'cancelled'})
            if options is not None and value not in options:
                if value == '' and column.nullable and not exact:
                    return None
                _fail(field, INVALID_VALUE_KEY, 'Value is not an allowed option')
    except InvalidFieldError as exc:
        exc.field = field
        raise
    except (ValueError, TypeError, AttributeError, InvalidOperation, OverflowError):
        _fail(field, INVALID_DATE_KEY if isinstance(typ, (Date, DateTime)) else INVALID_VALUE_KEY)
    return value


def validate_payload(model, data):
    """Validate aliases before route truthiness checks/coercions or DB queries.

    Normalize numeric values before SQL predicates and ad hoc route conversions.
    Dates retain the handlers' format/default contract. The mutation wrapper
    fingerprints the original payload before this function changes cached JSON.
    """
    if not isinstance(data, dict):
        _fail(None, INVALID_VALUE_KEY, 'Expected an object')
    columns = inspect(model).columns
    for key, value in data.items():
        field = ALIASES.get(key, key)
        if model.__tablename__ == 'vehicles' and key == 'mileage':
            field = 'current_mileage'
        if field not in columns:
            continue
        # Empty optional dates/currency retain the routes' existing defaults.
        if value in (None, '') and (isinstance(columns[field].type, (Date, DateTime)) or field == 'currency'):
            continue
        try:
            if key in {'start_time', 'end_time'} and isinstance(value, str) and len(value) == 5:
                try:
                    datetime.strptime(value, '%H:%M')
                except ValueError:
                    _fail(key, INVALID_DATE_KEY)
                continue
            parsed = validate_field(model, field, value)
            if not isinstance(columns[field].type, (Date, DateTime)):
                data[key] = parsed
        except InvalidFieldError as exc:
            exc.field = key
            raise


def validate_record(record):
    """Validate only supplied/changed columns, leaving historical data for the scan."""
    state = inspect(record)
    for attribute in state.mapper.column_attrs:
        if attribute.key in state.dict and (state.pending or state.transient or state.attrs[attribute.key].history.has_changes()):
            value = validate_field(type(record), attribute.key, state.dict[attribute.key])
            setattr(record, attribute.key, value)


@event.listens_for(Session, 'before_flush')
def _validate_mutation_flush(session, flush_context, instances):
    # Covers computed amounts and automatic related writes before any autoflush.
    # Backups use preflight exact validation instead, never rounding recovery data.
    if not has_request_context() or getattr(g, 'mutation_context', None) is None:
        return
    for record in session.new | session.dirty:
        if isinstance(record, models()):
            validate_record(record)

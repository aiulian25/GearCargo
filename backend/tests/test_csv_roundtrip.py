"""Tests for F57 — station_address survives a fuel CSV export→import round-trip.

The fuel column spec stored `station` but not `station_address`, so a CSV
round-trip silently dropped every station address. These tests lock the
lossless round-trip and confirm older CSVs without the column still import.
"""

import csv
import io
from datetime import date

from app import db
from app.models import Vehicle, FuelEntry
from app.services.csv_io import (
    columns_for, export_entries_csv, import_entries_csv,
)

TODAY = date.today()


def _mk_vehicle(user_id, name='Focus'):
    v = Vehicle(user_id=user_id, name=name, make='Ford', model='Focus')
    db.session.add(v)
    db.session.commit()
    db.session.refresh(v)
    return v


def test_station_address_in_fuel_columns():
    headers = [h for h, _, _ in columns_for('fuel')]
    assert 'station_address' in headers
    # It sits right after `station`, mirroring the model's field order.
    assert headers.index('station_address') == headers.index('station') + 1


def test_fuel_station_address_survives_roundtrip(app, user):
    with app.app_context():
        v = _mk_vehicle(user.id)
        vid = v.id
        db.session.add(FuelEntry(
            user_id=user.id, vehicle_id=vid, date=TODAY, amount=60,
            total_price=60, liters=40, fuel_type='petrol',
            station='Costco', station_address='12 Retail Park, Reading RG1 1AA'))
        db.session.commit()

        csv_text = export_entries_csv(user, 'fuel')

        # The address is present in the exported CSV cell.
        rows = list(csv.DictReader(io.StringIO(csv_text)))
        assert rows[0]['station_address'] == '12 Retail Park, Reading RG1 1AA'

        # Remove the original so the re-import isn't skipped as a merge duplicate
        # (per-instance delete — joined-table inheritance can't bulk-delete).
        for e in FuelEntry.query.filter_by(user_id=user.id).all():
            db.session.delete(e)
        db.session.commit()

        summary = import_entries_csv(user, 'fuel', csv_text)
        assert summary['created'] == 1
        assert summary['error_count'] == 0

        reimported = FuelEntry.query.filter_by(user_id=user.id).one()
        assert reimported.station == 'Costco'
        assert reimported.station_address == '12 Retail Park, Reading RG1 1AA'


def test_old_csv_without_station_address_still_imports(app, user):
    """A CSV pre-dating the new column (no station_address header) imports fine —
    unknown/missing columns are tolerated."""
    with app.app_context():
        v = _mk_vehicle(user.id)
        vid = v.id
        csv_text = (
            'vehicle_id,date,amount,station\n'
            f'{vid},{TODAY.isoformat()},55,Shell\n'
        )
        summary = import_entries_csv(user, 'fuel', csv_text)
        assert summary['created'] == 1
        assert summary['error_count'] == 0

        e = FuelEntry.query.filter_by(user_id=user.id).one()
        assert e.station == 'Shell'
        assert e.station_address is None


def test_csv_str_cells_are_injection_guarded(app, user):
    """station_address is a plain 'str' cell, so it inherits the same
    spreadsheet-formula-injection guard as every other text column."""
    with app.app_context():
        v = _mk_vehicle(user.id)
        vid = v.id
        db.session.add(FuelEntry(
            user_id=user.id, vehicle_id=vid, date=TODAY, amount=60,
            total_price=60, liters=40, station='X',
            station_address='=SUM(A1:A9)'))
        db.session.commit()

        csv_text = export_entries_csv(user, 'fuel')
        rows = list(csv.DictReader(io.StringIO(csv_text)))
        # A leading '=' must not be emitted raw (it would execute in Excel).
        assert not rows[0]['station_address'].startswith('=')

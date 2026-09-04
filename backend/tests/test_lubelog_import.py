"""Regression tests for R4-14: the LubeLogger importer attached an insurance
policy whose own vehicle was not in the backup to an ARBITRARY vehicle
(`next(iter(vehicle_id_map.values()))`), corrupting that vehicle's costs.

This is the A2 defect already fixed in the ZIP importer
(`routes/backup.py:2147-2156`); the LubeLogger path kept the fallback.

The fixture builds real BSON bytes inside a real ZIP, so the whole pipeline runs
— scan_bson_documents -> classify_documents -> map_to_gearcargo -> the import
loop — rather than a stub of it.
"""

import io
import struct
import zipfile
from datetime import datetime, timezone

import pytest

from app import db
from app.models import InsurancePolicy, User, Vehicle
from app.services.lubelog_import import import_lubelog_to_gearcargo


# ── minimal BSON writer (only the types LubeLogger records use) ──────────────

def _cstring(name):
    return name.encode('utf-8') + b'\x00'


def _element(doc_type, name, payload):
    return bytes([doc_type]) + _cstring(name) + payload


def _bson(document):
    body = b''
    for name, value in document.items():
        if isinstance(value, bool):
            body += _element(0x08, name, b'\x01' if value else b'\x00')
        elif isinstance(value, int):
            body += _element(0x10, name, struct.pack('<i', value))
        elif isinstance(value, float):
            body += _element(0x01, name, struct.pack('<d', value))
        elif isinstance(value, datetime):
            millis = int(value.replace(tzinfo=timezone.utc).timestamp() * 1000)
            body += _element(0x09, name, struct.pack('<q', millis))
        else:
            encoded = str(value).encode('utf-8') + b'\x00'
            body += _element(0x02, name, struct.pack('<i', len(encoded)) + encoded)
    return struct.pack('<i', len(body) + 5) + body + b'\x00'


def _lubelog_zip(documents):
    database = b''.join(_bson(document) for document in documents)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('data/cartracker.db', database)
    buffer.seek(0)
    return buffer


VEHICLE_ONE = {
    '_id': 1, 'Make': 'VW', 'Model': 'Golf', 'Year': 2019, 'LicensePlate': 'AB12CDE',
}


def _insurance_record(record_id, vehicle_id, description='Car Insurance premium'):
    """A LubeLogger taxrecord that map_to_gearcargo turns into a policy."""
    return {
        '_id': record_id, 'VehicleId': vehicle_id, 'Description': description,
        'Cost': 120.0, 'IsRecurring': True, 'RecurringInterval': 'OneMonth',
        'Date': datetime(2026, 3, 1),
    }


def _make_user(email='lubelog@example.com'):
    user = User(username=email.split('@')[0], email=email, is_active=True)
    user.set_password('StrongPass123!')
    db.session.add(user)
    db.session.commit()
    return user


def test_a_record_for_a_missing_vehicle_is_dropped_and_counted(app):
    """The backup describes vehicle 1, but the record belongs to vehicle 2 —
    which is not in the file.

    map_to_gearcargo drops it (correctly — inventing a vehicle would be worse),
    but it used to do so SILENTLY: the user saw "import completed" while part of
    their history was discarded. It is now counted and reported.
    """
    with app.app_context():
        user = _make_user()
        archive = _lubelog_zip([VEHICLE_ONE, _insurance_record(10, vehicle_id=2)])

        result = import_lubelog_to_gearcargo(user, archive, merge_mode='merge',
                                             distance_unit='km')

        assert result.get('error') is None, result
        imported = result['imported']
        assert imported['vehicles'] == 1
        assert imported['insurance_policies'] == 0
        assert imported['skipped_unmatched_records'] == 1     # was: uncounted
        # Nothing was pinned onto the wrong car.
        assert InsurancePolicy.query.count() == 0


def test_an_orphaned_policy_is_never_pinned_to_an_arbitrary_vehicle(app, monkeypatch):
    """The import loop's own guard.

    Reaching it through a real archive is not possible — map_to_gearcargo already
    drops records for unknown vehicles — so the mapping stage is stubbed to hand
    the loop exactly the state the old fallback mishandled. The guard is
    defensive, but the behaviour it replaces (attach to an ARBITRARY vehicle,
    corrupting that vehicle's costs) is bad enough to keep pinned.
    """
    import app.services.lubelog_import as lubelog

    def _orphaned_policy(classified, config=None, distance_unit=None):
        return {
            'version': '2.0', 'source': 'lubelog', 'reminders': [], 'todos': [],
            'attachments': [], 'skipped_unmatched_records': 0,
            'vehicles': [{
                'lubelog_id': 1, 'name': 'Golf', 'make': 'VW', 'model': 'Golf',
                'fuel_entries': [], 'service_entries': [], 'repair_entries': [],
                'tax_entries': [], 'parking_entries': [],
            }],
            'insurance_policies': [{
                'vehicle_lubelog_id': 99,          # not in `vehicles` above
                'provider': 'Orphan Insurance', 'premium': 100.0,
                'payment_frequency': 'monthly',
                'start_date': '2026-01-01', 'end_date': '2026-12-31',
                'status': 'active',
            }],
        }

    monkeypatch.setattr(lubelog, 'map_to_gearcargo', _orphaned_policy)

    with app.app_context():
        user = _make_user('orphan@example.com')
        archive = _lubelog_zip([VEHICLE_ONE])

        result = import_lubelog_to_gearcargo(user, archive, merge_mode='merge',
                                             distance_unit='km')

        imported = result['imported']
        assert imported['insurance_policies'] == 0
        assert imported['skipped_unmatched_policies'] == 1
        assert InsurancePolicy.query.count() == 0          # was: attached to the Golf


def test_a_policy_for_a_known_vehicle_still_imports(app):
    """The skip must not cost the normal case."""
    with app.app_context():
        user = _make_user('match@example.com')
        archive = _lubelog_zip([VEHICLE_ONE, _insurance_record(11, vehicle_id=1)])

        result = import_lubelog_to_gearcargo(user, archive, merge_mode='merge',
                                             distance_unit='km')

        imported = result['imported']
        assert imported['insurance_policies'] == 1
        assert imported['skipped_unmatched_policies'] == 0
        assert imported['skipped_unmatched_records'] == 0

        policy = InsurancePolicy.query.one()
        vehicle = Vehicle.query.one()
        assert policy.vehicle_id == vehicle.id
        assert policy.user_id == user.id


def test_the_counter_is_always_reported(app):
    """The key must exist even when nothing was skipped, so the client can read
    it without guarding for absence."""
    with app.app_context():
        user = _make_user('counter@example.com')
        archive = _lubelog_zip([VEHICLE_ONE])

        result = import_lubelog_to_gearcargo(user, archive, merge_mode='merge',
                                             distance_unit='km')

        assert result['imported']['skipped_unmatched_policies'] == 0
        assert result['imported']['skipped_unmatched_records'] == 0


# ---------------------------------------------------------------------------
# R4-37 — the guesser emitted `battery`, `filter_change` and `suspension`, none
# of which are valid service types. Rows imported under them were invisible to
# the vehicle-health component map (`vehicles.py:3367`), which only knows the
# twelve values in VALID_SERVICE_TYPES, and would be filtered out by the
# create/update routes if the same value were ever submitted through the API.
# ---------------------------------------------------------------------------

from app.models.service import VALID_SERVICE_TYPES
from app.services.lubelog_import import _guess_service_type


@pytest.mark.parametrize('description', [
    'Oil and filter change',
    'Brake pads and discs',
    'Front disk replacement',
    'Tyre rotation',
    'New tires fitted',
    'Battery replacement',
    'MOT test',
    'Air filter change',
    'Cabin filter',
    'Full service',
    'Annual service',
    'Suspension overhaul',
    'Paint correction',
    '',
    None,
])
def test_every_guessed_type_is_a_valid_service_type(description):
    assert _guess_service_type(description) in VALID_SERVICE_TYPES


@pytest.mark.parametrize('description, expected', [
    ('Oil and filter change', 'oil_change'),      # 'oil' wins over 'filter'
    ('Brake pads', 'brake_service'),
    ('Tyre rotation', 'tire_rotation'),
    ('Battery replacement', 'other'),             # was: 'battery'
    ('MOT test', 'inspection'),
    ('Air filter change', 'air_filter'),          # was: 'filter_change'
    ('Full service', 'full_service'),
    ('Suspension overhaul', 'other'),             # was: 'suspension'
    ('Paint correction', 'other'),
])
def test_the_guesser_still_classifies_the_same_way(description, expected):
    assert _guess_service_type(description) == expected


@pytest.mark.parametrize('description, guessed', [
    ('Something else entirely', 'tire_rotation'),        # 'tire' inside 'entirely'
    ('Remote central locking repair', 'inspection'),     # 'mot' inside 'remote'
])
def test_known_substring_looseness_of_the_guesser(description, guessed):
    """Pinned, not fixed: the guesser matches bare substrings, so unrelated
    words trip its branches. Out of scope for R4-37, which is about the guesser
    emitting values outside VALID_SERVICE_TYPES — these are all valid types,
    just the wrong ones. Flagged for the Step 38 hygiene sweep."""
    assert _guess_service_type(description) == guessed
    assert _guess_service_type(description) in VALID_SERVICE_TYPES


def test_the_route_and_the_importer_share_one_allow_list():
    """Two copies used to drift; the route now imports the model's set."""
    from app.routes import services as services_route

    assert services_route.VALID_SERVICE_TYPES is VALID_SERVICE_TYPES


def test_every_valid_service_type_is_known_to_the_health_map():
    """A type the guesser can emit must be resolvable by the health endpoint."""
    import inspect

    from app.routes import vehicles as vehicles_route

    source = inspect.getsource(vehicles_route)
    mapped_block = source.split('SERVICE_TYPE_TO_COMPONENTS = {', 1)[1].split('}', 1)[0]

    for service_type in VALID_SERVICE_TYPES:
        assert f"'{service_type}'" in mapped_block, (
            f'{service_type} has no entry in SERVICE_TYPE_TO_COMPONENTS')


def test_battery_rows_still_reach_the_health_check_by_keyword():
    """Why mapping 'battery' to 'other' loses nothing.

    'battery' was never a service type, so SERVICE_TYPE_TO_COMPONENTS never
    matched it either — the component signal has always come from the keyword
    fallback on title/notes, and the importer sets `title` from the LubeLog
    description (`lubelog_import.py:806`). That path is unaffected.
    """
    import inspect

    from app.routes import vehicles as vehicles_route

    source = inspect.getsource(vehicles_route)
    keyword_block = source.split('SERVICE_KEYWORDS = {', 1)[1].split('\n    }', 1)[0]

    assert "'battery': [" in keyword_block
    battery_keywords = keyword_block.split("'battery': [", 1)[1].split(']', 1)[0]
    assert "'battery'" in battery_keywords

    # And the guesser puts nothing in the way of that match.
    assert _guess_service_type('Battery replacement') == 'other'

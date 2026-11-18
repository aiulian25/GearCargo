"""The migration that removes the prediction structures runs on a database that holds real rows."""
import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

MIGRATION_FILE = Path(__file__).parents[1] / 'migrations/versions/remove_ai_features.py'
UNREACHABLE_REDIS = 'redis://127.0.0.1:1/0'
PREVIOUS_SCHEMA = (
    'CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, email_smart_alerts BOOLEAN)',
    'CREATE TABLE vehicles (id INTEGER PRIMARY KEY, name TEXT, prediction_accuracy_score FLOAT, last_prediction_at DATETIME)',
    'CREATE TABLE fuel_entries (id INTEGER PRIMARY KEY, liters NUMERIC, ocr_populated BOOLEAN)',
    'CREATE TABLE prediction_alerts (id INTEGER PRIMARY KEY, vehicle_id INTEGER NOT NULL, user_id INTEGER, alert_type TEXT NOT NULL)',
    'CREATE INDEX ix_prediction_alerts_vehicle_id ON prediction_alerts (vehicle_id)',
    'CREATE TABLE notification_logs (id INTEGER PRIMARY KEY, notification_type TEXT NOT NULL, title TEXT, reminder_id INTEGER, '
    'prediction_id INTEGER REFERENCES prediction_alerts (id))',
    'CREATE TABLE appointment_tasks (id INTEGER PRIMARY KEY, title TEXT NOT NULL, todo_id INTEGER, source_signature TEXT, '
    'prediction_id INTEGER REFERENCES prediction_alerts (id) ON DELETE SET NULL)',
    'CREATE TABLE due_dismissals (id INTEGER PRIMARY KEY, kind TEXT NOT NULL, ref_id INTEGER NOT NULL)',
    'CREATE TABLE import_identities (id INTEGER PRIMARY KEY, entity_kind TEXT NOT NULL)',
    'CREATE TABLE scheduled_effects (id INTEGER PRIMARY KEY, job_name TEXT NOT NULL)',
    'CREATE TABLE scheduled_job_runs (job_name TEXT PRIMARY KEY)',
    'CREATE TABLE activity_logs (id INTEGER PRIMARY KEY, event_type TEXT NOT NULL)',
    'CREATE TABLE app_settings ("key" TEXT PRIMARY KEY, value TEXT)',
)
PREVIOUS_ROWS = (
    "INSERT INTO users VALUES (1, 'owner@example.invalid', 1)",
    "INSERT INTO vehicles VALUES (1, 'Car', 0.8, '2026-11-01 03:00:00')",
    'INSERT INTO fuel_entries VALUES (1, 40, 0)',
    "INSERT INTO prediction_alerts VALUES (1, 1, 1, 'oil_change')",
    "INSERT INTO notification_logs VALUES (1, 'reminder', 'Insurance due', 5, NULL), (2, 'ai_prediction', 'Brakes', NULL, 1), "
    "(3, 'fuel_anomaly', 'Fuel', NULL, NULL), (4, 'mileage_prediction', 'Oil', NULL, NULL)",
    "INSERT INTO appointment_tasks VALUES (1, 'Replace the belt', NULL, 'signed-for-a-prediction', 1), "
    "(2, 'Check the tyres', 7, 'signed-for-a-todo', NULL)",
    "INSERT INTO due_dismissals VALUES (1, 'prediction', 1), (2, 'todo', 7)",
    "INSERT INTO import_identities VALUES (1, 'predictions'), (2, 'vehicles')",
    "INSERT INTO scheduled_effects VALUES (1, 'check_predictions'), (2, 'check_reminders')",
    "INSERT INTO scheduled_job_runs VALUES ('check_predictions'), ('ollama_probe'), ('check_reminders')",
    "INSERT INTO activity_logs VALUES (1, 'ai_settings_updated'), (2, 'ai_cache_flushed'), (3, 'login')",
    "INSERT INTO app_settings VALUES ('ollama_model_predict', 'some-model'), ('chat_classifier_enabled', 'true'), "
    "('restore_marker', 'personal')",
)


@pytest.fixture()
def migration():
    spec = importlib.util.spec_from_file_location('retired_structures_migration', MIGRATION_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def connection(monkeypatch):
    monkeypatch.delenv('REDIS_URL', raising=False)
    engine = create_engine('sqlite://')
    with engine.begin() as open_connection:
        for statement in (*PREVIOUS_SCHEMA, *PREVIOUS_ROWS):
            open_connection.execute(text(statement))
        yield open_connection
    engine.dispose()


def column(connection, statement):
    return connection.execute(text(statement)).scalars().all()


def columns_of(connection, table):
    return {item['name'] for item in inspect(connection).get_columns(table)}


def test_upgrade_removes_generated_data_and_keeps_what_people_entered(migration, connection):
    with Operations.context(MigrationContext.configure(connection)):
        migration.upgrade()

    assert 'prediction_alerts' not in inspect(connection).get_table_names()
    assert column(connection, 'SELECT title FROM notification_logs') == ['Insurance due']
    assert column(connection, 'SELECT kind FROM due_dismissals') == ['todo']
    assert column(connection, 'SELECT entity_kind FROM import_identities') == ['vehicles']
    assert column(connection, 'SELECT job_name FROM scheduled_effects') == ['check_reminders']
    assert column(connection, 'SELECT job_name FROM scheduled_job_runs') == ['check_reminders']
    assert column(connection, 'SELECT event_type FROM activity_logs') == ['login']
    assert column(connection, 'SELECT "key" FROM app_settings') == ['restore_marker']
    assert column(connection, 'SELECT name FROM vehicles') == ['Car']
    assert column(connection, 'SELECT email FROM users') == ['owner@example.invalid']
    assert column(connection, 'SELECT liters FROM fuel_entries') == [40]


def test_upgrade_drops_every_column_it_names(migration, connection):
    with Operations.context(MigrationContext.configure(connection)):
        migration.upgrade()

    for table, dropped in migration.DROPPED_COLUMNS:
        assert dropped not in columns_of(connection, table), (table, dropped)


def test_task_made_from_a_prediction_stays_as_a_plain_task(migration, connection):
    with Operations.context(MigrationContext.configure(connection)):
        migration.upgrade()

    tasks = connection.execute(text('SELECT title, todo_id, source_signature FROM appointment_tasks ORDER BY id')).all()
    assert [tuple(task) for task in tasks] == [('Replace the belt', None, None), ('Check the tyres', 7, 'signed-for-a-todo')]


def test_downgrade_restores_empty_structures(migration, connection):
    with Operations.context(MigrationContext.configure(connection)):
        migration.upgrade()
        migration.downgrade()

    assert column(connection, 'SELECT count(*) FROM prediction_alerts') == [0]
    for table, restored in migration.DROPPED_COLUMNS:
        assert restored in columns_of(connection, table), (table, restored)
    assert column(connection, 'SELECT name FROM vehicles') == ['Car']


def test_unreachable_cache_does_not_stop_the_upgrade(migration, connection, monkeypatch):
    monkeypatch.setenv('REDIS_URL', UNREACHABLE_REDIS)

    with Operations.context(MigrationContext.configure(connection)):
        migration.upgrade()

    assert 'prediction_alerts' not in inspect(connection).get_table_names()

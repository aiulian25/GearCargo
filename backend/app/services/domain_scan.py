"""Read-only inventory of records needing review under the current write rules."""
import json

import click
from flask import Flask
from sqlalchemy import Boolean, JSON, inspect, literal_column, select

from app import db
from app.services.domain_validation import models, validate_field
from app.utils.entryparse import InvalidFieldError


def scan_records():
    report = {'version': 1, 'read_only': True, 'scanned': 0, 'issues': [], 'schema_gaps': []}
    # Raw rows avoid Numeric/date result processors crashing on historical bad
    # SQLite values. Identifiers come exclusively from application mappings.
    with db.engine.connect() as connection:
        catalog = inspect(connection)
        for model in models():
            mapper = inspect(model)
            missing_tables = [table.name for table in mapper.tables if not catalog.has_table(table.name)]
            if missing_tables:
                report['schema_gaps'].append({'model': model.__tablename__, 'missing_tables': missing_tables})
                continue
            available = {table.name: {c['name'] for c in catalog.get_columns(table.name)} for table in mapper.tables}
            columns = []
            for attribute in mapper.column_attrs:
                column = attribute.columns[0]
                if column.name in available[column.table.name]:
                    columns.append(column)
                else:
                    report['schema_gaps'].append({'model': model.__tablename__, 'missing_column': attribute.key})
            quote = connection.dialect.identifier_preparer.quote
            statement = select(*(literal_column(
                f'{quote(c.table.name)}.{quote(c.name)}').label(c.key)
                for c in columns)).select_from(mapper.persist_selectable)
            for row in connection.execute(statement).mappings():
                report['scanned'] += 1
                for column in columns:
                    value = row[column.key]
                    try:
                        # Decode native DB representations, never fix source data.
                        if isinstance(column.type, Boolean) and type(value) is int and value in (0, 1):
                            value = bool(value)
                        if isinstance(column.type, JSON) and isinstance(value, str):
                            value = json.loads(value)
                        if column.key in {'currency', 'distance_unit'} and value is None:
                            raise InvalidFieldError('validation.required', 'Unknown value; review source before assigning', column.key)
                        validate_field(model, column.key, value, exact=True)
                    except (InvalidFieldError, ValueError, TypeError) as exc:
                        report['issues'].append({
                            'table': model.__tablename__, 'id': row['id'],
                            'field': column.key,
                            'message_key': getattr(exc, 'message_key', 'validation.invalidValue'),
                            'reason': getattr(exc, 'error', 'Invalid stored representation'),
                            'action': 'Review the preserved source and correct explicitly; no automatic repair performed.',
                        })
    report['issue_count'] = len(report['issues'])
    return report


def register_domain_scan(app):
    @app.cli.command('validate-records')
    @click.option('--output', type=click.File('w'), default='-', help='JSON report destination; defaults to stdout.')
    def validate_records(output):
        """Report invalid business records without changing database values."""
        json.dump(scan_records(), output, indent=2)
        output.write('\n')


def create_scan_app(database_uri=None):
    """CLI-only factory: never run recovery, schedulers, OCR or admin creation."""
    from app import _with_psycopg2_driver
    from app.config import Config

    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = _with_psycopg2_driver(
        database_uri or Config.SQLALCHEMY_DATABASE_URI)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    register_domain_scan(app)
    return app

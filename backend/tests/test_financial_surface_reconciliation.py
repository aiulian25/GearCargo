"""GC-019: independent financial surfaces must agree on the declared basis."""
from datetime import date, timedelta
import pytest
from app import db
from app.models import User, Vehicle, ConsumableEntry
from app.utils.timeutils import utc_today


def test_consumable_is_in_report(app, client, user, auth_headers):
    with app.app_context():
        v = Vehicle(user_id=user.id, name='Ledger fixture')
        db.session.add(v)
        db.session.flush()
        db.session.add(ConsumableEntry(user_id=user.id, vehicle_id=v.id,
            date=utc_today(), amount=80, currency='GBP', title='Tyres'))
        db.session.commit()
        vid = v.id
    response = client.post('/api/reports/preview', headers=auth_headers(user.id),
        json={'vehicle_ids': [vid], 'period': 'current_month'})
    assert response.status_code == 200
    assert response.json['entry_counts']['total'] == 1
    assert response.json['totals']['grand_total'] == 80


@pytest.fixture
def fixed_clock(monkeypatch):
    from datetime import datetime, timezone
    from app.routes import vehicles, insurance
    from app.utils import timeutils
    from app.services import expense_ledger, expense_views, pdf_report_service, currency
    today = date(2025, 3, 31)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2025, 3, 31, 12, tzinfo=timezone.utc if tz else None)
    for module in (vehicles, pdf_report_service):
        monkeypatch.setattr(module, 'datetime', Clock)
    for module in (vehicles, insurance, expense_ledger, expense_views, timeutils):
        monkeypatch.setattr(module, 'utc_today', lambda: today)
    for module in (vehicles, currency):
        monkeypatch.setattr(module, 'get_rates_cached', lambda app: {'GBP': .8, 'USD': 2})
    return today


def test_all_surfaces_reconcile(app, client, user, auth_headers, fixed_clock):
    from app.models import FuelEntry, ServiceEntry, RepairEntry, TaxEntry, ParkingEntry, InsurancePolicy
    from app.services.pdf_report_service import get_vehicle_entries, generate_pdf_report, generate_shared_pdf_report
    from app.services.shared_report import SharedReport
    from app.routes.reports import _report_summary
    from pypdf import PdfReader
    from pathlib import Path
    import os
    with app.app_context():
        owner = db.session.get(User, user.id)
        owner.currency = 'GBP'
        v = Vehicle(user_id=user.id, name='Golden ledger', distance_unit='miles',
                    purchase_price=1000, purchase_currency='USD')
        db.session.add(v)
        db.session.flush()
        for model, amount, ccy, extra in [
            (FuelEntry, 20, 'USD', {'total_price': 20, 'odometer': 100}),
            (ServiceEntry, 10, 'EUR', {'odometer': 110}),
            (RepairEntry, 30, 'GBP', {'description': 'PART_123'}), (TaxEntry, 40, 'GBP', {}),
            (ParkingEntry, 50, 'GBP', {}), (ConsumableEntry, 80, 'GBP', {})]:
            db.session.add(model(user_id=user.id, vehicle_id=v.id, date=date(2025, 3, 1),
                                 amount=amount, currency=ccy, **extra))
        for premium, currency, frequency, start, end, status in [
            (10, 'GBP', 'monthly', date(2024, 12, 31), date(2025, 12, 31), 'active'),
            (50, 'USD', 'quarterly', date(2024, 12, 15), date(2025, 12, 14), 'active'),
            (25, 'EUR', 'one_time', date(2025, 2, 1), date(2025, 12, 31), 'active'),
            (5, 'GBP', 'monthly', date(2025, 1, 5), date(2025, 2, 5), 'cancelled'),
            (7, 'GBP', 'annual', date(2024, 12, 1), date(2024, 12, 31), 'expired')]:
            db.session.add(InsurancePolicy(user_id=user.id, vehicle_id=v.id, provider='Fixture',
                premium=premium, currency=currency, payment_frequency=frequency,
                start_date=start, end_date=end, status=status))
        # Future recorded work is excluded from every non-forecast total.
        db.session.add(ServiceEntry(user_id=user.id, vehicle_id=v.id, date=date(2025, 4, 1), amount=999, currency='GBP'))
        db.session.commit()
        vid = v.id
        summary = _report_summary(owner, [v], 'year', 2025, None)
        pdf_rows = get_vehicle_entries(v, date(2025, 1, 1), date(2025, 12, 31), 'GBP', {'GBP': .8, 'USD': 2})
        private = generate_pdf_report(owner, [v], 'year', year=2025)
        shared = SharedReport.from_summary(summary, label='Golden ledger', app_name='GearCargo', expires_at=None)
        public = generate_shared_pdf_report(shared)
        assert pdf_rows['repair'][0]['description'] == 'PART_123'
        assert pdf_rows['totals']['grand_total'] == summary['totals']['grand_total'] == 296
        assert summary['entry_counts']['total'] == 13
        assert summary['end_date'] == '2025-03-31'
        assert summary['recorded_total'] == 216 and summary['insurance_estimate'] == 80
        for name, buffer in [('private', private), ('public', public)]:
            text = '\n'.join(page.extract_text() for page in PdfReader(buffer).pages)
            assert '296.00' in text and 'Consumables' in text and '80.00' in text
            assert 'scheduled insurance estimates' in text.lower()
            if os.environ.get('GC_PUBLIC_PDF_OUTPUT_DIR'):
                folder = Path(os.environ['GC_PUBLIC_PDF_OUTPUT_DIR'])
                folder.mkdir(parents=True, exist_ok=True)
                (folder / f'gc019-{name}.pdf').write_bytes(buffer.getvalue())
    def get(path):
        response = client.get(path, headers=auth_headers(user.id))
        assert response.status_code == 200, response.json
        return response.json
    stats = get(f'/api/vehicles/{vid}/stats')
    analytics = get(f'/api/vehicles/{vid}/cost-analytics')
    expenses = get(f'/api/vehicles/{vid}/expenses-summary?year=2025')
    fleet = get('/api/vehicles/summary')
    insurance = get('/api/insurance/stats')
    assert stats['total_costs'] == analytics['total_cost'] == fleet['total_cost'] == 333
    assert stats['ytd_spent'] == expenses['totals']['grand_total'] == 296
    assert stats['costs_this_month'] == 246
    assert stats['insurance_costs'] == insurance['ytd_scheduled_estimate'] == 80
    assert [row['total'] for row in expenses['monthly']] == [15, 35, 246]
    assert [row['cost'] for row in analytics['series'][-3:]] == [15, 35, 246]
    assert analytics['distance_unit'] == 'miles' and analytics['total_distance'] == 10
    assert analytics['cost_per_distance_lifetime'] == 33.3
    assert analytics['ownership']['purchase_price_display'] == 400
    assert analytics['ownership']['total_with_purchase'] == 733
    assert stats['insurance_annual_cost'] == insurance['active_annualized_premium'] == 220
    assert all(data['basis'] == summary['basis'] for data in (stats, analytics, expenses, fleet))


@pytest.mark.parametrize('frequency, expected', [
    ('monthly', ['2025-01-31', '2025-02-28', '2025-03-31']),
    ('quarterly', ['2025-03-31']), ('semi_annual', []), ('semi-annual', []),
    ('annual', []), ('yearly', []), ('one_time', []),
])
def test_schedule_month_end_and_prior_year(frequency, expected):
    from types import SimpleNamespace
    from app.services.expense_ledger import scheduled_dates
    policy = SimpleNamespace(start_date=date(2024, 12, 31), end_date=date(2025, 12, 31), payment_frequency=frequency)
    assert [d.isoformat() for d in scheduled_dates(policy, date(2025, 1, 1), date(2025, 3, 31))] == expected


@pytest.mark.parametrize('rates', [{}, {'JPY': 0}, {'JPY': -1}, {'JPY': float('inf')}, {'JPY': float('nan')}])
def test_missing_fx_is_excluded_not_mixed(rates, fixed_clock):
    from app.services.expense_ledger import Expense, aggregate
    rows = [Expense(fixed_clock, 'fuel', 10, 'GBP', None),
            Expense(fixed_clock, 'consumable', 5000, 'JPY', None),
            Expense(fixed_clock, 'insurance', 0, 'USD', None)]
    result = aggregate(rows, 'GBP', rates)
    assert result['totals']['grand_total'] == 10
    assert result['unconverted'] == {'JPY': 5000}
    assert result['entry_counts']['total'] == 3 and result['converted'] is False
    zero = aggregate(rows[2:], 'GBP', {})
    assert zero['converted'] is True and zero['fx_applied'] is False


def test_unknown_purchase_requires_review_and_known_currency_survives_preference(app, client, user, auth_headers, fixed_clock):
    with app.app_context():
        legacy = Vehicle(user_id=user.id, name='Legacy', purchase_price=1000)
        db.session.add(legacy)
        db.session.commit()
        legacy_id = legacy.id
    result = client.get(f'/api/vehicles/{legacy_id}/cost-analytics', headers=auth_headers(user.id)).json
    assert result['ownership']['purchase_currency_review_required'] is True
    assert result['ownership']['total_with_purchase'] is None
    created = client.post('/api/vehicles', headers=auth_headers(user.id), json={'name': 'New', 'purchase_price': 1000})
    assert created.status_code == 201
    vid = created.json['vehicle']['id']
    assert created.json['vehicle']['purchase_currency'] == 'GBP'
    with app.app_context():
        db.session.get(User, user.id).currency = 'USD'
        db.session.commit()
    changed = client.get(f'/api/vehicles/{vid}/cost-analytics', headers=auth_headers(user.id)).json
    assert changed['ownership']['purchase_currency'] == 'GBP'
    assert changed['ownership']['purchase_price'] == 1000
    assert changed['ownership']['purchase_price_display'] == 2500
    reviewed = client.put(f'/api/vehicles/{legacy_id}', headers=auth_headers(user.id), json={'purchase_currency': 'eur'})
    assert reviewed.status_code == 200 and reviewed.json['vehicle']['purchase_currency'] == 'EUR'
    invalid = client.put(f'/api/vehicles/{legacy_id}', headers=auth_headers(user.id), json={'purchase_currency': 'XYZ'})
    assert invalid.status_code == 400


def test_backup_purchase_currency_and_old_version_review(app, user):
    from copy import deepcopy
    from app.services.backup_schema import export_user_data, prepare_backup
    from app.services.import_identity import same_source
    with app.app_context():
        owner = db.session.get(User, user.id)
        db.session.add(Vehicle(user_id=user.id, name='Purchase', purchase_price=20, purchase_currency='RON'))
        db.session.commit()
        backup = export_user_data(owner)
        assert backup['version'] == '4.4'
        assert backup['vehicles'][0]['purchase_currency'] == 'RON'
        assert prepare_backup(backup).records['vehicles'][0]['purchase_currency'] == 'RON'
        old = deepcopy(backup)
        old['version'] = '4.2'
        del old['vehicles'][0]['purchase_currency']
        assert prepare_backup(old).records['vehicles'][0]['purchase_currency'] is None
        assert same_source({'name': 'Legacy'}, {'name': 'Legacy', 'purchase_currency': None})
        assert not same_source({'name': 'Legacy'}, {'name': 'Legacy', 'purchase_currency': 'GBP'})


def test_partial_totals_reconcile_and_distance_is_unavailable(app, client, user, auth_headers, fixed_clock):
    from app.models import FuelEntry
    from app.routes.reports import _report_summary
    from app.services.pdf_report_service import get_vehicle_entries
    with app.app_context():
        v = Vehicle(user_id=user.id, name='Missing FX', distance_unit='km', purchase_price=10, purchase_currency='JPY')
        db.session.add(v)
        db.session.flush()
        db.session.add_all([
            FuelEntry(user_id=user.id, vehicle_id=v.id, date=fixed_clock, amount=10,
                      total_price=10, currency='GBP', odometer=100),
            ConsumableEntry(user_id=user.id, vehicle_id=v.id, date=fixed_clock, amount=5000,
                            currency='JPY', odometer=200),
        ])
        db.session.commit()
        vid = v.id
        report = _report_summary(db.session.get(User, user.id), [v], 'year', 2025, None)
        rows = get_vehicle_entries(v, date(2025, 1, 1), fixed_clock, 'GBP', {'GBP': .8, 'USD': 2})
        assert rows['consumable'][0]['amount'] is None
        assert rows['totals']['grand_total'] == report['totals']['grand_total'] == 10
        assert not report['converted'] and report['unconverted'] == {'JPY': 5000}
    stats = client.get(f'/api/vehicles/{vid}/stats', headers=auth_headers(user.id)).json
    analytics = client.get(f'/api/vehicles/{vid}/cost-analytics', headers=auth_headers(user.id)).json
    fleet = client.get('/api/vehicles/summary', headers=auth_headers(user.id)).json
    assert stats['total_costs'] == analytics['total_cost'] == fleet['total_cost'] == 10
    assert all(body['converted'] is False for body in (stats, analytics, fleet))
    assert analytics['cost_per_distance_lifetime'] is None
    assert analytics['ownership']['total_with_purchase'] is None
    assert analytics['ownership']['purchase_converted'] is False
    assert analytics['forecast'] is None


def test_year_summary_is_owner_scoped_and_validates_year(app, client, user, auth_headers):
    with app.app_context():
        other = User(username='other-ledger', email='other-ledger@example.invalid')
        other.set_password('FixturePassword123!')
        db.session.add(other)
        db.session.flush()
        foreign = Vehicle(user_id=other.id, name='Other')
        own = Vehicle(user_id=user.id, name='Own')
        db.session.add_all([foreign, own])
        db.session.commit()
        foreign_id, own_id = foreign.id, own.id
    assert client.get(f'/api/vehicles/{foreign_id}/expenses-summary', headers=auth_headers(user.id)).status_code == 404
    for year in ['0', '10000', 'not-a-year']:
        assert client.get(f'/api/vehicles/{own_id}/expenses-summary?year={year}', headers=auth_headers(user.id)).status_code == 400


def test_unset_display_currency_uses_same_default_in_reports(app, client, user, auth_headers, fixed_clock):
    from app.services.pdf_report_service import generate_pdf_report
    from pypdf import PdfReader
    with app.app_context():
        owner = db.session.get(User, user.id)
        owner.currency = None
        v = Vehicle(user_id=user.id, name='Default currency')
        db.session.add(v)
        db.session.flush()
        db.session.add(ConsumableEntry(user_id=user.id, vehicle_id=v.id, date=fixed_clock, amount=80, currency='GBP'))
        db.session.commit()
        vid = v.id
        pdf = generate_pdf_report(owner, [v], 'year', year=2025)
        text = '\n'.join(page.extract_text() for page in PdfReader(pdf).pages)
        assert '80.00 GBP' in text
    preview = client.post('/api/reports/preview', headers=auth_headers(user.id),
                          json={'vehicle_ids': [vid], 'period': 'year', 'year': 2025}).json
    fleet = client.get('/api/vehicles/summary', headers=auth_headers(user.id)).json
    assert preview['display_currency'] == fleet['display_currency'] == 'GBP'
    assert preview['totals']['grand_total'] == fleet['total_cost'] == 80


def test_purchase_currency_migration_preserves_unknown_history():
    import importlib.util
    from pathlib import Path
    from sqlalchemy import create_engine, inspect, text
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    path = Path(__file__).parents[1] / 'migrations/versions/gc019_purchase_currency.py'
    spec = importlib.util.spec_from_file_location('gc019_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE vehicles (id INTEGER PRIMARY KEY, purchase_price NUMERIC(12,2))'))
        connection.execute(text('INSERT INTO vehicles (id, purchase_price) VALUES (1, 1234.56), (2, 0), (3, NULL)'))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        assert connection.execute(text('SELECT purchase_currency FROM vehicles')).scalars().all() == [None, None, None]
        assert float(connection.execute(text('SELECT purchase_price FROM vehicles WHERE id=1')).scalar()) == 1234.56
        assert next(c for c in inspect(connection).get_columns('vehicles') if c['name'] == 'purchase_currency')['nullable']
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
        assert 'purchase_currency' not in {c['name'] for c in inspect(connection).get_columns('vehicles')}
    engine.dispose()


def test_insurance_stats_preserves_policy_owner_scope_for_legacy_links(app, client, user, auth_headers, fixed_clock):
    from app.models import InsurancePolicy
    with app.app_context():
        other = User(username='legacy-policy-owner', email='legacy-policy@example.invalid')
        other.set_password('FixturePassword123!')
        db.session.add(other)
        db.session.flush()
        vehicle = Vehicle(user_id=other.id, name='Foreign vehicle')
        db.session.add(vehicle)
        db.session.flush()
        # Legacy cross-owner links are not accepted by current write routes.
        # The new period total must preserve the existing policy-owner filter.
        for uid, amount in [(user.id, 10), (other.id, 900)]:
            db.session.add(InsurancePolicy(user_id=uid, vehicle_id=vehicle.id, provider='Fixture',
                premium=amount, currency='GBP', payment_frequency='one_time', status='active',
                start_date=fixed_clock, end_date=date(2025, 12, 31)))
        db.session.commit()
    response = client.get('/api/insurance/stats', headers=auth_headers(user.id))
    assert response.status_code == 200
    assert response.json['total_policies'] == 1
    assert response.json['ytd_scheduled_estimate'] == response.json['active_annualized_premium'] == 10

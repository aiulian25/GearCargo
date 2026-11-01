"""GC-020: complete aggregates and independently bounded, filtered detail pages."""
from datetime import date

import pytest
from sqlalchemy import event

from app import db
from app.models import (User, Vehicle, FuelEntry, ServiceEntry, RepairEntry, TaxEntry,
                        ParkingEntry, ConsumableEntry, InsurancePolicy, Reminder, Todo, Attachment)

MODELS = dict(fuel=FuelEntry, service=ServiceEntry, repair=RepairEntry, tax=TaxEntry,
              parking=ParkingEntry, consumable=ConsumableEntry)


@pytest.fixture(autouse=True)
def clock_and_rates(monkeypatch):
    from app.routes import vehicles
    from app.services import expense_views, expense_ledger, currency
    for module in (vehicles, expense_views, expense_ledger):
        monkeypatch.setattr(module, 'utc_today', lambda: date(2025, 3, 31))
    for module in (vehicles, currency):
        monkeypatch.setattr(module, 'get_rates_cached', lambda app: {'GBP': .8, 'USD': 2})


def vehicle(user, name='History'):
    v = Vehicle(user_id=user.id, name=name)
    db.session.add(v)
    db.session.flush()
    return v


def entry(user, v, category, when=date(2024, 1, 31), amount=10, currency='GBP', **extra):
    if category == 'fuel':
        extra['total_price'] = amount
    row = MODELS[category](user_id=user.id, vehicle_id=v.id, date=when,
                           amount=amount, currency=currency, **extra)
    db.session.add(row)
    return row


def policy(user, v, start, end, frequency='monthly', currency='GBP', premium=10):
    row = InsurancePolicy(user_id=user.id, vehicle_id=v.id, provider='Fixture',
        start_date=start, end_date=end, payment_frequency=frequency, currency=currency,
        premium=premium, status='expired')
    db.session.add(row)
    return row


def test_large_mixed_history_pages_reconcile_with_summary_and_report(client, user, auth_headers):
    v = vehicle(user)
    ids = {category: [] for category in [*MODELS, 'insurance']}
    for category in MODELS:
        for index in range(121):  # Exceeds 20/50/100-record defaults, with tied dates.
            row = entry(user, v, category, currency=['GBP', 'EUR', 'USD'][index % 3])
            db.session.flush()
            ids[category].append(row.id)
        entry(user, v, category, date(2020, 1, 1), amount=7)
        entry(user, v, category, date(2024, 2, 1), amount=3)
        entry(user, v, category, date(2025, 4, 1), amount=999)
    for index in range(121):
        row = policy(user, v, date(2024, 1, 31), date(2024, 12, 31),
                     currency=['GBP', 'EUR', 'USD'][index % 3])
        db.session.flush()
        ids['insurance'].append(row.id)
    db.session.commit()
    headers = auth_headers(user.id)
    base = f'/api/vehicles/{v.id}'

    def get(path, **params):
        response = client.get(base + path, headers=headers, query_string=params)
        assert response.status_code == 200, response.json
        return response.json

    summary = get('/expenses-summary', year=2024)
    assert summary['available_years'] == [2025, 2024, 2020]
    assert summary['available_months'] == list(range(1, 13))
    assert summary['totals']['grand_total'] == 16038  # 6 × (890 + 3) + 12 × 890
    assert summary['converted'] and summary['fx_applied']
    january = get('/expenses-summary', year=2024, month=1)
    assert january['totals']['grand_total'] == 6230  # 7 × 890
    for category in ids:
        all_ids, subtotal = [], 0
        for page in range(1, 8):
            data = get('/expense-records', category=category, year=2024, month=1, page=page)
            assert data['total'] == 121 and data['pages'] == 7
            assert len(data['records']) == (20 if page < 7 else 1)
            assert data['display_currency'] == 'GBP'
            assert data['start_date'] == '2024-01-01' and data['end_date'] == '2024-01-31'
            all_ids.extend(row['id'] for row in data['records'])
            subtotal += data['page_total']
            assert all(row['currency'] in ('GBP', 'USD', 'EUR') for row in data['records'])
            assert all(row['premium' if category == 'insurance' else 'amount'] == 10 for row in data['records'])
        assert all_ids == list(reversed(ids[category]))
        assert subtotal == january['totals'][category] == 890
    report = client.post('/api/reports/preview', headers=headers,
        json={'vehicle_ids': [v.id], 'period': 'year', 'year': 2024})
    assert report.status_code == 200
    assert report.json['totals'] == summary['totals']
    assert sum(row['total'] for row in summary['monthly']) == report.json['totals']['grand_total']
    assert get('/expenses-summary', year=2020)['totals']['grand_total'] == 42
    assert get('/expense-records', category='fuel', year=2024, month=2)['total'] == 1
    assert get('/expense-records', category='fuel', year=2025)['total'] == 0
    # Public category-list contracts retain their original default page sizes.
    for route, size in [('fuel', 20), ('services', 20), ('repairs', 20), ('taxes', 20), ('parking', 20), ('consumables', 50)]:
        response = client.get(f'/api/{route}', headers=headers, query_string={'vehicle_id': v.id})
        assert response.status_code == 200, response.json
        assert len(response.json['entries']) == size


def test_insurance_only_year_options_and_period_policy_estimates(client, user, auth_headers):
    v = vehicle(user)
    policy(user, v, date(2018, 12, 31), date(2020, 12, 31))
    policy(user, v, date(2015, 1, 1), date(2024, 12, 31), 'one_time', premium=70)
    policy(user, v, date(2024, 12, 31), date(2025, 12, 31), 'quarterly', 'USD', 50)
    db.session.commit()
    headers = auth_headers(user.id)
    base = f'/api/vehicles/{v.id}'
    summary = client.get(base + '/expenses-summary?year=2020', headers=headers).json
    assert summary['available_years'] == [2025, 2024, 2020, 2019, 2018, 2015]
    assert summary['totals']['insurance'] == summary['totals']['grand_total'] == 120
    page = client.get(base + '/expense-records?category=insurance&year=2020', headers=headers).json
    assert page['total'] == 2  # Two policies cover the year, only one has scheduled costs.
    assert sorted(row['period_amount'] for row in page['records']) == [0, 120]
    assert sorted(row['period_occurrences'] for row in page['records']) == [0, 12]
    assert page['page_total'] == summary['totals']['insurance']
    march = client.get(base + '/expense-records?category=insurance&year=2025&month=3', headers=headers).json
    assert march['page_total'] == 20 and march['records'][0]['period_occurrences'] == 1
    future = client.get(base + '/expense-records?category=insurance&year=2025&month=4', headers=headers).json
    assert future['records'] == [] and future['page_total'] == 0


def test_detail_queries_stay_bounded_and_preserve_attachments(app, client, user, auth_headers):
    v = vehicle(user)
    for index in range(121):
        row = entry(user, v, 'fuel')
        db.session.flush()
        db.session.add(Attachment(user_id=user.id, vehicle_id=v.id, entry_id=row.id,
            filename=f'{index}.jpg', filepath=f'/unused/{index}.jpg'))
    db.session.commit()
    headers = auth_headers(user.id)
    queries = []
    def capture(conn, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith('SELECT'):
            queries.append(statement)
    counts = []
    with app.app_context():
        event.listen(db.engine, 'before_cursor_execute', capture)
        try:
            for size in (20, 100):
                queries.clear()
                response = client.get(f'/api/vehicles/{v.id}/expense-records?year=2024&per_page={size}', headers=headers)
                assert response.status_code == 200
                assert len(response.json['records']) == size
                assert all(len(row['attachments']) == 1 for row in response.json['records'])
                counts.append(len(queries))
        finally:
            event.remove(db.engine, 'before_cursor_execute', capture)
    assert max(counts) <= 12 and abs(counts[1] - counts[0]) <= 1


def test_missing_rates_are_disclosed_on_page_and_summary(client, user, auth_headers):
    v = vehicle(user)
    entry(user, v, 'fuel', amount=5000, currency='JPY')
    entry(user, v, 'fuel', amount=10)
    db.session.commit()
    headers = auth_headers(user.id)
    base = f'/api/vehicles/{v.id}'
    page = client.get(base + '/expense-records?year=2024', headers=headers).json
    summary = client.get(base + '/expenses-summary?year=2024', headers=headers).json
    assert page['page_total'] == summary['totals']['grand_total'] == 10
    assert page['converted'] is False and page['unconverted'] == {'JPY': 5000}
    assert next(row for row in page['records'] if row['currency'] == 'JPY')['period_amount'] is None


def test_all_date_tasks_and_outstanding_fines_are_vehicle_scoped(client, user, auth_headers):
    own, other = vehicle(user), vehicle(user, 'Another vehicle')
    for v in (own, other):
        for index in range(121):
            db.session.add(Todo(user_id=user.id, vehicle_id=v.id, title=f'Todo {index}'))
            db.session.add(Reminder(user_id=user.id, vehicle_id=v.id, title=f'Reminder {index}', due_date=date(2020, 1, 1)))
        for status in ('pending', 'contested', 'paid'):
            entry(user, v, 'parking', date(2020, 1, 1), parking_type='fine', fine_status=status, currency='EUR')
    db.session.commit()
    headers = auth_headers(user.id)
    base = f'/api/vehicles/{own.id}/expense-records'
    for category in ('todo', 'reminder'):
        response = client.get(base, headers=headers, query_string={'category': category, 'year': 2024, 'month': 3, 'page': 7})
        assert response.status_code == 200, response.json
        data = response.json
        assert data['total'] == 121 and len(data['records']) == 1
        assert data['records'][0]['vehicle_id'] == own.id
        assert data['scope'] == 'all_dates' and data['start_date'] is None and data['page_total'] is None
    fines = client.get(base + '?category=parking&scope=outstanding&year=2024', headers=headers).json
    assert fines['total'] == 2 and fines['page_total'] == 16
    assert {row['fine_status'] for row in fines['records']} == {'pending', 'contested'}
    assert all(row['date'] == '2020-01-01' for row in fines['records'])


def test_invalid_filters_empty_pages_and_foreign_vehicle(client, user, auth_headers):
    own = vehicle(user)
    foreign_user = User(username='foreign-pages', email='foreign-pages@example.invalid')
    foreign_user.set_password('FixturePassword123!')
    db.session.add(foreign_user)
    db.session.flush()
    foreign = vehicle(foreign_user)
    db.session.commit()
    headers = auth_headers(user.id)
    base = f'/api/vehicles/{own.id}/expense-records'
    for query in ('year=0', 'year=10000', 'year=abc', 'month=0', 'month=13', 'month=no',
                  'category=unknown', 'page=0', 'page=-1', 'page=abc', 'page=999999999999999999999', 'per_page=0',
                  'per_page=101', 'scope=unknown', 'category=fuel&scope=outstanding'):
        assert client.get(base + '?' + query, headers=headers).status_code == 400, query
    for query in ('year=0', 'year=10000', 'month=13', 'month=no'):
        assert client.get(f'/api/vehicles/{own.id}/expenses-summary?' + query, headers=headers).status_code == 400
    empty = client.get(base + '?page=999', headers=headers).json
    assert empty['records'] == [] and empty['pages'] == 0 and empty['current_page'] == 999
    for vid in (foreign.id, 999999):
        assert client.get(f'/api/vehicles/{vid}/expense-records', headers=headers).status_code == 404

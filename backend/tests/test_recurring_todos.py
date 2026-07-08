"""Tests for F15 — recurring todos (parity with reminders)."""

from datetime import date, timedelta

from app import db
from app.models import User, Vehicle
from app.models.todo import Todo


def _mk_vehicle(user_id):
    v = Vehicle(user_id=user_id, name='Focus', make='Ford', model='Focus')
    db.session.add(v)
    db.session.commit()
    db.session.refresh(v)
    return v


def _create(client, auth_headers, user_id, **body):
    return client.post('/api/todos', headers=auth_headers(user_id), json=body)


def test_weekly_recurring_todo_spawns_one_successor(app, client, user, auth_headers):
    due = date.today()
    with app.app_context():
        v = _mk_vehicle(user.id)
        vid = v.id

    created = _create(client, auth_headers, user.id, vehicle_id=vid,
                      title='Tyre pressure check', due_date=due.isoformat(),
                      recurring=True, frequency='weekly').get_json()['todo']
    assert created['recurring'] is True
    assert created['frequency'] == 'weekly'

    resp = client.post(f"/api/todos/{created['id']}/complete", headers=auth_headers(user.id))
    body = resp.get_json()
    assert body['todo']['completed'] is True
    # Exactly one successor, 7 days out, not completed.
    assert 'next_todo' in body
    assert body['next_todo']['due_date'] == (due + timedelta(days=7)).isoformat()
    assert body['next_todo']['completed'] is False
    assert body['next_todo']['recurring'] is True

    with app.app_context():
        assert Todo.query.filter_by(vehicle_id=vid).count() == 2  # original + successor


def test_monthly_recurring_advances_one_month(app, client, user, auth_headers):
    from dateutil.relativedelta import relativedelta
    due = date.today()
    with app.app_context():
        v = _mk_vehicle(user.id)
        vid = v.id
    tid = _create(client, auth_headers, user.id, vehicle_id=vid, title='Wash',
                  due_date=due.isoformat(), recurring=True, frequency='monthly').get_json()['todo']['id']
    body = client.post(f'/api/todos/{tid}/complete', headers=auth_headers(user.id)).get_json()
    assert body['next_todo']['due_date'] == (due + relativedelta(months=1)).isoformat()


def test_non_recurring_todo_is_terminal(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        vid = v.id
    tid = _create(client, auth_headers, user.id, vehicle_id=vid, title='One-off',
                  due_date=date.today().isoformat()).get_json()['todo']['id']
    body = client.post(f'/api/todos/{tid}/complete', headers=auth_headers(user.id)).get_json()
    assert 'next_todo' not in body
    with app.app_context():
        assert Todo.query.filter_by(vehicle_id=vid).count() == 1  # no successor


def test_recurring_without_due_date_does_not_spawn(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        vid = v.id
    # Recurring but no due_date → nothing to advance from → terminal.
    tid = _create(client, auth_headers, user.id, vehicle_id=vid, title='No date',
                  recurring=True, frequency='weekly').get_json()['todo']['id']
    body = client.post(f'/api/todos/{tid}/complete', headers=auth_headers(user.id)).get_json()
    assert 'next_todo' not in body
    with app.app_context():
        assert Todo.query.filter_by(vehicle_id=vid).count() == 1

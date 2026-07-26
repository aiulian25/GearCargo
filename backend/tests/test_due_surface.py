"""Tests for F4 — unified "Due & Expiring" surface (GET /api/due)."""

from datetime import date, timedelta

from app import db
from app.models import (
    User, Vehicle, Reminder, ServiceEntry, TaxEntry, InsurancePolicy,
    Attachment, ParkingEntry, ConsumableEntry,
)

TODAY = date.today()


def _mk_vehicle(user_id, name='Focus', mileage=0, archived=False):
    v = Vehicle(user_id=user_id, name=name, make='Ford', model='Focus',
                current_mileage=mileage, archived=archived)
    db.session.add(v)
    db.session.commit()
    db.session.refresh(v)
    return v


def _seed_one_of_each(user_id, vehicle_id):
    """Seed a due/expiring record of every kind (all within the 30-day window)."""
    db.session.add(Reminder(
        user_id=user_id, vehicle_id=vehicle_id, title='Oil change',
        due_date=TODAY + timedelta(days=3), reminder_type='maintenance'))
    db.session.add(ServiceEntry(
        user_id=user_id, vehicle_id=vehicle_id, date=TODAY, amount=0,
        service_type='oil', next_due_date=TODAY + timedelta(days=10)))
    db.session.add(TaxEntry(
        user_id=user_id, vehicle_id=vehicle_id, date=TODAY, amount=0,
        tax_type='road_tax', next_due_date=TODAY + timedelta(days=15)))
    db.session.add(InsurancePolicy(
        user_id=user_id, vehicle_id=vehicle_id, provider='Acme',
        premium=500, status='active',
        start_date=TODAY - timedelta(days=340), end_date=TODAY + timedelta(days=20)))
    db.session.add(Attachment(
        user_id=user_id, vehicle_id=vehicle_id, filename='mot.pdf',
        filepath='/x/mot.pdf', original_filename='MOT.pdf',
        expires_at=TODAY + timedelta(days=25)))
    db.session.add(ParkingEntry(
        user_id=user_id, vehicle_id=vehicle_id, date=TODAY, amount=0,
        parking_type='permit', location='Downtown',
        permit_expires=TODAY + timedelta(days=12)))
    # Consumable worn to 100% → 'replace' (mileage-based).
    db.session.add(ConsumableEntry(
        user_id=user_id, vehicle_id=vehicle_id, date=TODAY, amount=0,
        consumable_type='tire', install_odometer=0, odometer=0,
        expected_lifespan_km=1000))
    db.session.commit()


def test_requires_auth(client):
    assert client.get('/api/due').status_code == 401


def test_merges_all_sources(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id, 'Golf', mileage=1000)  # 100% wear on the tire
        _seed_one_of_each(user.id, v.id)

    # Explicit 30-day window — _seed_one_of_each spans up to +25 days, wider than
    # the fixture user's default alert_days_before horizon (F53).
    resp = client.get('/api/due?days=30', headers=auth_headers(user.id))
    assert resp.status_code == 200
    body = resp.get_json()
    kinds = {it['kind'] for it in body['items']}
    assert kinds == {'reminder', 'service', 'tax', 'insurance', 'document',
                     'parking', 'consumable'}
    assert body['count'] == len(body['items']) == 7
    # Every item deep-links and is labelled.
    for it in body['items']:
        assert it['link'] and it['link'].startswith('/')
        assert it['title']
        assert it['severity'] in ('critical', 'warning', 'info')


def test_overdue_reminder_sorts_above_future_insurance(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id, 'Golf')
        db.session.add(Reminder(
            user_id=user.id, vehicle_id=v.id, title='Overdue inspection',
            due_date=TODAY - timedelta(days=5), reminder_type='inspection'))
        db.session.add(InsurancePolicy(
            user_id=user.id, vehicle_id=v.id, provider='Acme', premium=500,
            status='active', start_date=TODAY - timedelta(days=340),
            end_date=TODAY + timedelta(days=20)))
        db.session.commit()

    # Insurance ends in 20 days — wider than the default alert_days_before
    # horizon (F53), so pin an explicit 30-day window for the sort assertion.
    items = client.get('/api/due?days=30', headers=auth_headers(user.id)).get_json()['items']
    assert items[0]['kind'] == 'reminder'
    assert items[0]['severity'] == 'critical'
    assert items[0]['days_left'] == -5
    assert items[1]['kind'] == 'insurance'
    assert items[1]['severity'] == 'info'  # 20 days out


def test_empty_fleet_returns_empty(app, client, user, auth_headers):
    resp = client.get('/api/due', headers=auth_headers(user.id))
    assert resp.status_code == 200
    assert resp.get_json() == {'items': [], 'count': 0}


def test_days_horizon_excludes_far_future(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id, 'Golf')
        db.session.add(Reminder(
            user_id=user.id, vehicle_id=v.id, title='Far reminder',
            due_date=TODAY + timedelta(days=200), reminder_type='maintenance'))
        db.session.commit()

    # Default 30-day window hides it…
    assert client.get('/api/due', headers=auth_headers(user.id)).get_json()['count'] == 0
    # …a wider window surfaces it.
    body = client.get('/api/due?days=365', headers=auth_headers(user.id)).get_json()
    assert body['count'] == 1
    assert body['items'][0]['kind'] == 'reminder'


def test_archived_vehicle_entries_excluded(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id, 'Archived', mileage=1000, archived=True)
        db.session.add(ServiceEntry(
            user_id=user.id, vehicle_id=v.id, date=TODAY, amount=0,
            service_type='oil', next_due_date=TODAY + timedelta(days=5)))
        db.session.commit()

    # Service on an archived vehicle must not surface.
    assert client.get('/api/due', headers=auth_headers(user.id)).get_json()['count'] == 0


def test_duplicates_collapse_to_most_urgent(app, client, user, auth_headers):
    """F39: same kind+vehicle+title collapses to ONE row (most urgent) with a count."""
    with app.app_context():
        v = _mk_vehicle(user.id, 'Golf')
        for days_ago in (30, 20, 10):  # three overdue MOT reminders
            db.session.add(Reminder(
                user_id=user.id, vehicle_id=v.id, title='MOT',
                due_date=TODAY - timedelta(days=days_ago), reminder_type='inspection'))
        db.session.commit()

    body = client.get('/api/due', headers=auth_headers(user.id)).get_json()
    assert body['count'] == 1
    item = body['items'][0]
    assert item['title'] == 'MOT'
    assert item['count'] == 3
    # The surviving row is the MOST urgent occurrence (furthest overdue).
    assert item['days_left'] == -30
    assert item['severity'] == 'critical'


def test_duplicates_not_merged_across_vehicles_or_kinds(app, client, user, auth_headers):
    with app.app_context():
        v1 = _mk_vehicle(user.id, 'Golf')
        v2 = _mk_vehicle(user.id, 'Qashqai')
        # Same title on two different vehicles → two rows.
        for vid in (v1.id, v2.id):
            db.session.add(Reminder(
                user_id=user.id, vehicle_id=vid, title='MOT',
                due_date=TODAY + timedelta(days=2), reminder_type='inspection'))
        # Same title, different kind (tax vs reminder) on v1 → separate row.
        db.session.add(TaxEntry(
            user_id=user.id, vehicle_id=v1.id, date=TODAY, amount=0,
            tax_type='road_tax', title='MOT', next_due_date=TODAY + timedelta(days=2)))
        db.session.commit()

    items = client.get('/api/due', headers=auth_headers(user.id)).get_json()['items']
    assert len(items) == 3
    assert all(it['count'] == 1 for it in items)


def test_ownership_isolation(app, client, user, auth_headers):
    with app.app_context():
        other = User(email='other@example.com', username='other', is_active=True)
        other.set_password('Str0ng!Passw0rd')
        db.session.add(other)
        db.session.commit()
        ov = _mk_vehicle(other.id, 'Theirs')
        db.session.add(Reminder(
            user_id=other.id, vehicle_id=ov.id, title='Their reminder',
            due_date=TODAY + timedelta(days=2), reminder_type='maintenance'))
        db.session.commit()

    # The requesting user sees none of the other user's due items.
    assert client.get('/api/due', headers=auth_headers(user.id)).get_json()['count'] == 0


# --- F52: snooze silences the feed (and, via the shared clause, push + email) --

def _due_kinds(client, user, auth_headers, days=30):
    resp = client.get(f'/api/due?days={days}', headers=auth_headers(user.id))
    return [it['title'] for it in resp.get_json()['items']]


def test_snoozed_reminder_hidden_then_reappears(app, client, user, auth_headers):
    from datetime import datetime, timezone
    with app.app_context():
        v = _mk_vehicle(user.id)
        r = Reminder(user_id=user.id, vehicle_id=v.id, title='Snoozed MOT',
                     due_date=TODAY + timedelta(days=3), reminder_type='inspection',
                     snoozed_until=datetime.now(timezone.utc) + timedelta(days=5))
        db.session.add(r)
        db.session.commit()
        rid = r.id

    # Snoozed → absent from Coming up.
    assert 'Snoozed MOT' not in _due_kinds(client, user, auth_headers)

    # Snooze window elapsed (back-date it) → reappears.
    with app.app_context():
        r = db.session.get(Reminder, rid)
        r.snoozed_until = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.session.commit()
    assert 'Snoozed MOT' in _due_kinds(client, user, auth_headers)


def test_never_snoozed_reminder_still_shows(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id)
        db.session.add(Reminder(user_id=user.id, vehicle_id=v.id, title='Plain',
                                due_date=TODAY + timedelta(days=2),
                                reminder_type='maintenance'))  # snoozed_until NULL
        db.session.commit()
    assert 'Plain' in _due_kinds(client, user, auth_headers)


def test_check_due_reminders_skips_snoozed(app, user, monkeypatch):
    """The hourly push job must not fire for a snoozed reminder."""
    from datetime import datetime, timezone
    import app.routes.push as push_mod
    from app.services import check_due_reminders

    pushed = []
    monkeypatch.setattr(push_mod, 'send_push_to_user',
                        lambda *a, **k: pushed.append(1) or 1)

    with app.app_context():
        v = _mk_vehicle(user.id)
        # Overdue but snoozed 3 days out → must stay silent.
        db.session.add(Reminder(
            user_id=user.id, vehicle_id=v.id, title='Overdue-but-snoozed',
            due_date=TODAY - timedelta(days=1), reminder_type='inspection',
            notify_push=True,
            snoozed_until=datetime.now(timezone.utc) + timedelta(days=3)))
        db.session.commit()

    check_due_reminders(app)
    assert pushed == []


# --- F53: default horizon follows the user's alert_days_before ----------------

def test_default_horizon_follows_alert_days_before(app, client, user, auth_headers):
    with app.app_context():
        u = db.session.get(User, user.id)
        u.alert_days_before = 7
        db.session.commit()
        v = _mk_vehicle(user.id)
        # Due in 10 days — inside 30, outside the user's 7-day horizon.
        db.session.add(Reminder(user_id=user.id, vehicle_id=v.id, title='In10',
                                due_date=TODAY + timedelta(days=10),
                                reminder_type='maintenance'))
        db.session.commit()

    # No ?days → follows alert_days_before=7 → In10 absent.
    default = client.get('/api/due', headers=auth_headers(user.id)).get_json()
    assert 'In10' not in [it['title'] for it in default['items']]

    # Explicit ?days=30 overrides → In10 present.
    wide = client.get('/api/due?days=30', headers=auth_headers(user.id)).get_json()
    assert 'In10' in [it['title'] for it in wide['items']]


def test_build_due_items_none_days_uses_pref_else_30(app, user):
    from app.services.due import build_due_items
    with app.app_context():
        u = db.session.get(User, user.id)
        u.alert_days_before = None       # unset → falls back to 30
        db.session.commit()
        v = _mk_vehicle(user.id)
        db.session.add(Reminder(user_id=user.id, vehicle_id=v.id, title='In25',
                                due_date=TODAY + timedelta(days=25),
                                reminder_type='maintenance'))
        db.session.commit()
        # days=None with no pref → 30-day fallback includes the 25-day item.
        titles = [i['title'] for i in build_due_items(user.id)]
        assert 'In25' in titles


# --- F44: todos in the Coming up feed ----------------------------------------

def test_todo_with_due_date_appears_and_dismisses(app, client, user, auth_headers):
    from app.models import Todo
    with app.app_context():
        v = _mk_vehicle(user.id)
        t = Todo(user_id=user.id, vehicle_id=v.id, title='Buy roof rack',
                 due_date=TODAY + timedelta(days=3), completed=False)
        db.session.add(t)
        # A standalone (no-vehicle) todo also surfaces.
        db.session.add(Todo(user_id=user.id, title='Renew club membership',
                            due_date=TODAY + timedelta(days=2), completed=False))
        # Completed / date-less todos never appear.
        db.session.add(Todo(user_id=user.id, title='Done thing',
                            due_date=TODAY, completed=True))
        db.session.add(Todo(user_id=user.id, title='No date', completed=False))
        db.session.commit()
        tid = t.id

    items = client.get('/api/due?days=30', headers=auth_headers(user.id)).get_json()['items']
    todo_items = [it for it in items if it['kind'] == 'todo']
    titles = {it['title'] for it in todo_items}
    assert 'Buy roof rack' in titles
    assert 'Renew club membership' in titles
    assert 'Done thing' not in titles and 'No date' not in titles
    # Vehicle-bound todo deep-links to its todo tab.
    roof = next(it for it in todo_items if it['title'] == 'Buy roof rack')
    assert roof['link'].endswith('/expenses?tab=todo')

    # Dismiss the vehicle todo → gone from the feed (occurrence-scoped).
    resp = client.post('/api/due/dismiss', json={'kind': 'todo', 'ref_id': tid},
                       headers=auth_headers(user.id))
    assert resp.status_code == 200
    after = client.get('/api/due?days=30', headers=auth_headers(user.id)).get_json()['items']
    assert 'Buy roof rack' not in {it['title'] for it in after}

    # Undo restores it.
    client.post('/api/due/undismiss', json={'kind': 'todo', 'ref_id': tid},
                headers=auth_headers(user.id))
    restored = client.get('/api/due?days=30', headers=auth_headers(user.id)).get_json()['items']
    assert 'Buy roof rack' in {it['title'] for it in restored}


def test_todo_dismiss_ownership_enforced(app, client, user, auth_headers):
    from app.models import Todo
    with app.app_context():
        other = User(email='other-todo@example.com', username='othertodo', is_active=True)
        other.set_password('Str0ng!Passw0rd')
        db.session.add(other)
        db.session.commit()
        ot = Todo(user_id=other.id, title='Their todo',
                  due_date=TODAY + timedelta(days=1), completed=False)
        db.session.add(ot)
        db.session.commit()
        otid = ot.id

    # Dismissing another user's todo → 404, nothing stored.
    resp = client.post('/api/due/dismiss', json={'kind': 'todo', 'ref_id': otid},
                       headers=auth_headers(user.id))
    assert resp.status_code == 404


# --- F45: AI predictions in the Coming up feed --------------------------------

def _mk_prediction(user_id, vehicle_id, **kw):
    from app.models import PredictionAlert
    kw.setdefault('alert_type', 'service')
    kw.setdefault('title', 'Brake pads wearing')
    kw.setdefault('urgency', 'medium')
    kw.setdefault('dismissed', False)
    kw.setdefault('actioned', False)
    p = PredictionAlert(user_id=user_id, vehicle_id=vehicle_id, **kw)
    db.session.add(p)
    db.session.commit()
    return p


def test_high_urgency_prediction_appears(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id, mileage=50000)
        _mk_prediction(user.id, v.id, title='Timing belt due', urgency='high')
        # A low-urgency prediction with a far-off mileage must NOT appear.
        _mk_prediction(user.id, v.id, title='Distant thing', urgency='low',
                       predicted_mileage=80000)
        db.session.commit()

    items = client.get('/api/due?days=30', headers=auth_headers(user.id)).get_json()['items']
    preds = [it for it in items if it['kind'] == 'prediction']
    titles = {it['title'] for it in preds}
    assert 'Timing belt due' in titles
    assert 'Distant thing' not in titles
    belt = next(it for it in preds if it['title'] == 'Timing belt due')
    assert belt['severity'] == 'critical'
    assert belt['link'].endswith('/alerts')


def test_near_mileage_prediction_appears_with_distance_left(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id, mileage=59600)
        # Predicted at 60,000; current 59,600 → within 1,000 → surfaces.
        _mk_prediction(user.id, v.id, title='Oil change soon', urgency='medium',
                       predicted_mileage=60000)
        db.session.commit()

    items = client.get('/api/due?days=30', headers=auth_headers(user.id)).get_json()['items']
    oil = next(it for it in items if it['kind'] == 'prediction')
    assert oil['distance_left'] == 400
    assert oil['distance_unit'] == 'km'
    assert oil['severity'] == 'warning'          # not passed yet


def test_prediction_mileage_passed_is_critical(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id, mileage=61000)
        _mk_prediction(user.id, v.id, title='Overdue service', urgency='medium',
                       predicted_mileage=60000)
        db.session.commit()

    it = next(x for x in client.get('/api/due?days=30', headers=auth_headers(user.id))
              .get_json()['items'] if x['kind'] == 'prediction')
    assert it['severity'] == 'critical'
    assert it['distance_left'] == 0              # floored


def test_dismissed_or_actioned_predictions_excluded(app, client, user, auth_headers):
    with app.app_context():
        v = _mk_vehicle(user.id, mileage=50000)
        _mk_prediction(user.id, v.id, title='Dismissed', urgency='high', dismissed=True)
        _mk_prediction(user.id, v.id, title='Actioned', urgency='high', actioned=True)
        db.session.commit()

    items = client.get('/api/due?days=30', headers=auth_headers(user.id)).get_json()['items']
    assert not any(it['kind'] == 'prediction' for it in items)


def test_prediction_dismiss_flips_native_flag(app, client, user, auth_headers):
    from app.models import PredictionAlert
    with app.app_context():
        v = _mk_vehicle(user.id, mileage=50000)
        p = _mk_prediction(user.id, v.id, title='Flip me', urgency='high')
        pid = p.id

    resp = client.post('/api/due/dismiss', json={'kind': 'prediction', 'ref_id': pid},
                       headers=auth_headers(user.id))
    assert resp.status_code == 200
    with app.app_context():
        p = db.session.get(PredictionAlert, pid)
        assert p.dismissed is True and p.dismissed_at is not None
        # No DueDismissal row for a native-flag kind.
        from app.models import DueDismissal
        assert DueDismissal.query.filter_by(kind='prediction', ref_id=pid).count() == 0

    # Undo flips it back.
    client.post('/api/due/undismiss', json={'kind': 'prediction', 'ref_id': pid},
                headers=auth_headers(user.id))
    with app.app_context():
        p = db.session.get(PredictionAlert, pid)
        assert p.dismissed is False and p.dismissed_at is None

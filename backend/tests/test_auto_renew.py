"""Tests for F6 — honoring InsurancePolicy.auto_renew."""

from datetime import date, timedelta

from app import db
from app.models import User, Vehicle, InsurancePolicy
from app.services import process_auto_renew_insurance


def _mk_user(email, username):
    u = User(email=email, username=username, is_active=True)
    u.set_password('Str0ng!Passw0rd')
    db.session.add(u)
    db.session.commit()
    return u


def _mk_vehicle(user_id, name='Focus'):
    v = Vehicle(user_id=user_id, name=name, make='Ford', model='Focus')
    db.session.add(v)
    db.session.commit()
    db.session.refresh(v)
    return v


def _mk_policy(user_id, vehicle_id, start, end, auto_renew=True, status='active',
               premium=500, **kw):
    p = InsurancePolicy(user_id=user_id, vehicle_id=vehicle_id, provider='Aviva',
                        policy_number='POL-1', premium=premium, start_date=start,
                        end_date=end, auto_renew=auto_renew, status=status, **kw)
    db.session.add(p)
    db.session.commit()
    db.session.refresh(p)
    return p


def test_expired_auto_renew_creates_one_successor(app):
    with app.app_context():
        u = _mk_user('r1@example.com', 'ren1')
        v = _mk_vehicle(u.id)
        start = date.today() - timedelta(days=400)
        end = date.today() - timedelta(days=35)   # 365-day term, expired
        old = _mk_policy(u.id, v.id, start, end, premium=500)
        old_id = old.id

    process_auto_renew_insurance(app)

    with app.app_context():
        old = db.session.get(InsurancePolicy, old_id)
        assert old.status == 'expired'
        successors = InsurancePolicy.query.filter_by(renewed_from_id=old_id).all()
        assert len(successors) == 1
        s = successors[0]
        assert s.status == 'active' and s.auto_renew is True
        assert s.start_date == old.end_date + timedelta(days=1)
        assert (s.end_date - s.start_date).days == (old.end_date - old.start_date).days
        assert float(s.premium) == 500.0 and s.provider == 'Aviva'


def test_idempotent_no_duplicate_on_second_run(app):
    with app.app_context():
        u = _mk_user('r2@example.com', 'ren2')
        v = _mk_vehicle(u.id)
        old = _mk_policy(u.id, v.id, date.today() - timedelta(days=400),
                         date.today() - timedelta(days=35))
        old_id = old.id

    process_auto_renew_insurance(app)
    process_auto_renew_insurance(app)

    with app.app_context():
        assert InsurancePolicy.query.filter_by(renewed_from_id=old_id).count() == 1


def test_non_auto_renew_not_renewed(app):
    with app.app_context():
        u = _mk_user('r3@example.com', 'ren3')
        v = _mk_vehicle(u.id)
        old = _mk_policy(u.id, v.id, date.today() - timedelta(days=400),
                         date.today() - timedelta(days=10), auto_renew=False)
        old_id = old.id

    process_auto_renew_insurance(app)

    with app.app_context():
        assert InsurancePolicy.query.filter_by(renewed_from_id=old_id).count() == 0
        # Untouched: still active (we only expire auto_renew ones we process).
        assert db.session.get(InsurancePolicy, old_id).status == 'active'


def test_not_yet_expired_not_renewed(app):
    with app.app_context():
        u = _mk_user('r4@example.com', 'ren4')
        v = _mk_vehicle(u.id)
        old = _mk_policy(u.id, v.id, date.today() - timedelta(days=30),
                         date.today() + timedelta(days=335))  # still active
        old_id = old.id

    process_auto_renew_insurance(app)

    with app.app_context():
        assert InsurancePolicy.query.filter_by(renewed_from_id=old_id).count() == 0
        assert db.session.get(InsurancePolicy, old_id).status == 'active'


def test_editing_renewed_policy_clears_confirm_flag(app, client, user, auth_headers):
    """PUT on an auto-renewed policy clears renewed_from_id (user confirmed)."""
    with app.app_context():
        v = _mk_vehicle(user.id)
        old = _mk_policy(user.id, v.id, date.today() - timedelta(days=400),
                         date.today() - timedelta(days=35))
        old_id = old.id

    process_auto_renew_insurance(app)
    with app.app_context():
        successor = InsurancePolicy.query.filter_by(renewed_from_id=old_id).first()
        sid = successor.id
        assert successor.renewed_from_id == old_id

    resp = client.put(f'/api/insurance/{sid}', json={'premium': 550},
                      headers=auth_headers(user.id))
    assert resp.status_code == 200
    assert resp.get_json()['policy']['renewed_from_id'] is None

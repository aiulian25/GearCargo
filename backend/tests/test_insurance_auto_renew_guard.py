"""Step 2 — auto-renew must refuse a policy with a non-positive term.

`process_auto_renew_insurance` rolls an expired auto_renew policy forward by its
own term length. A policy whose `end_date <= start_date` (bad import data) rolls
into a successor that expires the day it starts — which the NEXT run then picks
up and renews again: one junk policy plus one "Insurance renewed" push per day,
forever.

A legitimate one-day policy (term_days == 1) must keep renewing, so the guard is
`< 1`, not `<= 1`.
"""

from datetime import date, timedelta

from app import db
from app.models import Vehicle
from app.models.insurance import InsurancePolicy
from app.services import process_auto_renew_insurance

TODAY = date.today()


def _vehicle(user_id, name='Focus'):
    vehicle = Vehicle(user_id=user_id, name=name, make='Ford', model='Focus')
    db.session.add(vehicle)
    db.session.commit()
    db.session.refresh(vehicle)
    return vehicle


def _policy(user_id, vehicle_id, start_date, end_date, **kwargs):
    fields = dict(
        user_id=user_id, vehicle_id=vehicle_id,
        policy_number='POL-1', provider='Allianz', policy_type='comprehensive',
        premium=300, currency='EUR',
        start_date=start_date, end_date=end_date,
        status='active', auto_renew=True,
    )
    fields.update(kwargs)
    policy = InsurancePolicy(**fields)
    db.session.add(policy)
    db.session.commit()
    db.session.refresh(policy)
    return policy


def _count(user_id):
    return InsurancePolicy.query.filter_by(user_id=user_id).count()


def test_same_day_policy_is_not_renewed(app, user):
    """start_date == end_date → term_days == 0 → no successor."""
    with app.app_context():
        vehicle = _vehicle(user.id)
        broken = _policy(user.id, vehicle.id,
                         start_date=TODAY - timedelta(days=10),
                         end_date=TODAY - timedelta(days=10))
        broken_id = broken.id

    process_auto_renew_insurance(app)

    with app.app_context():
        assert _count(user.id) == 1, 'a successor was created for a zero-length term'
        settled = db.session.get(InsurancePolicy, broken_id)
        assert settled.status == 'expired'


def test_inverted_dates_are_not_renewed(app, user):
    """end_date < start_date → negative term → no successor."""
    with app.app_context():
        vehicle = _vehicle(user.id)
        _policy(user.id, vehicle.id,
                start_date=TODAY - timedelta(days=5),
                end_date=TODAY - timedelta(days=30))

    process_auto_renew_insurance(app)

    with app.app_context():
        assert _count(user.id) == 1


def test_broken_policy_does_not_grow_on_repeated_runs(app, user):
    """The actual reported symptom: one junk policy per daily run."""
    with app.app_context():
        vehicle = _vehicle(user.id)
        _policy(user.id, vehicle.id,
                start_date=TODAY - timedelta(days=10),
                end_date=TODAY - timedelta(days=10))

    for _ in range(3):
        process_auto_renew_insurance(app)

    with app.app_context():
        assert _count(user.id) == 1


def test_broken_policy_sends_no_renewal_push(app, user, monkeypatch):
    """No successor means no "Insurance renewed" notification either."""
    sent = []
    import app.routes.push as push_routes
    monkeypatch.setattr(push_routes, 'send_push_to_user',
                        lambda *a, **k: sent.append(a))

    with app.app_context():
        vehicle = _vehicle(user.id)
        _policy(user.id, vehicle.id,
                start_date=TODAY - timedelta(days=10),
                end_date=TODAY - timedelta(days=10))

    process_auto_renew_insurance(app)

    assert sent == []


def test_one_day_policy_still_renews(app, user):
    """term_days == 1 is legitimate short-term cover — the guard must not eat it."""
    with app.app_context():
        vehicle = _vehicle(user.id)
        good = _policy(user.id, vehicle.id,
                       start_date=TODAY - timedelta(days=10),
                       end_date=TODAY - timedelta(days=9))
        good_id = good.id

    process_auto_renew_insurance(app)

    with app.app_context():
        assert _count(user.id) == 2, 'a valid one-day policy should still renew'
        successor = InsurancePolicy.query.filter_by(renewed_from_id=good_id).one()
        assert successor.start_date == TODAY - timedelta(days=8)
        assert successor.end_date == TODAY - timedelta(days=7)
        assert successor.auto_renew is True


def test_normal_annual_policy_still_renews(app, user):
    """Regression guard: the common path is untouched."""
    with app.app_context():
        vehicle = _vehicle(user.id)
        good = _policy(user.id, vehicle.id,
                       start_date=TODAY - timedelta(days=400),
                       end_date=TODAY - timedelta(days=35))
        good_id = good.id

    process_auto_renew_insurance(app)

    with app.app_context():
        assert _count(user.id) == 2
        old = db.session.get(InsurancePolicy, good_id)
        assert old.status == 'expired'
        successor = InsurancePolicy.query.filter_by(renewed_from_id=good_id).one()
        assert successor.status == 'active'
        assert successor.start_date == old.end_date + timedelta(days=1)

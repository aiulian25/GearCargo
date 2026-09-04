"""Regression tests for R4-06: the nightly `generate_auto_predictions` job.

Two defects, both invisible in production because the job logs and moves on:

1. It inserted a fresh batch WITHOUT dismissing the previous one — unlike the
   HTTP path (`routes/predictions.py:297-310`) — so alerts accumulated on every
   weekly re-run, per vehicle, forever.
2. The per-vehicle `except Exception` did not roll back, so a batch that failed
   halfway left its partial rows pending and the trailing commit persisted them.

Also pinned: fuel-ANOMALY alerts are a different feature that happens to be
Ollama-generated. Dismissing "everything this model made" would silently delete
them on a weekly schedule, so the two generators are told apart explicitly.
"""

from datetime import timedelta

import pytest

from app import db
from app.models import PredictionAlert, User, Vehicle
from app.models.prediction import GENERATED_BY_ANOMALY, GENERATED_BY_PREDICTION
from app.services import generate_auto_predictions


def _prediction(title, urgency='medium'):
    return {
        'type': 'maintenance', 'title': title, 'description': f'{title} desc',
        'confidence': 0.8, 'urgency': urgency,
    }


TWO_PREDICTIONS = {'predictions': [_prediction('Brake pads'), _prediction('Air filter')]}


def _seed_user_with_vehicle(name, email, make='VW'):
    user = User(username=email.split('@')[0], email=email, is_active=True)
    user.set_password('StrongPass123!')
    db.session.add(user)
    db.session.commit()
    vehicle = Vehicle(user_id=user.id, name=name, make=make, model='Golf',
                      archived=False, last_prediction_at=None)
    db.session.add(vehicle)
    db.session.commit()
    return user, vehicle


def _active_alerts(vehicle_id, generated_by=GENERATED_BY_PREDICTION):
    return PredictionAlert.query.filter_by(
        vehicle_id=vehicle_id, generated_by=generated_by,
        dismissed=False, actioned=False,
    ).all()


def _enable_ai(app):
    app.config['OLLAMA_ENABLED'] = True
    app.config['OLLAMA_MODEL'] = 'test-model'


def test_a_second_run_replaces_the_previous_batch(app, monkeypatch):
    """Weekly re-runs must REPLACE the previous AI batch, not stack on it."""
    monkeypatch.setattr('app.services.ollama.chat', lambda **kwargs: TWO_PREDICTIONS)

    with app.app_context():
        _enable_ai(app)
        user, vehicle = _seed_user_with_vehicle('Daily', 'predict@example.com')
        # A batch from an earlier run is already on file.
        db.session.add(PredictionAlert(
            user_id=user.id, vehicle_id=vehicle.id, alert_type='maintenance',
            title='Stale prediction', generated_by=GENERATED_BY_PREDICTION))
        db.session.commit()
        vehicle_id = vehicle.id

    generate_auto_predictions(app)
    with app.app_context():
        Vehicle.query.get(vehicle_id).last_prediction_at = None   # make it due again
        db.session.commit()
    generate_auto_predictions(app)

    with app.app_context():
        active = _active_alerts(vehicle_id)
        assert len(active) == 2, [a.title for a in active]
        assert {a.title for a in active} == {'Brake pads', 'Air filter'}


def test_a_batch_that_fails_halfway_leaves_no_partial_rows(app, monkeypatch):
    """The second prediction is malformed, so the batch raises after the first
    alert was added. Without a rollback those partial rows reached the DB."""
    broken_batch = {'predictions': [_prediction('Good one'),
                                    {'title': {'not': 'a string'}, 'urgency': 'low',
                                     'type': 'maintenance', 'description': 'x',
                                     'confidence': 0.5}]}

    with app.app_context():
        _enable_ai(app)
        # The prompt carries make/model (not the vehicle's nickname), so the
        # make is what tells the two apart inside the fake.
        _, failing = _seed_user_with_vehicle('Breaks', 'fails@example.com', make='BrokenMake')
        _, healthy = _seed_user_with_vehicle('Works', 'works@example.com', make='GoodMake')
        failing_id, healthy_id = failing.id, healthy.id

    def _chat(**kwargs):
        return broken_batch if 'BrokenMake' in str(kwargs.get('prompt', '')) else TWO_PREDICTIONS

    monkeypatch.setattr('app.services.ollama.chat', _chat)
    generate_auto_predictions(app)

    with app.app_context():
        assert _active_alerts(failing_id) == []        # no half-written batch
        assert len(_active_alerts(healthy_id)) == 2    # unaffected, and committed


def test_fuel_anomaly_alerts_survive_the_nightly_run(app, monkeypatch):
    """Fuel anomalies are a separate feature that is also Ollama-generated.
    Replacing the prediction batch must not silently delete them."""
    monkeypatch.setattr('app.services.ollama.chat', lambda **kwargs: TWO_PREDICTIONS)

    with app.app_context():
        _enable_ai(app)
        user, vehicle = _seed_user_with_vehicle('Daily', 'anomaly@example.com')
        db.session.add(PredictionAlert(
            user_id=user.id, vehicle_id=vehicle.id, alert_type='fuel',
            title='Consumption spike', urgency='medium',
            generated_by=GENERATED_BY_ANOMALY))
        db.session.commit()
        vehicle_id = vehicle.id

    generate_auto_predictions(app)

    with app.app_context():
        anomalies = _active_alerts(vehicle_id, generated_by=GENERATED_BY_ANOMALY)
        assert [a.title for a in anomalies] == ['Consumption spike']
        assert len(_active_alerts(vehicle_id)) == 2   # the new prediction batch


def test_the_job_marks_each_vehicle_as_analysed(app, monkeypatch):
    """last_prediction_at gates the 7-day re-run window; it must be persisted."""
    monkeypatch.setattr('app.services.ollama.chat', lambda **kwargs: TWO_PREDICTIONS)

    with app.app_context():
        _enable_ai(app)
        _, vehicle = _seed_user_with_vehicle('Daily', 'stamp@example.com')
        vehicle_id = vehicle.id

    generate_auto_predictions(app)

    with app.app_context():
        assert Vehicle.query.get(vehicle_id).last_prediction_at is not None

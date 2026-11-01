"""Disposable-process acceptance fixture; never imported by the application."""
import json
import os
from pathlib import Path
import sys
import time

from sqlalchemy import event
from sqlalchemy.orm import Session
from app import create_app
from app.config import TestingConfig
from app.models import InsurancePolicy
from app.services import process_auto_renew_insurance
from app.services.scheduler_registry import JobDefinition
from app.services.scheduler_ownership import run_due_job, seed_jobs, active_run


def main():
    config_path, control_path, mode, label = sys.argv[1:]
    settings = json.loads(Path(config_path).read_text())
    config = type('ProcessConfig', (TestingConfig,), settings)
    app = create_app(config, process_role='scheduler')
    control = Path(control_path)

    def work(app):
        if mode == 'hold':
            (control / f'holding-{label}').write_text(json.dumps({'pid': active_run.get().lock.pid}))
            deadline = time.monotonic() + 30
            while not (control / f'release-{label}').exists():
                if time.monotonic() > deadline:
                    raise RuntimeError('Fixture release deadline')
                time.sleep(0.02)
        if mode == 'crash_flush':
            @event.listens_for(Session, 'after_flush')
            def crash(session, context):
                if any(isinstance(row, InsurancePolicy) for row in session.new):
                    os._exit(73)
        if mode == 'crash_commit':
            @event.listens_for(Session, 'after_commit')
            def crash(session):
                if active_run.get():
                    os._exit(73)
        process_auto_renew_insurance(app)

    definitions = {'test-renewal': JobDefinition('test-renewal', work, seconds=60, start_after=-1)}
    seed_jobs(app, definitions)
    (control / f'ready-{label}').write_text('ready')
    deadline = time.monotonic() + 30
    while not (control / 'start').exists():
        if time.monotonic() > deadline:
            raise RuntimeError('Fixture start deadline')
        time.sleep(0.02)
    result = run_due_job(app, 'test-renewal', definitions)
    print(json.dumps({'ran': result}), flush=True)


if __name__ == '__main__':
    main()

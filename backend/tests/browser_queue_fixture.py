"""Isolated GC-007 browser fixture; never imported by the production app.

Run only with GC_BROWSER_QUEUE_TEST=1 and a disposable VOLUMES_PATH. The browser
runner proxies this fixture through a loopback-only server and a Unix socket.
"""
import os
from pathlib import Path

if os.environ.get('GC_BROWSER_QUEUE_TEST') != '1':
    raise RuntimeError('This disposable browser fixture requires explicit opt-in.')

from flask import request, jsonify
from app import create_app, db
from app.config import TestingConfig
from app.models import User, Vehicle


class BrowserConfig(TestingConfig):
    SQLALCHEMY_DATABASE_URI = 'sqlite:////tmp/gc007-browser.sqlite'
    SESSION_TYPE = 'filesystem'
    SESSION_FILE_DIR = '/tmp/gc007-sessions'
    WTF_CSRF_ENABLED = os.environ.get('GC_BROWSER_CSRF_TEST') == '1'
    JWT_COOKIE_SECURE = False
    VOLUMES_PATH = '/tmp/gc007-volumes'
    UPLOAD_FOLDER = '/tmp/gc007-volumes/attachments'
    BACKUP_FOLDER = '/tmp/gc007-volumes/backups'
    MAIL_ENABLED = False


for directory in (BrowserConfig.VOLUMES_PATH, BrowserConfig.UPLOAD_FOLDER, BrowserConfig.BACKUP_FOLDER):
    Path(directory).mkdir(parents=True, exist_ok=True)
app = create_app(BrowserConfig)
with app.app_context():
    db.create_all()
    for name in ('A', 'B'):
        user = User(username=f'queue_{name}', email=f'queue-{name.lower()}@example.invalid',
                    is_active=True, login_alerts_enabled=False)
        user.set_password('BrowserFixture123!')
        db.session.add(user)
    db.session.commit()
    owner_ids = {name: User.query.filter_by(username=f'queue_{name}').one().id for name in ('A', 'B')}


@app.route('/__gc007/records')
def records():
    assert request.headers.get('X-GC007-Fixture') == 'disposable-browser-only'
    return jsonify({name: [v.name for v in Vehicle.query.filter_by(user_id=owner_id)]
                    for name, owner_id in owner_ids.items()})


@app.route('/__gc007/delete-a', methods=['POST'])
def delete_a():
    assert request.headers.get('X-GC007-Fixture') == 'disposable-browser-only'
    from app.services.deletion import delete_owned_data, finish_cleanup
    operation = delete_owned_data(owner_ids['A'])
    finish_cleanup(operation)
    return jsonify({'deleted': True})

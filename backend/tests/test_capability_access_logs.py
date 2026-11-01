"""Synthetic canaries through the real Gunicorn configuration and Flask factory.

Only this test's stdout/stderr are inspected. Set GC_LOG_TEST_OUTPUT to retain
them outside a disposable container; no production logs or services are used.
"""
from datetime import timedelta
import http.client
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest


BACKEND = Path(__file__).resolve().parents[1]
FIXTURE = '''
import os
from pathlib import Path
from flask import request
from app import create_app, db
from app.config import TestingConfig

class Config(TestingConfig):
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.environ['GC_LOG_WORK'] + '/app.sqlite'
    SESSION_TYPE = 'filesystem'
    SESSION_FILE_DIR = os.environ['GC_LOG_WORK'] + '/sessions'
    VOLUMES_PATH = os.environ['GC_LOG_WORK']
    BACKUP_FOLDER = os.environ['GC_LOG_WORK'] + '/backups'
    UPLOAD_FOLDER = os.environ['GC_LOG_WORK'] + '/uploads'
    PROPAGATE_EXCEPTIONS = False
    LOG_FORMAT = os.environ['GC_LOG_FORMAT']
    LOG_REDACT_PII = os.environ['GC_LOG_PII'] == 'true'

app = create_app(Config, process_role='web')
app.static_folder = os.environ['GC_LOG_WORK'] + '/static'
Path(app.static_folder).mkdir()
Path(app.static_folder, 'index.html').write_text('<html>synthetic SPA fixture</html>')
with app.app_context():
    db.create_all()

@app.get('/gc032-ready')
def ready():
    return {'ready': True}

@app.before_request
def fail_inside_flask():
    if request.args.get('fail') == 'flask':
        raise RuntimeError('fixture Flask failure ' + request.url + '\\nReferer: ' +
                           request.headers.get('Referer', ''))

flask_wsgi = app.wsgi_app
def fail_outside_flask(environ, start_response):
    if environ.get('QUERY_STRING', '').startswith('fail=gunicorn'):
        raise RuntimeError('fixture WSGI failure ' + environ.get('RAW_URI', ''))
    return flask_wsgi(environ, start_response)
app.wsgi_app = fail_outside_flask
'''


def test_gunicorn_atoms_exclude_headers_queries_and_environment():
    from gearcargo_gunicorn_logger import CapabilitySafeLogger
    from gunicorn.glogging import SafeAtoms

    logger = object.__new__(CapabilitySafeLogger)
    environ = {'REQUEST_METHOD': 'GET', 'RAW_URI': '/secret?sig=Query-canary',
               'HTTP_REFERER': '/shared/report/Ref-canary',
               'QUERY_STRING': 'sig=Query-canary', 'HTTP_USER_AGENT': 'Agent-canary',
               'gearcargo.log_route': '/api/reports/shared/<token>',
               'gearcargo.request_id': 'server-generated-id'}
    atoms = SafeAtoms(logger.atoms(SimpleNamespace(status='200 OK', sent=42),
                                  SimpleNamespace(headers=[('Referer', 'Ref-canary')]),
                                  environ, timedelta(microseconds=1234)))
    assert atoms['r'] == 'GET /api/reports/shared/<token>'
    assert atoms['s'] == '200' and atoms['b'] == 42 and atoms['D'] == 1234
    assert atoms['gc_request_id'] == 'server-generated-id'
    for atom in ('q', 'f', 'a', '{referer}i', '{referrer}i', '{query_string}e', '{raw_uri}e'):
        assert atoms[atom] == '-'
    assert 'canary' not in repr(atoms)


@pytest.mark.parametrize('log_format,pii', [('text', 'true'), ('text', 'false'),
                                          ('json', 'true'), ('json', 'false')])
def test_actual_gunicorn_never_emits_capabilities(tmp_path, log_format, pii):
    work = tmp_path / 'server'
    work.mkdir()
    for folder in ('backups', 'uploads'):
        (work / folder).mkdir()
    (work / 'gc032_fixture.py').write_text(FIXTURE)
    output = Path(os.environ.get('GC_LOG_TEST_OUTPUT', str(tmp_path))) / f'{log_format}-{pii}'
    output.mkdir(parents=True, exist_ok=True)
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    env = {**os.environ, 'GC_LOG_WORK': str(work), 'GC_LOG_FORMAT': log_format,
           'GC_LOG_PII': pii, 'LOG_LEVEL': 'debug', 'GUNICORN_WORKERS': '1',
           'PYTHONPATH': os.pathsep.join((str(work), str(BACKEND), os.environ.get('PYTHONPATH', '')))}
    # A fresh process uses the shipped configuration, including its logger class,
    # preload and post_fork hooks. Bind only ephemeral loopback, never public ports.
    command = [sys.executable, '-m', 'gunicorn', '--config', str(BACKEND / 'gunicorn.conf.py'),
               '--bind', f'127.0.0.1:{port}', '--workers', '1', 'gc032_fixture:app']
    (output / 'command.json').write_text(json.dumps(command))
    canaries = set()
    requests = []

    def get(target, headers=None, method='GET'):
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
        try:
            connection.request(method, target, headers=headers or {})
            response = connection.getresponse()
            response.read()
            return response.status, response.getheader('X-Request-ID')
        finally:
            connection.close()

    with (output / 'access.log').open('w') as access, (output / 'error.log').open('w') as errors:
        server = subprocess.Popen(command, cwd=BACKEND, env=env, stdout=access, stderr=errors)
        try:
            deadline = time.monotonic() + 30
            while True:
                try:
                    assert get('/gc032-ready')[0] == 200
                    break
                except (OSError, http.client.HTTPException):
                    if server.poll() is not None or time.monotonic() >= deadline:
                        pytest.fail(f'Gunicorn did not start; synthetic logs: {output}')
                    time.sleep(0.05)

            cases = [
                ('/api/reports/shared/{secret}', 'GET'),
                ('/api/reports/shared/{secret}/pdf', 'GET'),
                ('/shared/report/{secret}', 'GET'),
                ('/api/calendar/feed/{secret}', 'GET'),
                ('/api/attachments/42/view?sig={secret}&sig=Repeat-secret_Q&EXP=123', 'GET'),
                ('/uploads/{secret}.jpg?sig=Signature-secret_Q&uid=1&exp=123', 'GET'),
                ('/api/reports/shared/%45ncoded-{secret}', 'GET'),
                ('/api/reports/shared/{secret}?fail=flask&sig=Flask-query_Q', 'GET'),
                ('/api/reports/shared/{secret}?fail=gunicorn&sig=WSGI-query_Q', 'GET'),
                ('/api/unmatched/{secret}?Signature=Unknown-query_Q', 'GET'),
                ('/api/calendar/feed/{secret}', 'POST'),
                ('/gc032-ready?unknown={secret}', 'GET'),
            ]
            canaries.update(('Repeat-secret_Q', 'Signature-secret_Q', 'Flask-query_Q',
                             'WSGI-query_Q', 'Unknown-query_Q'))
            for index, (template, method) in enumerate(cases):
                secret = f'Path-canary_{index}_Q'
                referer = f'Ref-canary_{index}_Q'
                supplied_id = f'Id-canary_{index}_Q'
                agent = f'Agent-canary_{index}_Q'
                canaries.update((secret, referer, supplied_id, agent))
                headers = {('Referer', 'Referrer', 'rEfErEr', 'REFERRER')[index % 4]:
                           f'https://test.invalid/shared/report/{referer}?sig={referer}',
                           'X-Request-ID': supplied_id, 'User-Agent': agent}
                status, request_id = get(template.format(secret=secret), headers, method)
                requests.append((status, request_id))
                if 'fail=gunicorn' in template:
                    assert status == 500
                if 'fail=flask' in template:
                    assert status == 500
                if template.startswith(('/shared/report/', '/gc032-ready')):
                    assert status == 200

            # Parser-level errors occur before Flask and can quote invalid header
            # names or methods in Gunicorn warnings. Neither value is safe to log.
            for raw in (
                b'GET /api/reports/shared/Parser-path_Q HTTP/1.1\r\nHost: localhost\r\nBad Header-secret_Q: value\r\n\r\n',
                b'Method-secret_Q@ /api/reports/shared/Parser-path_Q HTTP/1.1\r\nHost: localhost\r\n\r\n',
            ):
                canaries.update(('Parser-path_Q', 'Header-secret_Q', 'Method-secret_Q'))
                with socket.create_connection(('127.0.0.1', port), timeout=5) as connection:
                    connection.sendall(raw)
                    assert b'400' in connection.recv(4096).split(b'\r\n', 1)[0]
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)

    access_text = (output / 'access.log').read_text()
    error_text = (output / 'error.log').read_text()
    combined = access_text + error_text
    for secret in sorted(canaries):
        assert secret not in combined, f'{secret} leaked into synthetic logs at {output}'
    lines = re.findall(r'method=(\S+) route=(\S+) status=(\d{3}) bytes=(\d+) '
                       r'duration_us=(\d+) request_id=([a-f0-9]{32})', access_text)
    assert len(lines) >= len(cases) + 1
    for (template, _), (_, request_id) in zip(cases, requests):
        if 'fail=gunicorn' not in template:
            assert re.fullmatch(r'[a-f0-9]{32}', request_id or '')
    for status, request_id in requests:
        if request_id:
            assert any(line[2] == str(status) and line[5] == request_id for line in lines)
    for route in ('/api/reports/shared/<token>', '/api/reports/shared/<token>/pdf',
                  '/api/calendar/feed/<token>', '/api/attachments/<int:attachment_id>/view',
                  '/uploads/<path:filename>', '/[unmatched]', '/gc032-ready'):
        assert any(line[1] == route for line in lines), route
    assert any(line[2] == '500' and line[1] == '/[unmatched]' for line in lines)
    assert 'RuntimeError: fixture Flask failure' in error_text
    assert 'RuntimeError: fixture WSGI failure' in error_text
    assert 'Traceback' in error_text
    assert 'Invalid HTTP request [details omitted]' in error_text
    assert '[request target omitted]' in error_text  # Debug mode is safe too.
    if log_format == 'json':
        payloads = [json.loads(line) for line in error_text.splitlines() if line.startswith('{')]
        assert any('fixture Flask failure' in row.get('exception', '') for row in payloads)

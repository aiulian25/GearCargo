"""Real Redis browser-session failures before dispatch and after authentication."""
import os
from pathlib import Path
import socket
import subprocess
import time

import pytest
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from app import create_app, db
from app.models import User
from app.routes import auth


@pytest.fixture
def redis_server(tmp_path):
    with socket.socket() as listener:
        listener.bind(('127.0.0.1',0)); port=listener.getsockname()[1]
    client=Redis(host='127.0.0.1',port=port,socket_connect_timeout=.2,socket_timeout=.2)
    logs=Path(os.environ.get('GC_SCHEDULER_LOG_DIR',str(tmp_path)))/tmp_path.name
    logs.mkdir(parents=True,exist_ok=True)
    processes=[]
    def start():
        with (logs/f'redis-{len(processes)}.txt').open('w') as stream:
            child=subprocess.Popen(['redis-server','--bind','127.0.0.1','--port',str(port),
                '--save','','--appendonly','no','--dir',str(tmp_path)],stdout=stream,stderr=subprocess.STDOUT)
        processes.append(child)
        deadline=time.monotonic()+10
        while True:
            try:
                if client.ping(): break
            except RedisConnectionError: pass
            assert child.poll() is None and time.monotonic()<deadline
            time.sleep(.02)
        return child
    child=start()
    yield client,child,start,f'redis://127.0.0.1:{port}/0'
    for child in processes:
        if child.poll() is None: child.terminate()
        child.wait(timeout=10)


def browser_app(app,user,redis_server,monkeypatch,**overrides):
    redis_client,_,_,url=redis_server
    config={**app.config,'SESSION_TYPE':'redis','SESSION_REDIS':redis_client,'REDIS_URL':url,
            'WTF_CSRF_ENABLED':True,'APP_URL':'http://localhost','CSRF_TRUSTED_ORIGINS':['http://localhost'],
            'RATELIMIT_STORAGE_URL':'memory://',**overrides}
    result=create_app(type('BrowserConfig',(),config))
    monkeypatch.setattr(auth,'redis_client',redis_client)
    with result.test_request_context():
        access,refresh=auth.generate_tokens(db.session.get(User,user.id))
    return result,access,refresh


def test_browser_read_failure_returns_503_without_empty_session_fallback(app,user,redis_server,monkeypatch):
    browser,access,_=browser_app(app,user,redis_server,monkeypatch)
    client=browser.test_client();client.set_cookie('access_token',access)
    proof=client.get('/api/auth/csrf-token').json['csrf_token']
    cookie=client.get_cookie(browser.config['SESSION_COOKIE_NAME']).value
    redis_server[1].terminate();redis_server[1].wait(timeout=10)
    response=client.get('/api/auth/me')
    assert response.status_code==503 and response.json['code']=='AUTH_UNAVAILABLE'
    assert not response.headers.getlist('Set-Cookie')
    assert client.get_cookie(browser.config['SESSION_COOKIE_NAME']).value==cookie
    response=client.post('/api/auth/logout',headers={'Origin':'http://localhost','X-CSRF-Token':proof})
    assert response.status_code==503
    # A client that does not need browser CSRF state still verifies its JWT in DB.
    assert browser.test_client().get('/api/auth/me',headers={'Authorization':'Bearer '+access}).status_code==200
    redis_server[2]()  # lost cache, same durable DB
    assert client.get('/api/auth/me').status_code==200
    assert client.post('/api/auth/logout',headers={'Origin':'http://localhost','X-CSRF-Token':proof}).status_code==403
    proof=client.get('/api/auth/csrf-token').json['csrf_token']
    assert client.post('/api/auth/logout',headers={'Origin':'http://localhost','X-CSRF-Token':proof}).status_code==200
    assert browser.test_client().get('/api/auth/me',headers={'Authorization':'Bearer '+access}).status_code==401


@pytest.mark.parametrize('operation', ['login', 'logout', 'refresh'])
def test_browser_write_failure_withholds_new_auth_cookies(app,user,redis_server,monkeypatch,operation):
    from flask import request
    browser,access,refresh=browser_app(app,user,redis_server,monkeypatch)
    @browser.after_request
    def disconnect_after_login(response):
        if request.path == '/api/auth/'+operation:
            redis_server[1].terminate(); redis_server[1].wait(timeout=10)
        return response
    client=browser.test_client(); client.set_cookie('access_token',access)
    proof=client.get('/api/auth/csrf-token').json['csrf_token']
    response=client.post('/api/auth/'+operation,json={'email':user.email,'password':'StrongPass123!','refresh_token':refresh},
                        headers={'Origin':'http://localhost','X-CSRF-Token':proof})
    assert response.status_code==503 and response.json['code']=='AUTH_UNAVAILABLE'
    assert response.headers['Cache-Control']=='no-store'
    assert not response.headers.getlist('Set-Cookie')
    if operation != 'login':
        assert browser.test_client().get('/api/auth/me',headers={'Authorization':'Bearer '+access}).status_code==401


def test_redis_limiter_failure_is_503_not_unlimited_access(app,user,redis_server,monkeypatch):
    browser,access,_=browser_app(app,user,redis_server,monkeypatch,
        RATELIMIT_ENABLED=True,RATELIMIT_STORAGE_URL=redis_server[3])
    client=browser.test_client()
    assert client.get('/api/auth/me',headers={'Authorization':'Bearer '+access}).status_code==200
    redis_server[1].terminate();redis_server[1].wait(timeout=10)
    response=client.get('/api/auth/me',headers={'Authorization':'Bearer '+access})
    assert response.status_code==503 and response.json['code']=='AUTH_UNAVAILABLE'

"""GC-010 receipt rollout: parent consistency and idempotent upload/link."""
from io import BytesIO
from datetime import date
import pytest
from app import db
from app.models import Attachment, InsurancePolicy
from tests.test_mutation_retries import operation, fuel, car

PDF = b'%PDF-1.4\n% disposable receipt fixture\n%%EOF\n'

def upload(client, auth, vehicle_id=None, entry_id=None, category=None, headers=None):
    data = {'file': (BytesIO(PDF), 'receipt.pdf')}
    if vehicle_id: data['vehicle_id'] = str(vehicle_id)
    if entry_id: data['entry_id'] = str(entry_id)
    if category: data['category'] = category
    return client.post('/api/attachments', headers=headers or operation(auth), data=data)

@pytest.fixture(autouse=True)
def no_background(monkeypatch):
    monkeypatch.setattr('app.services.task_queue.enqueue_task', lambda *a, **kw: None)


def test_upload_rejects_mismatched_parent_without_creating_file(app, client, user, auth_headers):
    from pathlib import Path
    auth = auth_headers(user.id)
    vehicle_a, vehicle_b = car(user), car(user)
    entry = fuel(client, auth, vehicle_b)
    response = upload(client, auth, vehicle_a.id, entry['id'])
    assert response.status_code == 409
    assert Attachment.query.count() == 0
    assert not list(Path(app.config['UPLOAD_FOLDER']).rglob('*.pdf'))


def test_link_rejects_mismatch_without_partial_metadata_change(client, user, auth_headers):
    auth = auth_headers(user.id)
    vehicle_a, vehicle_b = car(user), car(user)
    attachment = upload(client, auth, vehicle_a.id).json['attachment']
    entry = fuel(client, auth, vehicle_b)
    response = client.put(f'/api/attachments/{attachment["id"]}', headers=operation(auth, attachment['revision']),
                          json={'entry_id': entry['id'], 'description': 'must not persist'})
    assert response.status_code == 409
    row = db.session.get(Attachment, attachment['id'])
    assert row.entry_id is None and row.vehicle_id == vehicle_a.id and row.description is None


def test_upload_and_link_response_loss_are_exactly_once(client, user, auth_headers):
    auth = auth_headers(user.id)
    vehicle = car(user)
    entry = fuel(client, auth, vehicle)
    key = operation(auth)
    first = upload(client, auth, vehicle.id, headers=key)
    retry = upload(client, auth, vehicle.id, headers=key)
    assert first.status_code == retry.status_code == 201
    assert first.data == retry.data and Attachment.query.count() == 1
    attachment = first.json['attachment']
    link_headers = operation(auth, attachment['revision'])
    path = f'/api/attachments/{attachment["id"]}'
    data = {'entry_id': entry['id'], 'category': 'receipt'}
    linked = client.put(path, headers=link_headers, json=data)
    again = client.put(path, headers=link_headers, json=data)
    assert linked.status_code == again.status_code == 200 and linked.data == again.data
    assert client.get(path + '/download', headers=auth).data == PDF
    assert db.session.get(Attachment, attachment['id']).entry_id == entry['id']


def test_link_conflict_preserves_uploaded_file(client, user, auth_headers):
    auth = auth_headers(user.id)
    vehicle = car(user)
    entry = fuel(client, auth, vehicle)
    attachment = upload(client, auth, vehicle.id).json['attachment']
    path = f'/api/attachments/{attachment["id"]}'
    assert client.put(path, headers=operation(auth, attachment['revision']), json={'description': 'Other edit'}).status_code == 200
    result = client.put(path, headers=operation(auth, attachment['revision']), json={'entry_id': entry['id']})
    assert result.status_code == 409 and result.json['code'] == 'REVISION_CONFLICT'
    assert client.get(path + '/download', headers=auth).data == PDF
    assert db.session.get(Attachment, attachment['id']).entry_id is None


def test_orphan_link_derives_vehicle(client, user, auth_headers):
    auth = auth_headers(user.id)
    vehicle = car(user)
    entry = fuel(client, auth, vehicle)
    attachment = upload(client, auth).json['attachment']
    response = client.put(f'/api/attachments/{attachment["id"]}', headers=operation(auth, attachment['revision']), json={'entry_id': entry['id']})
    assert response.status_code == 200
    assert response.json['attachment']['vehicle_id'] == vehicle.id


def test_insurance_link_is_explicit_and_never_uses_an_entry_id_collision(client, user, auth_headers):
    auth = auth_headers(user.id)
    vehicle = car(user)
    entry = fuel(client, auth, vehicle)
    policy = InsurancePolicy(user_id=user.id, vehicle_id=vehicle.id, provider='Test', premium=12,
                             start_date=date(2026, 1, 1), end_date=date(2027, 1, 1))
    db.session.add(policy); db.session.commit()
    attachment = upload(client, auth, vehicle.id).json['attachment']
    path = f'/api/attachments/{attachment["id"]}'
    response = client.put(path, headers=operation(auth, attachment['revision']), json={'insurance_id': policy.id, 'category': 'insurance_document'})
    assert response.status_code == 200
    assert response.json['insurance_id'] == policy.id
    assert policy.document_attachment_id == attachment['id']
    assert db.session.get(Attachment, attachment['id']).entry_id is None
    current = response.json['attachment']
    result = client.put(path, headers=operation(auth, current['revision']), json={'entry_id': entry['id']})
    assert result.status_code == 409


def test_foreign_parent_is_not_disclosed(client, user, auth_headers, app):
    from app.models import User
    other = User(username='receipt_other', email='receipt_other@example.invalid', is_active=True)
    other.set_password('StrongPass123!'); db.session.add(other); db.session.commit()
    other_vehicle = car(other)
    other_entry = fuel(client, auth_headers(other.id), other_vehicle)
    auth = auth_headers(user.id)
    vehicle = car(user)
    attachment = upload(client, auth, vehicle.id).json['attachment']
    result = client.put(f'/api/attachments/{attachment["id"]}', headers=operation(auth, attachment['revision']), json={'entry_id': other_entry['id']})
    assert result.status_code == 404
    assert db.session.get(Attachment, attachment['id']).entry_id is None

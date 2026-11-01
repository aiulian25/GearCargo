"""Proposal 9: selected data, exact splits/refunds, replay and retention."""
from datetime import date
from decimal import Decimal
import copy
import uuid
import pytest
from app import db
from app.models import Vehicle, ServiceEntry, Entry, StatementBatch, StatementTransaction, StatementMatch, MutationOperation
from app.services.reconciliation import batch_view


@pytest.fixture
def expenses(user):
    car = Vehicle(user_id=user.id, name='Statement car')
    db.session.add(car); db.session.flush()
    rows = [ServiceEntry(user_id=user.id, vehicle_id=car.id, date=date(2026,10,1), title=f'Invoice {n}', amount=value,
        currency='GBP', service_type='inspection') for n,value in enumerate(('40.00','60.00','-20.00'))]
    db.session.add_all(rows); db.session.commit()
    return rows


def headers(auth_headers, user, batch=None, key=None):
    return {**auth_headers(user.id), 'X-GearCargo-Mutation-Version':'1','Idempotency-Key': key or uuid.uuid4().hex,
        **({'If-Match':f'"{batch["revision"]}"'} if batch else {})}


def payload(**extra):
    return dict(name='October selected', source_key='a'*64, rows=[dict(row_number=2, date='2026-10-01', amount='100.00', currency='GBP', vendor='Garage'),
        dict(row_number=4,date='2026-10-02',amount='-20.00',currency='GBP',vendor='Refund')], **extra)


def create(client,user,auth_headers,body=None):
    response=client.post('/api/reconciliation',json=body or payload(),headers=headers(auth_headers,user))
    assert response.status_code==201,response.json
    return detail(client,user,auth_headers,response.json['id'])


def detail(client,user,auth_headers,ident):
    response=client.get(f'/api/reconciliation/{ident}',headers=auth_headers(user.id))
    assert response.status_code==200,response.json
    return response.json


def match(client,user,auth_headers,batch,row,entries,**extra):
    return client.put(f'/api/reconciliation/{batch["id"]}/rows/{batch["transactions"][row]["id"]}',json=dict(matches=[dict(entry_id=e.id,revision=e.revision,amount=value) for e,value in entries],**extra),headers=headers(auth_headers,user,batch))


def test_preview_replay_and_no_ledger_duplicates(client,user,auth_headers,expenses):
    preview=client.post('/api/reconciliation/preview',json=payload(),headers=auth_headers(user.id))
    assert preview.status_code==200 and StatementBatch.query.count()==0
    batch=create(client,user,auth_headers)
    assert Entry.query.count()==3 and StatementTransaction.query.count()==2
    for _ in range(2):
        r=client.post('/api/reconciliation',json=payload(),headers=headers(auth_headers,user))
        assert r.status_code==200 and r.json['id']==batch['id']
    assert StatementBatch.query.count()==1 and StatementTransaction.query.count()==2
    assert client.get(f'/api/reconciliation/{batch["id"]}',headers=auth_headers(user.id)).headers['Cache-Control']=='no-store'
    changed=payload();changed['rows'][0]['amount']='99.00'
    r=client.post('/api/reconciliation',json=changed,headers=headers(auth_headers,user))
    assert r.status_code==400 and r.json['message_key']=='reconciliation.selectionChanged'
    assert all('Garage' not in (r.body or '') for r in MutationOperation.query.all())


def test_split_refund_complete_summary_and_delete(client,user,auth_headers,expenses):
    batch=create(client,user,auth_headers)
    before=[e.to_dict() for e in expenses]
    r=match(client,user,auth_headers,batch,0,[(expenses[0],'40.00'),(expenses[1],'60.00')]);assert r.status_code==200,r.json
    batch=detail(client,user,auth_headers,batch['id'])
    assert batch['transactions'][0]['remaining']=='0.00' and batch['transactions'][1]['status']=='unmatched'
    r=match(client,user,auth_headers,batch,1,[(expenses[2],'-20.00')]);assert r.status_code==200,r.json
    batch=detail(client,user,auth_headers,batch['id'])
    opts=headers(auth_headers,user,batch)
    path=f'/api/reconciliation/{batch["id"]}/complete'
    r=client.post(path,json={},headers=opts);assert r.status_code==200,r.json
    repeat=client.post(path,json={},headers=opts);assert repeat.json==r.json and repeat.headers['Idempotent-Replay']=='true'
    batch=detail(client,user,auth_headers,batch['id'])
    assert batch['effective_status']=='reconciled' and batch['totals']['GBP']==dict(statement='80.00',allocated='80.00',excluded='0.00',remaining='0.00')
    assert [e.to_dict() for e in expenses]==before
    csv=client.get(f'/api/reconciliation/{batch["id"]}/summary.csv',headers=auth_headers(user.id))
    assert csv.status_code==200 and '-20.00' in csv.text and 'matched' in csv.text
    r=client.delete(f'/api/reconciliation/{batch["id"]}',headers=headers(auth_headers,user,batch));assert r.status_code==200
    assert StatementTransaction.query.count()==StatementMatch.query.count()==StatementBatch.query.count()==0
    assert [e.to_dict() for e in expenses]==before


def test_many_rows_one_expense_and_balance_limits(client,user,auth_headers,expenses):
    data=payload();data['rows'][0]['amount']='20.00';data['rows'][1].update(amount='20.00')
    batch=create(client,user,auth_headers,data)
    assert match(client,user,auth_headers,batch,0,[(expenses[0],'20.00')]).status_code==200
    old=batch;batch=detail(client,user,auth_headers,batch['id'])
    assert match(client,user,auth_headers,old,1,[(expenses[0],'20.00')]).status_code==409
    assert match(client,user,auth_headers,batch,1,[(expenses[0],'20.00')]).status_code==200
    other=copy.deepcopy(data);other['source_key']='b'*64
    second=create(client,user,auth_headers,other)
    assert match(client,user,auth_headers,second,0,[(expenses[0],'0.01')]).status_code==400
    assert match(client,user,auth_headers,second,0,[(expenses[1],'20.01')]).status_code==400
    assert match(client,user,auth_headers,second,0,[(expenses[2],'-1.00')]).status_code==400
    expenses[1].currency='EUR';db.session.commit()
    assert match(client,user,auth_headers,second,0,[(expenses[1],'20.00')]).status_code==400


def test_stale_entry_cannot_confirm_and_edit_invalidates_completion(client,user,auth_headers,expenses):
    batch=create(client,user,auth_headers)
    r=client.get(f'/api/reconciliation/{batch["id"]}/rows/{batch["transactions"][0]["id"]}/candidates',headers=auth_headers(user.id));assert r.status_code==200
    revision=expenses[0].revision
    expenses[0].amount=Decimal('45');db.session.commit()
    r=client.put(f'/api/reconciliation/{batch["id"]}/rows/{batch["transactions"][0]["id"]}',json={'matches':[dict(entry_id=expenses[0].id,revision=revision,amount='40.00')]},headers=headers(auth_headers,user,batch))
    assert r.status_code==400 and r.json['message_key']=='reconciliation.changed'
    assert match(client,user,auth_headers,batch,0,[(expenses[0],'40.00'),(expenses[1],'60.00')]).status_code==200
    batch=detail(client,user,auth_headers,batch['id'])
    assert match(client,user,auth_headers,batch,1,[],exclusion_reason='Personal refund').status_code==200
    batch=detail(client,user,auth_headers,batch['id'])
    assert client.post(f'/api/reconciliation/{batch["id"]}/complete',json={},headers=headers(auth_headers,user,batch)).status_code==200
    expenses[0].amount=Decimal('44');db.session.commit()
    batch=detail(client,user,auth_headers,batch['id'])
    assert batch['effective_status']=='needs_review' and not batch['resolved']
    assert client.post(f'/api/reconciliation/{batch["id"]}/complete',json={},headers=headers(auth_headers,user,batch)).status_code==400
    db.session.delete(expenses[0]);db.session.commit()
    assert detail(client,user,auth_headers,batch['id'])['transactions'][0]['status']=='needs_review'


@pytest.mark.parametrize('field,value',[('amount','1.001'),('amount','NaN'),('amount','0'),('currency',''),('currency','gbp'),('vendor','x'*121),('date','2026-02-30'),('row_number',True)])
def test_invalid_selection_is_atomic(client,user,auth_headers,field,value):
    data=payload();data['rows'][0][field]=value
    r=client.post('/api/reconciliation',json=data,headers=headers(auth_headers,user))
    assert r.status_code==400,r.json
    assert StatementBatch.query.count()==StatementTransaction.query.count()==0


def test_owner_isolation_online_required_and_formula_safe_export(client,user,auth_headers,expenses):
    from app.models import User
    other=User(username='other-statement',email='other-statement@example.invalid');other.set_password('TestsOnly123!');db.session.add(other);db.session.commit()
    data=payload();data['rows'][0]['vendor']='=HYPERLINK("bad")'
    batch=create(client,user,auth_headers,data)
    assert client.get(f'/api/reconciliation/{batch["id"]}',headers=auth_headers(other.id)).status_code==404
    assert client.get('/api/reconciliation',headers=auth_headers(other.id)).json['batches']==[]
    assert client.post('/api/reconciliation',json=data,headers=auth_headers(user.id)).status_code==428
    assert client.post('/api/reconciliation',json=data,headers={**headers(auth_headers,user),'X-GearCargo-Offline-Owner':str(user.id)}).status_code>=400
    assert "'=HYPERLINK" in client.get(f'/api/reconciliation/{batch["id"]}/summary.csv',headers=auth_headers(user.id)).text


def test_backup_replay_retention_and_legacy_version(app,client,user,auth_headers,expenses,tmp_path,monkeypatch):
    from io import BytesIO
    from app.routes import backup
    from app.services.backup_schema import prepare_backup, BackupSchemaError
    from app.models import User, ImportIdentity, ImportBatch
    monkeypatch.setattr(backup,'get_uploads_folder',lambda:str(tmp_path/'photos'))
    batch=create(client,user,auth_headers)
    assert match(client,user,auth_headers,batch,0,[(expenses[0],'40.00'),(expenses[1],'60.00')]).status_code==200
    batch=detail(client,user,auth_headers,batch['id'])
    assert match(client,user,auth_headers,batch,1,[(expenses[2],'-20.00')]).status_code==200
    batch=detail(client,user,auth_headers,batch['id'])
    assert client.post(f'/api/reconciliation/{batch["id"]}/complete',json={},headers=headers(auth_headers,user,batch)).status_code==200
    archive,data=backup.create_backup_zip(user)
    old=copy.deepcopy(data);old['version']='4.6'
    for key in ('statement_batches','statement_transactions','statement_matches'):old.pop(key)
    assert prepare_backup(old).records['statement_batches']==[]
    damaged=copy.deepcopy(data);damaged['statement_matches'][0]['amount']='100.01'
    with pytest.raises(BackupSchemaError):prepare_backup(damaged)
    target=User(username='statement-restore',email='statement-restore@example.invalid');target.set_password('Test123456!');db.session.add(target);db.session.commit()
    for _ in range(2):
        with app.test_request_context():result=backup.restore_from_zip(target,BytesIO(archive.getvalue()))
        assert result.status_code==200,result.json
    restored=StatementBatch.query.filter_by(user_id=target.id).one()
    restored_id=restored.id
    restored_view=detail(client,target,auth_headers,restored_id)
    assert restored_view['effective_status']=='reconciled' and restored_view['resolved']
    raw_replay=client.post('/api/reconciliation',json=payload(),headers=headers(auth_headers,target))
    assert raw_replay.status_code==200 and raw_replay.json['id']==restored_id
    assert client.delete(f'/api/reconciliation/{restored_id}',headers=headers(auth_headers,target,restored_view)).status_code==200
    assert Entry.query.filter_by(user_id=target.id).count()==3
    assert not ImportIdentity.query.filter(ImportIdentity.user_id==target.id,ImportIdentity.entity_kind.like('statement_%')).all()
    for imported in ImportBatch.query.filter_by(user_id=target.id):
        assert all(not r['kind'].startswith('statement_') for r in imported.metadata_json.get('records',[]))
        assert all(not r['kind'].startswith('statement_') for r in imported.metadata_json.get('origins',[]))
    assert StatementBatch.query.filter_by(user_id=user.id).count()==1


def test_vehicle_and_account_deletion_inventory(app,client,user,auth_headers,expenses):
    from app.services.deletion import delete_owned_data
    batch=create(client,user,auth_headers)
    assert match(client,user,auth_headers,batch,0,[(expenses[0],'40.00')]).status_code==200
    vehicle_id=expenses[0].vehicle_id
    delete_owned_data(user.id,vehicle_id=vehicle_id)
    assert StatementBatch.query.count()==1 and StatementTransaction.query.count()==2 and StatementMatch.query.count()==0
    assert not batch_view(StatementBatch.query.one())['resolved']
    uid=user.id
    delete_owned_data(uid)
    assert StatementBatch.query.count()==StatementTransaction.query.count()==StatementMatch.query.count()==0


def test_zero_net_unmatched_requires_row_resolution_and_revisions(client,user,auth_headers,expenses):
    data=payload();data['rows'][0]['amount']='20.00'
    batch=create(client,user,auth_headers,data)
    assert batch['totals']['GBP']['statement']=='0.00' and not batch['resolved']
    assert client.post(f'/api/reconciliation/{batch["id"]}/complete',json={},headers=headers(auth_headers,user,batch)).status_code==400
    assert client.post(f'/api/reconciliation/{batch["id"]}/complete',json={},headers=headers(auth_headers,user)).status_code==428
    data['raw_csv']='Unselected private data'
    assert client.post('/api/reconciliation/preview',json=data,headers=auth_headers(user.id)).status_code==400


def test_fuel_uses_ledger_total_and_candidate_currency_filter(client,user,auth_headers,expenses):
    from app.models import FuelEntry
    fuel=FuelEntry(user_id=user.id,vehicle_id=expenses[0].vehicle_id,date=date(2026,10,1),title='Fuel invoice',amount=1,total_price=100,currency='GBP',liters=50,price_per_liter=2)
    db.session.add(fuel);db.session.commit()
    batch=create(client,user,auth_headers)
    result=client.get(f'/api/reconciliation/{batch["id"]}/rows/{batch["transactions"][0]["id"]}/candidates',headers=auth_headers(user.id))
    assert result.json['candidates'][0]['id']==fuel.id and result.json['candidates'][0]['amount']=='100.00'
    assert match(client,user,auth_headers,batch,0,[(fuel,'100.00')]).status_code==200
    fuel.total_price=Decimal('99.99');db.session.commit()
    assert detail(client,user,auth_headers,batch['id'])['transactions'][0]['status']=='needs_review'


def test_concurrent_batches_cannot_overallocate_postgres(app,client,user,auth_headers,expenses):
    if db.engine.dialect.name!='postgresql':pytest.skip('PostgreSQL row-lock concurrency check')
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    data=payload();data['rows']=data['rows'][:1];data['rows'][0]['amount']='40.00'
    first=create(client,user,auth_headers,data)
    data['source_key']='c'*64
    second=create(client,user,auth_headers,data)
    body={'matches':[dict(entry_id=expenses[0].id,revision=expenses[0].revision,amount='40.00')]}
    requests=[(f'/api/reconciliation/{b["id"]}/rows/{b["transactions"][0]["id"]}',headers(auth_headers,user,b)) for b in (first,second)]
    barrier=Barrier(2)
    def confirm(args):
        with app.app_context(),app.test_client() as separate:
            barrier.wait(timeout=10)
            response=separate.put(args[0],json=body,headers=args[1])
            return response.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(confirm,requests))
    assert sorted(results)==[200,400]
    db.session.expire_all()
    assert sum((m.amount for m in StatementMatch.query.all()),Decimal(0))==Decimal('40.00')


def test_backup_statement_collision_is_reviewable_not_unique_error(client,user,auth_headers,expenses):
    from app.services.backup_schema import export_user_data, prepare_backup
    from app.services.import_identity import ImportPlan, ImportConflict
    create(client,user,auth_headers)
    prepared=prepare_backup(export_user_data(user))
    prepared.namespace='backup:unrelated-source'
    plan=ImportPlan(user,prepared)
    assert plan.preview['blocked'] and plan.preview['statement_collision']
    assert any(item['reason']=='statement_source_collision' for item in plan.actions.values())
    with pytest.raises(ImportConflict,match='statement file already exists'):
        plan.validate_apply('keep_existing')


def test_statement_migration_matches_model_on_both_databases(app):
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect
    path=Path(__file__).parents[1]/'migrations/versions/feature_reconciliation.py'
    spec=importlib.util.spec_from_file_location('statement_migration',path)
    migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    with app.app_context():
        db.session.remove()
        with db.engine.begin() as connection:
            migration.op=Operations(MigrationContext.configure(connection))
            migration.downgrade()
            for _ in range(2):
                migration.upgrade()
                inspector=inspect(connection)
                for model in (StatementBatch,StatementTransaction,StatementMatch):
                    table=model.__table__
                    actual={c['name']:c for c in inspector.get_columns(table.name)}
                    assert set(actual)=={c.name for c in table.columns}
                    for column in table.columns:
                        assert actual[column.name]['nullable']==column.nullable
                        assert str(actual[column.name]['type'].compile(dialect=connection.dialect))==str(column.type.compile(dialect=connection.dialect))
                    assert {tuple(fk['constrained_columns']) for fk in inspector.get_foreign_keys(table.name)}=={(fk.parent.name,) for fk in table.foreign_keys}
                    assert {c['name'] for c in inspector.get_check_constraints(table.name)}=={c.name for c in table.constraints if c.__class__.__name__=='CheckConstraint'}
                if _==0:migration.downgrade()


def test_reverting_expense_does_not_revive_old_allocations(client,user,auth_headers,expenses):
    from datetime import timedelta
    first=create(client,user,auth_headers)
    assert match(client,user,auth_headers,first,0,[(expenses[0],'40.00')]).status_code==200
    original_time=expenses[0].updated_at
    expenses[0].amount=Decimal('45');expenses[0].updated_at=original_time+timedelta(seconds=1);db.session.commit()
    data=payload();data['source_key']='d'*64
    second=create(client,user,auth_headers,data)
    assert match(client,user,auth_headers,second,0,[(expenses[0],'40.00')]).status_code==200
    expenses[0].amount=Decimal('40');expenses[0].updated_at=original_time+timedelta(seconds=2);db.session.commit()
    for batch in (first,second):
        row=detail(client,user,auth_headers,batch['id'])['transactions'][0]
        assert row['status']=='needs_review' and row['allocated']=='0.00'

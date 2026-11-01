"""Online, owner-scoped statement review. Only selected normalized rows arrive."""
import csv
from io import StringIO
from functools import wraps
from flask import Blueprint, jsonify, request, Response
from app import db
from app.models import StatementBatch, StatementTransaction
from app.routes.auth import token_required
from app.services import reconciliation as workflow
from app.services.import_identity import digest, lock_imports
from app.services.mutations import mutation_endpoint, commit_mutation
from app.utils.entryparse import InvalidFieldError, invalid_field_response
from app.utils.timeutils import utc_naive_now

reconciliation_bp = Blueprint('reconciliation', __name__)


@reconciliation_bp.after_request
def private_response(response):
    response.headers['Cache-Control'] = 'no-store'
    return response


def online(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        if request.headers.get('X-GearCargo-Offline-Owner'):
            return jsonify(code='ONLINE_REQUIRED', message_key='reconciliation.online', error='Statement confirmation requires an online review.'), 400
        if request.method != 'GET' and (request.headers.get('X-GearCargo-Mutation-Version') != '1' or not request.headers.get('Idempotency-Key')):
            return jsonify(code='MUTATION_PROTOCOL_REQUIRED', error='An operation ID and record revision are required.'), 428
        return function(*args, **kwargs)
    return wrapped


def owned(user, batch_id):
    return StatementBatch.query.filter_by(id=batch_id, user_id=user.id).first_or_404()


def saved(batch, status=200):
    batch.updated_at = utc_naive_now()
    commit_mutation()
    return jsonify(batch.to_dict()), status


@reconciliation_bp.get('')
@token_required
def list_batches(user):
    # Bounded list; older batches remain accessible by ID and pagination.
    page = max(1, request.args.get('page', 1, type=int))
    batches = StatementBatch.query.filter_by(user_id=user.id).order_by(StatementBatch.id.desc()).offset((page-1)*50).limit(51).all()
    return jsonify(batches=[dict(**b.to_dict(), name=b.name) for b in batches[:50]], more=len(batches)>50)


@reconciliation_bp.post('/preview')
@token_required
def preview(user):
    try:
        _, key, rows, selection = workflow.selected(request.get_json(silent=True))
        existing = StatementBatch.query.filter_by(user_id=user.id, source_key=key).first()
        return jsonify(rows=[{k: str(v) if k in ('date','amount') else v for k,v in row.items()} for row in rows],
            existing_id=existing.id if existing else None, conflict=bool(existing and existing.selection_hash != selection))
    except InvalidFieldError as exc:
        return invalid_field_response(exc)


@reconciliation_bp.post('')
@token_required
@online
@mutation_endpoint(StatementBatch)
def create(user):
    name, key, rows, selection = workflow.selected(request.get_json(silent=True))
    lock_imports(user.id)
    existing = StatementBatch.query.filter_by(user_id=user.id, source_key=key).first()
    if existing:
        if existing.selection_hash != selection: workflow.invalid('source_key', 'selectionChanged')
        return jsonify(existing.to_dict())
    batch = StatementBatch(user_id=user.id, name=name, source_key=key, selection_hash=selection)
    batch.transactions = [StatementTransaction(user_id=user.id, fingerprint=digest([key, row['row_number']]), **row) for row in rows]
    db.session.add(batch)
    return saved(batch, 201)


@reconciliation_bp.get('/<int:batch_id>')
@token_required
def detail(user, batch_id):
    return jsonify(workflow.batch_view(owned(user, batch_id)))


@reconciliation_bp.get('/<int:batch_id>/rows/<int:row_id>/candidates')
@token_required
def candidates(user, batch_id, row_id):
    owned(user, batch_id)
    row = StatementTransaction.query.filter_by(id=row_id, batch_id=batch_id, user_id=user.id).first_or_404()
    return jsonify(workflow.candidates(user.id, row, page=max(1, request.args.get('page', 1, type=int)), search=request.args.get('search', '').strip()[:120]))


@reconciliation_bp.put('/<int:batch_id>/rows/<int:row_id>')
@token_required
@online
@mutation_endpoint(StatementBatch, 'batch_id')
def match(user, batch_id, row_id):
    batch = owned(user, batch_id)
    row = StatementTransaction.query.filter_by(id=row_id, batch_id=batch_id, user_id=user.id).first_or_404()
    workflow.replace_matches(user.id, row, request.get_json(silent=True))
    batch.status = 'open'
    return saved(batch)


@reconciliation_bp.post('/<int:batch_id>/complete')
@token_required
@online
@mutation_endpoint(StatementBatch, 'batch_id')
def complete(user, batch_id):
    batch = owned(user, batch_id)
    # Lock referenced entries in the same order as confirmation. An expense
    # edit after commit remains detectable from the stored financial signature.
    from app.models import Entry
    ids = sorted({m.entry_id for row in batch.transactions for m in row.matches if m.entry_id})
    Entry.query.filter(Entry.user_id == user.id, Entry.id.in_(ids)).order_by(Entry.id).with_for_update(of=Entry).all()
    if not workflow.batch_view(batch)['resolved']: workflow.invalid('rows', 'unresolved')
    batch.status = 'reconciled'
    return saved(batch)


@reconciliation_bp.delete('/<int:batch_id>')
@token_required
@online
@mutation_endpoint(StatementBatch, 'batch_id')
def delete(user, batch_id):
    batch = owned(user, batch_id)
    # Remove portable import identities too: they can retain selected row data.
    # Previously saved backup files are separate artifacts, documented in UI.
    from app.models import ImportIdentity, ImportBatch
    targets = {'statement_batches': [batch.id], 'statement_transactions': [r.id for r in batch.transactions],
        'statement_matches': [m.id for r in batch.transactions for m in r.matches]}
    claims = set()
    for kind, ids in targets.items():
        for identity in ImportIdentity.query.filter(ImportIdentity.user_id == user.id, ImportIdentity.entity_kind == kind, ImportIdentity.target_id.in_(ids)):
            claims.add((identity.namespace, kind, identity.source_id))
        ImportIdentity.query.filter(ImportIdentity.user_id == user.id, ImportIdentity.entity_kind == kind, ImportIdentity.target_id.in_(ids)).delete(synchronize_session=False)
    for imported in ImportBatch.query.filter_by(user_id=user.id):
        metadata = dict(imported.metadata_json)
        metadata['records'] = [r for r in metadata.get('records', []) if (metadata.get('namespace'), r['kind'], r['source_id']) not in claims]
        metadata['origins'] = [o for o in metadata.get('origins', []) if (o['namespace'], o['kind'], o['source_id']) not in claims]
        imported.metadata_json = metadata
    db.session.delete(batch); commit_mutation()
    return jsonify(deleted=True)


@reconciliation_bp.get('/<int:batch_id>/summary.csv')
@token_required
def summary(user, batch_id):
    from app.services.csv_io import _fmt
    batch = workflow.batch_view(owned(user, batch_id))
    stream = StringIO(); writer = csv.writer(stream)
    writer.writerow(['row','date','vendor','currency','statement_amount','allocated','remaining','status','exclusion_reason','entry_id','match_amount','match_valid'])
    for row in batch['transactions']:
        for match in row['matches'] or [{}]:
            writer.writerow([row['row_number'], row['date'], _fmt(row['vendor'], 'str'), row['currency'], row['amount'], row['allocated'], row['remaining'], row['status'], _fmt(row['exclusion_reason'], 'str'), match.get('entry_id',''), match.get('amount',''), match.get('valid','')])
    return Response(stream.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename="statement-{batch_id}-summary.csv"', 'Cache-Control': 'no-store'})

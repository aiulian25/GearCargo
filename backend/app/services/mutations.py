"""Atomic operation receipts and optimistic concurrency for record writes.

Participating handlers flush with commit_mutation(); the wrapper commits the
record and the exact HTTP outcome together. Post-commit work is deferred so it
cannot run before that transaction is durable. Legacy online calls remain valid.
"""
from dataclasses import dataclass, field
from functools import wraps
import hashlib
import json
import re

from flask import current_app, g, jsonify, make_response, request, Response
from sqlalchemy import select
from sqlalchemy.orm.exc import StaleDataError

from app import db
from app.models.mutation import MutationOperation
from app.services.domain_validation import validate_payload
from app.utils.entryparse import InvalidFieldError, invalid_field_response


@dataclass
class MutationContext:
    after_commit: list = field(default_factory=list)
    after_rollback: list = field(default_factory=list)


def commit_mutation():
    if getattr(g, 'mutation_context', None) is not None:
        db.session.flush()
    else:
        db.session.commit()


def defer_after_commit(callback):
    context = getattr(g, 'mutation_context', None)
    if context is None:
        return False
    context.after_commit.append(callback)
    return True


def after_rollback(callback):
    context = getattr(g, 'mutation_context', None)
    if context is not None:
        context.after_rollback.append(callback)


def _fingerprint():
    if request.mimetype == 'multipart/form-data':
        files = []
        for key in sorted(request.files):
            for upload in request.files.getlist(key):
                digest = hashlib.sha256()
                while chunk := upload.stream.read(65536):
                    digest.update(chunk)
                upload.stream.seek(0)
                files.append([key, upload.filename, upload.mimetype, digest.hexdigest()])
        body = {'form': sorted((k, request.form.getlist(k)) for k in request.form), 'files': files}
    elif request.is_json:
        body = request.get_json(silent=True)
    else:
        body = request.get_data().hex()
    value = [request.method, request.path, sorted(request.args.lists()), request.headers.get('If-Match'), body]
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _receipt(user_id, key, fingerprint):
    dialect = db.engine.dialect.name
    if dialect == 'postgresql':
        from sqlalchemy.dialects.postgresql import insert
    elif dialect == 'sqlite':
        from sqlalchemy.dialects.sqlite import insert
    else:
        raise RuntimeError('Mutation receipts require PostgreSQL or SQLite')
    statement = insert(MutationOperation).values(user_id=user_id, operation_key=key, fingerprint=fingerprint)
    statement = statement.on_conflict_do_nothing(index_elements=['user_id', 'operation_key']).returning(MutationOperation.id)
    inserted_id = db.session.execute(statement).scalar_one_or_none()
    row = db.session.execute(select(MutationOperation).where(
        MutationOperation.user_id == user_id, MutationOperation.operation_key == key,
    )).scalar_one()
    return row, inserted_id is not None


def _conflict(model, user_id, record_id):
    current = model.query.filter_by(id=record_id, user_id=user_id).first() if record_id is not None else None
    return jsonify({'error': 'This record changed after you opened it. Reload and review before saving.',
                    'code': 'REVISION_CONFLICT', 'current_revision': current.revision if current else None,
                    'current': current.to_dict() if current else None}), 409


def mutation_endpoint(model, id_argument=None):
    def decorate(function):
        @wraps(function)
        def wrapped(current_user, *args, **kwargs):
            key = request.headers.get('Idempotency-Key')
            protocol = request.headers.get('X-GearCargo-Mutation-Version')
            expected = request.headers.get('If-Match')
            if model.__tablename__ == 'vehicles' and request.args.get('hard', '').lower() == 'true':
                if key or protocol or expected:
                    return jsonify({'error': 'Permanent vehicle deletion uses the online recovery workflow.', 'code': 'MUTATION_NOT_SUPPORTED'}), 400
                return function(current_user, *args, **kwargs)

            record_id = kwargs.get(id_argument) if id_argument else None
            if request.headers.get('X-GearCargo-Offline-Owner') and protocol != '1':
                return jsonify({'error': 'Reload GearCargo before sending offline changes.',
                                'code': 'MUTATION_PROTOCOL_REQUIRED'}), 428
            if protocol and protocol != '1':
                return jsonify({'error': 'Unsupported mutation protocol.', 'code': 'MUTATION_PROTOCOL'}), 400
            if key is not None and not re.fullmatch(r'[A-Za-z0-9_-]{16,128}', key):
                return jsonify({'error': 'Invalid operation ID.', 'code': 'INVALID_OPERATION_ID'}), 400
            if protocol and not key:
                return jsonify({'error': 'An operation ID is required.', 'code': 'OPERATION_ID_REQUIRED'}), 400
            if expected is not None and not re.fullmatch(r'"[1-9][0-9]{0,15}"', expected):
                return jsonify({'error': 'Invalid record revision.', 'code': 'INVALID_REVISION'}), 400
            if protocol and record_id is not None and expected is None:
                return jsonify({'error': 'Reload the record before saving.', 'code': 'REVISION_REQUIRED'}), 428
            user_id = current_user.id
            context = MutationContext()
            g.mutation_context = context
            committed = False
            try:
                row = None
                if key:
                    fingerprint = _fingerprint()
                    row, fresh = _receipt(user_id, key, fingerprint)
                    if not fresh:
                        if row.fingerprint != fingerprint:
                            db.session.rollback()
                            return jsonify({'error': 'This operation ID was already used for different content.',
                                            'code': 'OPERATION_KEY_REUSED'}), 409
                        response = Response(row.body, status=row.status, headers=row.headers)
                        response.headers['Idempotent-Replay'] = 'true'
                        db.session.rollback()
                        return response
                if request.is_json and request.method in {'POST', 'PUT', 'PATCH'}:
                    validate_payload(model, request.get_json(silent=True))
                if record_id is not None:
                    # Serialize read/modify/complete operations on PostgreSQL;
                    # ORM version checks also reject concurrent stale flushes.
                    current = model.query.filter_by(id=record_id, user_id=user_id).with_for_update(
                        of=model.__mapper__.base_mapper.local_table).first()
                    if expected is not None and (current is None or current.revision != int(expected[1:-1])):
                        db.session.rollback()
                        return _conflict(model, user_id, record_id)
                response = make_response(function(current_user, *args, **kwargs))
                if response.status_code >= 400:
                    db.session.rollback()
                    return response
                db.session.flush()
                if row is not None:
                    row.status = response.status_code
                    row.body = response.get_data(as_text=True)
                    row.headers = {k: v for k, v in response.headers if k.lower() in {'content-type', 'location', 'etag'}}
                db.session.commit()
                committed = True
                return response
            except InvalidFieldError as exc:
                db.session.rollback()
                return invalid_field_response(exc)
            except StaleDataError:
                db.session.rollback()
                return _conflict(model, user_id, record_id)
            except Exception:
                db.session.rollback()
                raise
            finally:
                g.mutation_context = None
                for callback in context.after_commit if committed else context.after_rollback:
                    try:
                        callback()
                    except Exception:
                        current_app.logger.exception('Post-mutation cleanup failed')
        return wrapped
    return decorate

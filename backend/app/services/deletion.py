"""GC-003: explicit relational deletion and a transactional cleanup outbox.

No file/Redis mutation happens in the deleting transaction. Cleanup reads only
committed tasks through an independent session. All participating application
activity is excluded during deletion/cleanup by the shared restore lease.
"""
from pathlib import Path
import uuid

import click
from flask import current_app
from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from app import db
from app.models import (Attachment, Backup, DeletionTask, User, Vehicle)
from app.services.restore_transaction import activity_guard, digest, sync_dir


class DeletionConflict(ValueError):
    """Data needs repair before deletion can safely proceed."""


def storage_roots():
    from app.routes.backup import get_attachment_folder, get_backup_folder, get_uploads_folder
    return {name: Path(path).absolute() for name, path in (
        ('attachments', get_attachment_folder()), ('uploads', get_uploads_folder()),
        ('backups', get_backup_folder()))}


def safe_path(storage, relative):
    root = storage_roots()[storage]
    path = root / relative
    if not relative or Path(relative).is_absolute() or '..' in Path(relative).parts:
        raise DeletionConflict('Invalid media path. Ask an administrator to repair it before deleting.')
    if root.is_symlink() or path.resolve() == root.resolve() or root.resolve() not in path.resolve().parents:
        raise DeletionConflict('Media path leaves its storage folder. Repair it before deleting.')
    for part in [path, *path.parents]:
        if part == root:
            break
        if part.is_symlink():
            raise DeletionConflict('Linked media paths need administrator review before deletion.')
    return path


def relative_path(storage, value):
    root = storage_roots()[storage]
    path = Path(value)
    if storage == 'uploads' and value.startswith('/uploads/'):
        path = Path(value[len('/uploads/'):])
    if path.is_absolute():
        try:
            path = path.relative_to(root)
        except ValueError:
            raise DeletionConflict('Media path leaves its storage folder. Repair it before deleting.') from None
    safe_path(storage, str(path))
    return str(path)


def queue_file(operation_id, storage, value, seen):
    if not value:
        return
    relative = relative_path(storage, value)
    if (storage, relative) in seen:
        return
    seen.add((storage, relative))
    path = safe_path(storage, relative)
    if not path.exists():
        return
    if not path.is_file():
        raise DeletionConflict('Expected a media file. Ask an administrator to repair this record.')
    db.session.add(DeletionTask(operation_id=operation_id, kind='file', payload={
        'storage': storage, 'path': relative, 'sha256': digest(path),
    }))


def _table(name):
    return db.metadata.tables[name]


def _ids(name, condition):
    table = _table(name)
    return set(db.session.execute(select(table.c.id).where(condition)).scalars())


def _plan(user_id, vehicle_ids, account):
    """Inventory every FK-owned row, including links with no vehicle_id set."""
    chosen = {'vehicles': set(vehicle_ids)}
    for name in ('entries', 'insurance_policies', 'reminders', 'prediction_alerts',
                 'todos', 'attachments', 'notification_logs', 'tire_sets', 'tires', 'tire_fitments', 'tread_readings', 'appointments', 'appointment_tasks', 'appointment_expenses'):
        table = _table(name)
        condition = table.c.vehicle_id.in_(vehicle_ids)
        if account:
            condition = or_(condition, table.c.user_id == user_id)
        chosen[name] = _ids(name, condition)
    for name in ('fuel_entries', 'service_entries', 'repair_entries', 'tax_entries',
                 'parking_entries', 'consumable_entries'):
        chosen[name] = _ids(name, _table(name).c.id.in_(chosen['entries']))
    chosen['statement_matches'] = _ids('statement_matches', _table('statement_matches').c.entry_id.in_(chosen['entries']))
    # Legacy/imported documents and generated reminders can omit vehicle_id.
    chosen['attachments'] |= _ids('attachments', _table('attachments').c.entry_id.in_(chosen['entries']))
    chosen['reminders'] |= _ids('reminders', _table('reminders').c.source_service_id.in_(chosen['service_entries']))
    logs = _table('notification_logs')
    chosen['notification_logs'] |= _ids('notification_logs', or_(
        logs.c.reminder_id.in_(chosen['reminders']), logs.c.prediction_id.in_(chosen['prediction_alerts'])))
    if account:
        chosen['users'] = {user_id}
        for name in ('backups', 'backup_schedules', 'push_subscriptions', 'email_consent_logs',
                     'activity_logs', 'user_sessions', 'report_shares', 'due_dismissals', 'mutation_operations', 'import_identities', 'import_batches', 'calendar_outbox', 'scheduled_effects', 'statement_batches', 'statement_transactions', 'statement_matches'):
            chosen[name] = _ids(name, _table(name).c.user_id == user_id)
        chosen['notification_logs'] |= _ids('notification_logs', logs.c.subscription_id.in_(chosen['push_subscriptions']))
    else:
        kinds = {'todo': 'todos', 'service': 'service_entries', 'tax': 'tax_entries',
                 'insurance': 'insurance_policies', 'document': 'attachments',
                 'parking': 'parking_entries', 'fine': 'parking_entries',
                 'consumable': 'consumable_entries', 'prediction': 'prediction_alerts',
                 'reminder': 'reminders', 'tire_rotation': 'tire_sets', 'tire_tread': 'tire_sets'}
        dismissals = _table('due_dismissals')
        chosen['due_dismissals'] = _ids('due_dismissals', (dismissals.c.user_id == user_id) & or_(
            *((dismissals.c.kind == kind) & dismissals.c.ref_id.in_(chosen[table]) for kind, table in kinds.items())))
    # A malformed cross-owner reference must never turn into an implicit cascade.
    for name, ids in chosen.items():
        table = _table(name)
        if 'user_id' in table.c:
            if db.session.execute(select(table.c.id).where(
                    table.c.id.in_(ids), table.c.user_id.is_not(None), table.c.user_id != user_id)).first():
                raise DeletionConflict('Related records belong to another account. Ask an administrator to repair the links.')
        if not account and 'vehicle_id' in table.c:
            if db.session.execute(select(table.c.id).where(
                    table.c.id.in_(ids), table.c.vehicle_id.is_not(None), ~table.c.vehicle_id.in_(vehicle_ids))).first():
                raise DeletionConflict('Related records belong to another vehicle. Repair the links before deleting.')
    if not account:
        from app.services.attachment_consistency import read_graph, relationship_issues
        issues = relationship_issues(read_graph(db.session.connection(),
            attachment_ids=chosen['attachments'], policy_ids=chosen['insurance_policies']))
        # Legacy omitted vehicle IDs are safe only when every known parent is
        # this vehicle. A contradictory explicit vehicle/owner is never guessed.
        unsafe = [issue for issue in issues if not (
            issue['code'] in ('entry_vehicle_mismatch', 'policy_vehicle_mismatch')
            and issue['vehicle_id'] is None and issue['parent_vehicle_id'] in vehicle_ids)]
        if unsafe:
            raise DeletionConflict('Attachment links disagree with their parents. Review the consistency report before deleting.')
    return chosen


def _check_restrictions(chosen, account):
    """Retain database restrictions, including any future/uninventoried child."""
    for table in db.metadata.tables.values():
        for fk in table.foreign_keys:
            parent_ids = chosen.get(fk.column.table.name, set())
            if not parent_ids:
                continue
            if account and table.name in ('blocked_ips', 'blocked_devices'):
                continue  # Explicitly detached/scrubbed below; these are instance security records.
            remaining = select(table.c.id).where(fk.parent.in_(parent_ids))
            if table.name in chosen:
                remaining = remaining.where(~table.c.id.in_(chosen[table.name]))
            if db.session.execute(remaining).first():
                raise DeletionConflict('Other records still reference this data. Ask an administrator to repair the links before deleting.')


def delete_owned_data(user_id, *, vehicle_id=None, actor_id=None):
    """Commit records and cleanup tasks together; callers own rollback on errors."""
    with activity_guard(exclusive=True):
        return _delete_owned_data(user_id, vehicle_id=vehicle_id, actor_id=actor_id)


def _delete_owned_data(user_id, *, vehicle_id=None, actor_id=None):
    account = vehicle_id is None
    user = db.session.get(User, user_id)
    if user is None:
        raise DeletionConflict('Account no longer exists. Refresh and try again.')
    vehicles = Vehicle.query.filter_by(user_id=user_id)
    if not account:
        vehicles = vehicles.filter_by(id=vehicle_id)
    vehicles = vehicles.all()
    if not account and not vehicles:
        raise DeletionConflict('Vehicle no longer exists. Refresh and try again.')
    chosen = _plan(user_id, [v.id for v in vehicles], account)
    _check_restrictions(chosen, account)
    if not account:
        # Core bulk deletion bypasses ORM flush events; retain remote tombstones.
        from app.services.calendar_outbox import models, enqueue
        for kind, model in models().items():
            for entry in model.query.filter(model.id.in_(chosen.get(model.__tablename__, set()))):
                enqueue(user, kind, entry, 'delete')
    operation_id, seen = uuid.uuid4().hex, set()
    for attachment in Attachment.query.filter(Attachment.id.in_(chosen['attachments'])):
        queue_file(operation_id, 'attachments', attachment.filepath, seen)
    for vehicle in vehicles:
        queue_file(operation_id, 'uploads', vehicle.photo, seen)
    if account:
        for backup in Backup.query.filter(Backup.id.in_(chosen['backups'])):
            queue_file(operation_id, 'backups', backup.filepath, seen)
        for value in [user.avatar, *(user.preferences or {}).get('avatar_history', [])]:
            queue_file(operation_id, 'uploads', value, seen)
        # Include superseded avatars no longer in the bounded history list.
        avatar_folder = safe_path('uploads', f'avatars/{user_id}')
        if avatar_folder.exists():
            for path in avatar_folder.rglob('*'):
                if path.is_file() or path.is_symlink():
                    queue_file(operation_id, 'uploads', str(path), seen)
        db.session.add(DeletionTask(operation_id=operation_id, kind='redis_user', payload={
            'user_id': user_id, 'email': user.email.lower(),
        }))
        for name in ('blocked_ips', 'blocked_devices'):
            table = _table(name)
            # Keep the instance block effective, but erase the deleted target's
            # email and descriptive PII. Actor-only links are simply detached.
            db.session.execute(update(table).where(or_(table.c.target_user_id == user_id,
                table.c.target_email == user.email)).values(target_user_id=None, target_email=None,
                    reason=None, unblock_reason=None))
            for column in ('blocked_by_id', 'unblocked_by_id'):
                db.session.execute(update(table).where(table.c[column] == user_id).values({column: None}))
        # Insert the success audit in THIS transaction, without the deleted PII.
        from app.models import ActivityLog
        for log in ActivityLog.query.filter(ActivityLog.user_id != user_id):
            data = log.extra_data or {}
            if any(data.get(key) == user_id for key in ('created_user_id', 'target_user_id', 'deleted_user_id')):
                log.description = 'Account administration event (deleted account)'
                log.extra_data = {key: value for key, value in data.items() if key not in (
                    'created_user_id', 'target_user_id', 'deleted_user_id', 'deleted_email', 'target_email')}
        db.session.add(ActivityLog(user_id=actor_id, event_type='user_deleted', event_category='admin',
                                   description='Account permanently deleted', success=True))
    else:
        from app.models import ReportShare
        for share in ReportShare.query.filter_by(user_id=user_id):
            if share.vehicle_ids and set(share.vehicle_ids).intersection(chosen['vehicles']):
                share.revoked = True
    # Flush the outbox/audit before issuing ordered Core deletes. Joined-table
    # subclasses must be removed before entries; policy documents after policies.
    db.session.flush()
    order = ('statement_matches', 'statement_transactions', 'statement_batches', 'appointment_expenses', 'appointment_tasks', 'appointments', 'tread_readings', 'tire_fitments', 'tires', 'tire_sets', 'notification_logs', 'due_dismissals', 'reminders', 'prediction_alerts', 'todos',
             'tax_entries', 'fuel_entries', 'service_entries', 'repair_entries', 'parking_entries',
             'consumable_entries', 'insurance_policies', 'attachments', 'entries', 'vehicles',
             'backup_schedules', 'backups', 'push_subscriptions', 'email_consent_logs',
             'activity_logs', 'user_sessions', 'report_shares', 'mutation_operations', 'import_identities', 'import_batches', 'calendar_outbox', 'scheduled_effects', 'users')
    for name in order:
        if chosen.get(name):
            table = _table(name)
            db.session.execute(delete(table).where(table.c.id.in_(chosen[name])))
    db.session.commit()
    db.session.expire_all()
    return operation_id


def _referenced(session, storage, relative):
    """A historical duplicate path must not erase another surviving record."""
    target = safe_path(storage, relative).resolve()
    values = [('attachments', value) for value in session.execute(select(Attachment.filepath)).scalars()]
    values.extend(('backups', value) for value in session.execute(select(Backup.filepath)).scalars())
    values.extend(('uploads', value) for value in session.execute(select(Vehicle.photo)).scalars())
    for avatar, preferences in session.execute(select(User.avatar, User.preferences)):
        values.extend(('uploads', value) for value in [avatar, *(preferences or {}).get('avatar_history', [])])
    for namespace, value in values:
        if value:
            try:
                # Operators can configure overlapping storage roots. Compare
                # actual paths across categories, not just same-kind strings.
                if safe_path(namespace, relative_path(namespace, value)).resolve() == target:
                    return True
            except DeletionConflict:
                continue  # Malformed unrelated record cannot name this safe path.
    return False


def _remove_file(session, payload):
    storage, relative = payload['storage'], payload['path']
    if not storage_roots()[storage].is_dir():
        raise OSError('Media storage is unavailable')
    path = safe_path(storage, relative)
    if _referenced(session, storage, relative):
        return  # Still owned: retain the shared file, retire this cleanup request.
    if not path.exists():
        # A crash/failure can happen after unlink but before the directory fsync.
        # Persist absence before retiring that task, including on this retry.
        if path.parent.is_dir():
            sync_dir(path.parent)
        return
    if not path.is_file() or digest(path) != payload['sha256']:
        raise DeletionConflict('File changed since deletion; operator review required.')
    path.unlink()
    sync_dir(path.parent)


def _remove_redis_user(session, payload):
    from app import redis_client
    user_id = payload['user_id']
    if session.get(User, user_id) is not None:
        raise DeletionConflict('Account identifier reused; operator review required.')
    if redis_client is None:
        if current_app.config.get('REDIS_URL') not in (None, '', 'memory://'):
            raise RuntimeError('Redis unavailable')
        return
    # SCAN stays bounded and every pattern is scoped to this former account.
    for pattern in (f'session:{user_id}:*',):
        for key in redis_client.scan_iter(match=pattern, count=100):
            redis_client.delete(key)
    redis_client.delete(f'known_devices:{user_id}', f'known_locations:{user_id}', f'2fa_pending:{user_id}')
    # A new owner can register the same email while cleanup was pending.
    if not session.execute(select(User.id).where(User.email == payload['email'])).first():
        redis_client.delete(f'failed_login:{payload["email"]}', f'lockout:{payload["email"]}',
                            f'security_answer_attempts:{payload["email"]}')


def cleanup_pending(operation_id=None, limit=100):
    """Retry committed tasks only. Failure retains the task; missing files succeed."""
    with activity_guard(exclusive=True):
        with Session(db.engine) as session:
            statement = select(DeletionTask).order_by(
                DeletionTask.attempts, DeletionTask.created_at, DeletionTask.id).limit(limit)
            if operation_id:
                statement = statement.where(DeletionTask.operation_id == operation_id)
            tasks = session.execute(statement).scalars().all()
            completed = 0
            for task in tasks:
                try:
                    if task.kind == 'file':
                        _remove_file(session, task.payload)
                    elif task.kind == 'redis_user':
                        _remove_redis_user(session, task.payload)
                    else:
                        raise DeletionConflict('Unknown cleanup task kind')
                except Exception as exc:
                    task.attempts += 1
                    task.last_error = type(exc).__name__
                    current_app.logger.warning('Deletion cleanup task %s remains pending (%s)', task.id, task.last_error)
                else:
                    session.delete(task)
                    completed += 1
                session.commit()
            remaining = select(db.func.count()).select_from(DeletionTask)
            if operation_id:
                remaining = remaining.where(DeletionTask.operation_id == operation_id)
            return {'completed': completed, 'pending': session.execute(remaining).scalar_one()}


def finish_cleanup(operation_id):
    """Post-commit errors must never misreport the relational deletion as failed."""
    try:
        result = cleanup_pending(operation_id)
        return {'state': 'pending' if result['pending'] else 'completed', **result}
    except Exception:
        current_app.logger.exception('Committed deletion cleanup will be retried')
        return {'state': 'pending'}


def scheduled_cleanup(app):
    from app.services.restore_transaction import RestoreBusy
    with app.app_context():
        try:
            cleanup_pending()
        except RestoreBusy:
            return  # Retry next interval; never interrupt restore or active work.
        except Exception:
            app.logger.exception('Deletion cleanup deferred')


def init_deletion_cleanup(app):
    @app.cli.command('cleanup-deleted-files')
    @click.option('--limit', type=click.IntRange(1, 10000), default=100)
    def cleanup_command(limit):
        """Retry committed file/account cleanup; pending tasks cause a nonzero exit."""
        try:
            result = cleanup_pending(limit=limit)
        except Exception as exc:
            raise click.ClickException('Cleanup unavailable; check application logs and restore status.') from exc
        click.echo(f"Completed: {result['completed']}; pending: {result['pending']}")
        if result['pending']:
            raise click.ClickException('Cleanup remains pending. Check storage/Redis availability and retry.')

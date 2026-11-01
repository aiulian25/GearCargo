"""Transactional calendar intents; remote work runs only in the bounded worker.

Rows coalesce edits but retain an in-flight lease. The worker acknowledges only
the generation it sent, so an edit/delete during transport remains pending.
Credentials stay encrypted in user settings, never in jobs or error messages.
"""
from collections import Counter
from datetime import datetime, timedelta
import hashlib
import json
from uuid import uuid4

from sqlalchemy import case, event, func, inspect, or_, select, update
from sqlalchemy.orm import Session

from app import db
from app.models.calendar_outbox import CalendarOutbox
from app.utils.timeutils import isoformat_utc, utc_naive_now

LEASE = timedelta(minutes=5)
MAX_ATTEMPTS = 8


def models():
    from app.models import FuelEntry, ServiceEntry, RepairEntry, InsurancePolicy, TaxEntry, ParkingEntry, Reminder, Appointment
    return dict(fuel=FuelEntry, service=ServiceEntry, repair=RepairEntry, insurance=InsurancePolicy,
                tax=TaxEntry, parking=ParkingEntry, reminder=Reminder, appointment=Appointment)


def source_key(source):
    fields = [source.get(key) or '' for key in ('id', 'provider', 'url', 'username', 'calendar_id')]
    return hashlib.sha256(json.dumps(fields).encode()).hexdigest()


def enqueue(user, kind, entry, action='update', *, session=None, force=False):
    from app.services.calendar_service import get_event_data_for_entry, get_user_calendar_sources
    session = session or db.session
    if kind not in models() or entry.user_id != user.id:
        return 0
    if kind == 'reminder' and entry.reminder_type == 'workshop_preparation':
        return 0  # The appointment owns the single timed calendar event.
    vehicle = getattr(entry, 'vehicle', None)
    if vehicle and vehicle.user_id != user.id:
        return 0
    operation = 'delete' if action == 'delete' or (kind == 'appointment' and entry.status == 'cancelled') or (kind == 'reminder' and (entry.completed or entry.dismissed)) else 'upsert'
    data = None if operation == 'delete' else get_event_data_for_entry(kind, entry, vehicle.full_name if vehicle else '')
    if operation == 'upsert' and not data:
        operation = 'delete'  # Date removed: retire the previous calendar event.
    payload = {key: value.isoformat() if isinstance(value, datetime) else value for key, value in data.items()} if data else None
    checksum = hashlib.sha256(json.dumps([operation, payload], sort_keys=True).encode()).hexdigest()
    table = CalendarOutbox.__table__
    connection = session.connection()
    if connection.dialect.name == 'postgresql':
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    count = 0
    for source in get_user_calendar_sources(user):
        key = source_key(source)
        existing = connection.execute(select(table.c.id).where(table.c.user_id == user.id,
            table.c.source_key == key, table.c.entry_type == kind, table.c.entry_id == entry.id)).first()
        if operation != 'delete' and not existing and (not user.calendar_enabled or not source['enabled'] or (vehicle and vehicle.archived)):
            continue
        now = utc_naive_now()
        values = dict(user_id=user.id, source_id=source['id'], source_key=key, entry_type=kind, entry_id=entry.id,
            vehicle_id=entry.vehicle_id, uid=f'gearcargo-{kind}-{entry.id}@gearcargo.local', operation=operation,
            payload=payload, payload_hash=checksum, generation=1, revision=1, status='pending', attempts=0,
            next_attempt_at=now, created_at=now, updated_at=now)
        live = (table.c.status == 'sending') & (table.c.lease_until > now)
        statement = insert(table).values(**values).on_conflict_do_update(
            index_elements=['user_id', 'source_key', 'entry_type', 'entry_id'],
            set_=dict(operation=operation, payload=payload, payload_hash=checksum, vehicle_id=entry.vehicle_id,
                generation=table.c.generation + 1, revision=table.c.revision + 1,
                status=case((live, 'sending'), else_='pending'), attempts=0, next_attempt_at=now,
                last_error=None, updated_at=now),
            where=(table.c.payload_hash != checksum) | table.c.status.in_(['failed', 'cancelled', 'paused']) | force)
        count += connection.execute(statement).rowcount
    return count


def enqueue_all(user, *, session=None, force=True):
    from app.services.vehicle_archive import active_vehicle_condition
    session = session or db.session
    count = 0
    for kind, model in models().items():
        for entry in session.query(model).filter(model.user_id == user.id, active_vehicle_condition(model)).yield_per(200):
            count += enqueue(user, kind, entry, session=session, force=force)
    return count


@event.listens_for(Session, 'before_flush')
def track_entries(session, context, instances):
    from app.models import Vehicle
    kinds = models()
    pending = session.info.setdefault('calendar_entries', {})
    for record in session.new | session.dirty | session.deleted:
        for kind, model in kinds.items():
            if isinstance(record, model) and (record in session.new or record in session.deleted or session.is_modified(record, include_collections=False)):
                pending[id(record)] = (kind, record, 'delete' if record in session.deleted else 'update')
                break
        if isinstance(record, Vehicle) and record not in session.new and record not in session.deleted:
            state = inspect(record)
            if any(state.attrs[field].history.has_changes() for field in ('archived', 'name', 'make', 'model', 'year')):
                session.info.setdefault('calendar_vehicles', set()).add(record.id)


@event.listens_for(Session, 'after_flush_postexec')
def persist_entries(session, context):
    from app.models import User, Vehicle
    pending = session.info.pop('calendar_entries', {})
    for vehicle_id in session.info.pop('calendar_vehicles', set()):
        vehicle = session.get(Vehicle, vehicle_id)
        if vehicle and not vehicle.archived:
            for kind, model in models().items():
                for entry in session.query(model).filter_by(vehicle_id=vehicle.id, user_id=vehicle.user_id):
                    pending[id(entry)] = (kind, entry, 'update')
    for kind, entry, action in pending.values():
        user = session.get(User, entry.user_id)
        if user:
            enqueue(user, kind, entry, action, session=session)


@event.listens_for(Session, 'after_soft_rollback')
def clear_entries(session, transaction):
    session.info.pop('calendar_entries', None)
    session.info.pop('calendar_vehicles', None)


def resolve_source(user, job):
    from app.services.calendar_service import get_user_calendar_sources
    return next((source for source in get_user_calendar_sources(user, include_secrets=True)
                 if source['id'] == job.source_id and source_key(source) == job.source_key), None)


def cancel_removed_sources(user):
    from app.services.calendar_service import get_user_calendar_sources
    keys = [source_key(source) for source in get_user_calendar_sources(user)]
    db.session.execute(update(CalendarOutbox).where(CalendarOutbox.user_id == user.id,
        CalendarOutbox.source_key.not_in(keys)).values(status='cancelled', lease_token=None,
            lease_until=None, payload=None, last_error='source_removed', revision=CalendarOutbox.revision + 1))


def claim(job_id, now):
    from app.models import User, Vehicle
    for _ in range(5):
        job = db.session.get(CalendarOutbox, job_id, populate_existing=True)
        if not job or job.status not in ('pending', 'retry', 'sending') or job.next_attempt_at > now:
            return None
        if job.status == 'sending' and job.lease_until and job.lease_until > now:
            return None
        user = db.session.get(User, job.user_id, populate_existing=True)
        source = resolve_source(user, job) if user else None
        vehicle = db.session.get(Vehicle, job.vehicle_id) if job.vehicle_id else None
        state = None
        if not source:
            state = 'cancelled'
        elif not user.is_active or not user.calendar_enabled or not source['enabled'] or (job.operation != 'delete' and vehicle and vehicle.archived):
            state = 'paused'
        if state:
            db.session.execute(update(CalendarOutbox).where(CalendarOutbox.id == job.id, CalendarOutbox.revision == job.revision)
                .values(status=state, revision=CalendarOutbox.revision + 1, lease_token=None, lease_until=None))
            db.session.commit()
            return None
        token = str(uuid4())
        changed = db.session.execute(update(CalendarOutbox).where(CalendarOutbox.id == job.id,
            CalendarOutbox.revision == job.revision).values(status='sending', attempts=job.attempts + 1,
                lease_token=token, lease_until=now + LEASE, revision=CalendarOutbox.revision + 1),
            execution_options={'synchronize_session': False}).rowcount
        snapshot = dict(id=job.id, generation=job.generation, token=token, operation=job.operation,
                        payload=job.payload, uid=job.uid, user_id=job.user_id, source=source)
        db.session.commit()
        if changed:
            return snapshot
    return None


def finish(claimed, accepted, now):
    from app.models import User
    job = db.session.get(CalendarOutbox, claimed['id'], populate_existing=True)
    if not job:
        return
    if job.lease_token != claimed['token']:
        # An expired consumer may finish transport after a newer generation was
        # acknowledged (even a failed response can follow an accepted PUT).
        # Atomically requeue the latest state without reviving removed sources.
        live = (CalendarOutbox.status == 'sending') & (CalendarOutbox.lease_until > now)
        db.session.execute(update(CalendarOutbox).where(CalendarOutbox.id == job.id,
            CalendarOutbox.generation != claimed['generation'], CalendarOutbox.status != 'cancelled',
            or_(CalendarOutbox.lease_token.is_(None), CalendarOutbox.lease_token != claimed['token']))
            .values(status=case((live, 'sending'), else_='pending'), generation=CalendarOutbox.generation + 1,
                revision=CalendarOutbox.revision + 1, attempts=0, next_attempt_at=now,
                last_error=None, updated_at=now), execution_options={'synchronize_session': False})
        db.session.commit()
        return
    newer = job.generation != claimed['generation']
    state = 'pending' if newer else 'synced' if accepted else 'failed' if job.attempts >= MAX_ATTEMPTS else 'retry'
    values = dict(status=state, lease_token=None, lease_until=None, revision=CalendarOutbox.revision + 1,
        last_error=None if accepted or newer else 'provider_unavailable', updated_at=now,
        next_attempt_at=now if newer or accepted else now + timedelta(minutes=min(60, 2 ** min(job.attempts - 1, 6))))
    if accepted and not newer:
        values['synced_at'] = now
    changed = db.session.execute(update(CalendarOutbox).where(CalendarOutbox.id == job.id, CalendarOutbox.revision == job.revision,
        CalendarOutbox.lease_token == claimed['token']).values(**values), execution_options={'synchronize_session': False}).rowcount
    if changed and accepted and not newer:
        db.session.execute(update(User).where(User.id == job.user_id,
            or_(User.calendar_last_sync.is_(None), User.calendar_last_sync < now)).values(calendar_last_sync=now))
    db.session.commit()


def process_calendar_outbox(app, limit=50):
    from app.services.restore_transaction import guarded_app_context
    from app.services.calendar_service import CalendarService
    from app.models import User
    with guarded_app_context(app):
        now = utc_naive_now()
        eligible = (CalendarOutbox.status.in_(['pending', 'retry']) | ((CalendarOutbox.status == 'sending') & (CalendarOutbox.lease_until <= now))) & (CalendarOutbox.next_attempt_at <= now)
        sources = db.session.query(CalendarOutbox.source_key).filter(eligible).group_by(CalendarOutbox.source_key).order_by(func.min(CalendarOutbox.next_attempt_at)).limit(limit).all()
        attempted = 0
        for (key,) in sources:
            ids = db.session.query(CalendarOutbox.id).filter(eligible, CalendarOutbox.source_key == key).order_by(CalendarOutbox.next_attempt_at, CalendarOutbox.id).limit(min(5, limit - attempted)).all()
            for (job_id,) in ids:
                claimed = claim(job_id, now)
                if not claimed:
                    continue
                attempted += 1
                try:
                    user = db.session.get(User, claimed['user_id'])
                    service = CalendarService(user, claimed['source'])
                    if claimed['operation'] == 'delete':
                        accepted, _ = service.delete_event(claimed['uid'])
                    else:
                        payload = dict(claimed['payload'])
                        for field in ('start', 'end'):
                            if payload.get(field): payload[field] = datetime.fromisoformat(payload[field])
                        accepted, _ = service.update_event(claimed['uid'], **payload)
                except Exception:
                    db.session.rollback()
                    accepted = False
                finish(claimed, accepted, utc_naive_now())
                if not accepted:
                    break  # A failing provider cannot consume the whole batch.
            if attempted >= limit:
                break
        return attempted


def retry_pending(user, source_id=None):
    query = db.session.query(CalendarOutbox).filter(CalendarOutbox.user_id == user.id,
        CalendarOutbox.status.in_(['retry', 'failed', 'paused']))
    if source_id:
        query = query.filter(CalendarOutbox.source_id == source_id)
    return query.update(dict(status='pending', attempts=0, next_attempt_at=utc_naive_now(), last_error=None,
                             revision=CalendarOutbox.revision + 1), synchronize_session=False)


def sync_status(user):
    from app.services.calendar_service import get_user_calendar_sources
    sources = []
    total = Counter()
    for source in get_user_calendar_sources(user):
        rows = db.session.query(CalendarOutbox.status, func.count(CalendarOutbox.id), func.min(CalendarOutbox.next_attempt_at)).filter_by(user_id=user.id, source_key=source_key(source)).group_by(CalendarOutbox.status).all()
        counts = Counter({state: count for state, count, _ in rows})
        total.update(counts)
        next_try = min((when for state, _, when in rows if state == 'retry'), default=None)
        sources.append(dict(id=source['id'], name=source['name'], enabled=bool(source['enabled'] and user.calendar_enabled),
            pending=counts['pending'] + counts['sending'], retrying=counts['retry'], failed=counts['failed'],
            synced=counts['synced'], paused=counts['paused'], next_attempt_at=isoformat_utc(next_try)))
    pending = total['pending'] + total['sending'] + total['retry']
    state = 'running' if pending else 'failed' if total['failed'] else 'paused' if total['paused'] else 'done' if total else 'idle'
    return dict(status=state, pending=pending, synced=total['synced'], failed=total['failed'], paused=total['paused'],
                sources=sources, errors=['provider_unavailable'] if total['failed'] else [])


def init_calendar_outbox(app):
    import click

    @app.cli.command('process-calendar-outbox')
    @click.option('--limit', type=click.IntRange(1, 500), default=50)
    def drain(limit):
        """Process one bounded batch; safe alongside scheduler consumers."""
        click.echo(f'Attempted {process_calendar_outbox(app, limit)} calendar operations.')

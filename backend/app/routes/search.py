"""
GearCargo - Global Search Route

GET /api/search?q=<query>
ILIKE search across vehicles, entries (all types, including service garage name,
parking location, fuel station, consumable brand, tax reference number, and
repair diagnosis/symptoms), reminders, insurance policies, todos, and attachment
OCR text. All results are strictly scoped to the authenticated user's data only.

Security notes:
  - Input sanitised: control characters stripped, length capped at 100 chars.
  - All queries filter by current_user.id — cross-user data leakage is impossible.
  - SQLAlchemy .ilike() uses parameterised queries — no SQL injection risk.
  - Rate-limited in create_app() (30/minute/user via _ai_rate_key).
"""
import re

from flask import Blueprint, request, jsonify

from app import db
from app.models import (
    Vehicle, Entry, Attachment, Reminder, InsurancePolicy,
    ServiceEntry, ParkingEntry, FuelEntry, ConsumableEntry,
    TaxEntry, RepairEntry, Todo,
)
from app.routes.auth import token_required

search_bp = Blueprint('search', __name__)

_MAX_Q_LEN = 100   # characters — hard cap, returns 400 above this
_MIN_Q_LEN = 2     # characters — returns empty results below this (no DB hit)
_MAX_PER_GROUP = 20  # max rows returned per category


def _sanitize_q(raw: str) -> str:
    """Strip control characters and leading/trailing whitespace from the query."""
    q = (raw or '').strip()
    # Remove ASCII control characters (null bytes, CR/LF, escape, etc.)
    # Defence-in-depth: LIKE patterns with these chars could affect log parsing.
    q = re.sub(r'[\x00-\x1f\x7f]', '', q)
    return q


@search_bp.route('', methods=['GET'])
@token_required
def global_search(current_user):
    """Full-text ILIKE search across the current user's data."""
    raw_q = request.args.get('q', '')
    q = _sanitize_q(raw_q)

    if len(q) > _MAX_Q_LEN:
        return jsonify({'error': 'Search query too long (max 100 characters)'}), 400

    # Return empty result set without hitting the DB for very short queries.
    if len(q) < _MIN_Q_LEN:
        return jsonify({
            'query': q,
            'results': {
                'vehicles': [], 'entries': [], 'attachments': [],
                'reminders': [], 'insurance': [], 'todos': [],
            },
            'total': 0,
        })

    pattern = f'%{q}%'
    uid = current_user.id

    # ── Vehicles ────────────────────────────────────────────────────────────
    vehicles = Vehicle.query.filter(
        Vehicle.user_id == uid,
        Vehicle.archived == False,  # noqa: E712 — SQLAlchemy requires ==
        db.or_(
            Vehicle.name.ilike(pattern),
            Vehicle.make.ilike(pattern),
            Vehicle.model.ilike(pattern),
            Vehicle.license_plate.ilike(pattern),
            Vehicle.vin.ilike(pattern),
        )
    ).limit(_MAX_PER_GROUP).all()

    # ── Entries (all types via base Entry table with polymorphism) ────────────
    # Base common columns match on the Entry table directly; subtype "place"
    # columns (service garage, parking location) live on the joined subclass
    # tables, so we collect matching ids from each and load them polymorphically
    # in one final query — this keeps result objects the correct concrete type.
    base_ids = {
        row.id for row in db.session.query(Entry.id).filter(
            Entry.user_id == uid,
            db.or_(
                Entry.title.ilike(pattern),
                Entry.description.ilike(pattern),
                Entry.notes.ilike(pattern),
            )
        ).limit(_MAX_PER_GROUP).all()
    }
    service_ids = {
        row.id for row in db.session.query(ServiceEntry.id).filter(
            ServiceEntry.user_id == uid,
            ServiceEntry.garage_name.ilike(pattern),
        ).limit(_MAX_PER_GROUP).all()
    }
    parking_ids = {
        row.id for row in db.session.query(ParkingEntry.id).filter(
            ParkingEntry.user_id == uid,
            ParkingEntry.location.ilike(pattern),
        ).limit(_MAX_PER_GROUP).all()
    }
    # Subtype-specific place/identifier columns not present on the base Entry
    # table — fuel station, consumable brand, tax reference, repair diagnosis /
    # symptoms. Collected per-table and merged so a hit on any of them surfaces
    # the entry with its correct concrete type (F49).
    fuel_ids = {
        row.id for row in db.session.query(FuelEntry.id).filter(
            FuelEntry.user_id == uid,
            FuelEntry.station.ilike(pattern),
        ).limit(_MAX_PER_GROUP).all()
    }
    consumable_ids = {
        row.id for row in db.session.query(ConsumableEntry.id).filter(
            ConsumableEntry.user_id == uid,
            ConsumableEntry.brand.ilike(pattern),
        ).limit(_MAX_PER_GROUP).all()
    }
    tax_ids = {
        row.id for row in db.session.query(TaxEntry.id).filter(
            TaxEntry.user_id == uid,
            TaxEntry.reference_number.ilike(pattern),
        ).limit(_MAX_PER_GROUP).all()
    }
    repair_ids = {
        row.id for row in db.session.query(RepairEntry.id).filter(
            RepairEntry.user_id == uid,
            db.or_(
                RepairEntry.diagnosis.ilike(pattern),
                RepairEntry.symptoms.ilike(pattern),
            ),
        ).limit(_MAX_PER_GROUP).all()
    }
    entry_ids = (base_ids | service_ids | parking_ids
                 | fuel_ids | consumable_ids | tax_ids | repair_ids)
    entries = (
        Entry.query.filter(Entry.id.in_(entry_ids))
        .order_by(Entry.date.desc()).limit(_MAX_PER_GROUP).all()
        if entry_ids else []
    )

    vehicle_map: dict[int, str] = {}

    # ── Reminders (title + description) ───────────────────────────────────────
    reminders = Reminder.query.filter(
        Reminder.user_id == uid,
        db.or_(
            Reminder.title.ilike(pattern),
            Reminder.description.ilike(pattern),
        )
    ).order_by(Reminder.due_date.desc()).limit(_MAX_PER_GROUP).all()

    # ── Insurance policies (provider + policy number) ─────────────────────────
    policies = InsurancePolicy.query.filter(
        InsurancePolicy.user_id == uid,
        db.or_(
            InsurancePolicy.provider.ilike(pattern),
            InsurancePolicy.policy_number.ilike(pattern),
        )
    ).order_by(InsurancePolicy.end_date.desc()).limit(_MAX_PER_GROUP).all()

    # ── Todos (title + description) ──────────────────────────────────────────
    todos = Todo.query.filter(
        Todo.user_id == uid,
        db.or_(
            Todo.title.ilike(pattern),
            Todo.description.ilike(pattern),
        )
    ).order_by(Todo.due_date.desc().nullslast()).limit(_MAX_PER_GROUP).all()

    # ── Attachments (OCR text + filename + description) ──────────────────────
    attachments = Attachment.query.filter(
        Attachment.user_id == uid,
        db.or_(
            Attachment.ocr_text.ilike(pattern),
            Attachment.original_filename.ilike(pattern),
            Attachment.description.ilike(pattern),
        )
    ).order_by(Attachment.created_at.desc()).limit(_MAX_PER_GROUP).all()

    # Build vehicle_map for entry / attachment / reminder / insurance labels
    all_vehicle_ids = (
        {e.vehicle_id for e in entries}
        | {a.vehicle_id for a in attachments if a.vehicle_id}
        | {r.vehicle_id for r in reminders if r.vehicle_id}
        | {p.vehicle_id for p in policies if p.vehicle_id}
        | {td.vehicle_id for td in todos if td.vehicle_id}
    )
    if all_vehicle_ids:
        vehicle_map = {
            v.id: v.name
            for v in Vehicle.query.filter(
                Vehicle.id.in_(all_vehicle_ids),
                Vehicle.user_id == uid,  # redundant but belt-and-suspenders
            ).all()
        }

    def _entry_result(e: Entry) -> dict:
        return {
            'id': e.id,
            'type': e.type,
            'title': e.title or e.description or '',
            'date': e.date.isoformat() if e.date else None,
            'amount': float(e.amount) if e.amount else None,
            'currency': e.currency,
            'vehicle_id': e.vehicle_id,
            'vehicle_name': vehicle_map.get(e.vehicle_id),
        }

    def _attachment_result(a: Attachment) -> dict:
        """Return attachment metadata plus a short OCR snippet around the match."""
        snippet = None
        if a.ocr_text:
            idx = a.ocr_text.lower().find(q.lower())
            if idx >= 0:
                start = max(0, idx - 60)
                end = min(len(a.ocr_text), idx + 60)
                snippet = (
                    ('…' if start > 0 else '')
                    + a.ocr_text[start:end]
                    + ('…' if end < len(a.ocr_text) else '')
                )
        return {
            'id': a.id,
            'filename': a.original_filename or a.filename,
            'category': a.category,
            'has_ocr': bool(a.ocr_text),
            'ocr_snippet': snippet,
            'vehicle_id': a.vehicle_id,
            'vehicle_name': vehicle_map.get(a.vehicle_id) if a.vehicle_id else None,
            'entry_id': a.entry_id,
        }

    def _reminder_result(r: Reminder) -> dict:
        return {
            'id': r.id,
            'title': r.title,
            'due_date': r.due_date.isoformat() if r.due_date else None,
            'reminder_type': r.reminder_type,
            'vehicle_id': r.vehicle_id,
            'vehicle_name': vehicle_map.get(r.vehicle_id) if r.vehicle_id else None,
        }

    def _insurance_result(p: InsurancePolicy) -> dict:
        return {
            'id': p.id,
            'provider': p.provider,
            'policy_number': p.policy_number,
            'end_date': p.end_date.isoformat() if p.end_date else None,
            'vehicle_id': p.vehicle_id,
            'vehicle_name': vehicle_map.get(p.vehicle_id) if p.vehicle_id else None,
        }

    def _todo_result(td: Todo) -> dict:
        return {
            'id': td.id,
            'title': td.title,
            'due_date': td.due_date.isoformat() if td.due_date else None,
            'priority': td.priority,
            'completed': bool(td.completed),
            'vehicle_id': td.vehicle_id,
            'vehicle_name': vehicle_map.get(td.vehicle_id) if td.vehicle_id else None,
        }

    results = {
        'vehicles': [
            {
                'id': v.id,
                'name': v.name,
                'make': v.make,
                'model': v.model,
                'year': v.year,
                'license_plate': v.license_plate,
            }
            for v in vehicles
        ],
        'entries': [_entry_result(e) for e in entries],
        'reminders': [_reminder_result(r) for r in reminders],
        'insurance': [_insurance_result(p) for p in policies],
        'todos': [_todo_result(td) for td in todos],
        'attachments': [_attachment_result(a) for a in attachments],
    }

    return jsonify({
        'query': q,
        'results': results,
        'total': (len(vehicles) + len(entries) + len(reminders)
                  + len(policies) + len(todos) + len(attachments)),
    })

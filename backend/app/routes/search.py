"""
GearCargo - Global Search Route

GET /api/search?q=<query>
ILIKE search across vehicles, entries (all types), and attachment OCR text.
All results are strictly scoped to the authenticated user's data only.

Security notes:
  - Input sanitised: control characters stripped, length capped at 100 chars.
  - All queries filter by current_user.id — cross-user data leakage is impossible.
  - SQLAlchemy .ilike() uses parameterised queries — no SQL injection risk.
  - Rate-limited in create_app() (30/minute/user via _ai_rate_key).
"""
import re

from flask import Blueprint, request, jsonify

from app import db
from app.models import Vehicle, Entry, Attachment
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
            'results': {'vehicles': [], 'entries': [], 'attachments': []},
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
    entries = Entry.query.filter(
        Entry.user_id == uid,
        db.or_(
            Entry.title.ilike(pattern),
            Entry.description.ilike(pattern),
            Entry.notes.ilike(pattern),
        )
    ).order_by(Entry.date.desc()).limit(_MAX_PER_GROUP).all()

    # Fetch vehicle names in one query to avoid N+1
    vehicle_ids = {e.vehicle_id for e in entries}
    vehicle_ids.update(a.vehicle_id for a in [])  # placeholder; extended below
    vehicle_map: dict[int, str] = {}

    # ── Attachments (OCR text + filename + description) ──────────────────────
    attachments = Attachment.query.filter(
        Attachment.user_id == uid,
        db.or_(
            Attachment.ocr_text.ilike(pattern),
            Attachment.original_filename.ilike(pattern),
            Attachment.description.ilike(pattern),
        )
    ).order_by(Attachment.created_at.desc()).limit(_MAX_PER_GROUP).all()

    # Build vehicle_map for entry / attachment labels
    all_vehicle_ids = (
        {e.vehicle_id for e in entries}
        | {a.vehicle_id for a in attachments if a.vehicle_id}
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
        'attachments': [_attachment_result(a) for a in attachments],
    }

    return jsonify({
        'query': q,
        'results': results,
        'total': len(vehicles) + len(entries) + len(attachments),
    })

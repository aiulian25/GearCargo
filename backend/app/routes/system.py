"""System / build-metadata endpoint.

Exposes the image's build manifest (baked at Docker build time into
``/app/build-info.json``) so the running PWA can detect a newer published build
and tell a feature update (``git_sha`` changed) apart from a weekly OS-security
rebuild (same ``git_sha``, newer ``build_date``).

When ``UPDATE_CHECK_ENABLED`` is set, the response also carries ``latest_release``
— the newest version published on GitHub — so version-pinned deployments (which
never see the git_sha/build_date change) can still surface that a newer release
exists. This is opt-in to preserve the default no-phone-home posture.

Authenticated on purpose: build/package details are only returned to signed-in
users, so anonymous scanners can't fingerprint the exact OS package versions.
"""
import os
import re
import json
import time

import requests
from flask import Blueprint, jsonify, current_app, request

from app.routes.auth import token_required

system_bp = Blueprint('system', __name__)

# Parsed once per process — the manifest is static for the life of the container.
_BUILD_INFO_CACHE = None

# GitHub latest-release cache. Server-side so GitHub is queried at most a few
# times a day regardless of how many clients poll /api/app-version.
_GITHUB_API = 'https://api.github.com'
_RELEASE_REPO_RE = re.compile(r'^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$')
_RELEASE_TTL = 6 * 3600          # cache a successful lookup for 6h
_RELEASE_TTL_MISS = 900          # cache a failure for 15 min (avoid hammering)
_release_fallback = {'ts': 0.0, 'data': None}   # in-process fallback when no Redis


def _load_build_info():
    global _BUILD_INFO_CACHE
    if _BUILD_INFO_CACHE is not None:
        return _BUILD_INFO_CACHE

    path = os.environ.get('BUILD_INFO_PATH', '/app/build-info.json')
    # Dev / missing file → neutral defaults so the frontend reads "up to date".
    data = {'version': '0.0.0', 'git_sha': 'dev', 'build_date': '', 'patched_packages': []}
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            loaded = json.load(fh)
        if isinstance(loaded, dict):
            data = {
                'version': str(loaded.get('version') or '0.0.0'),
                'git_sha': str(loaded.get('git_sha') or 'dev'),
                'build_date': str(loaded.get('build_date') or ''),
                'patched_packages': [str(p) for p in (loaded.get('patched_packages') or [])][:120],
            }
    except (FileNotFoundError, ValueError, OSError):
        pass

    _BUILD_INFO_CACHE = data
    return data


def _get_redis():
    """Shared app Redis client, or None (imported lazily like other routes)."""
    try:
        from app import redis_client
        return redis_client
    except Exception:
        return None


def _fetch_latest_release():
    """Return ``{'version', 'url', 'published_at'}`` for the configured repo's
    latest GitHub release, or ``None``.

    Server-side and heavily cached (Redis preferred, else a per-process fallback).
    Never raises — any failure degrades to ``None`` so the update UI simply omits
    the "newer release" hint. The only host contacted is api.github.com and the
    repo comes from config (validated), never from user input, so there is no
    SSRF surface.
    """
    repo = current_app.config.get('UPDATE_CHECK_REPO', '') or ''
    if not _RELEASE_REPO_RE.match(repo):
        return None

    key = f'latest_release:{repo}'
    now = time.time()
    rc = _get_redis()

    # --- cache read ---
    if rc is not None:
        try:
            raw = rc.get(key)
            if raw is not None:
                return json.loads(raw) or None
        except Exception:
            pass
    elif _release_fallback['data'] is not None and now - _release_fallback['ts'] < _RELEASE_TTL:
        return _release_fallback['data']

    # --- miss → query GitHub ---
    data = None
    try:
        resp = requests.get(
            f'{_GITHUB_API}/repos/{repo}/releases/latest',
            headers={'Accept': 'application/vnd.github+json',
                     'User-Agent': 'GearCargo-update-check'},
            timeout=5,
        )
        if resp.status_code == 200:
            j = resp.json()
            tag = (j.get('tag_name') or '').lstrip('vV')
            if tag:
                data = {
                    'version': tag,
                    'url': j.get('html_url') or '',
                    'published_at': j.get('published_at') or '',
                }
    except Exception as e:
        current_app.logger.debug(f'latest-release check failed: {e}')

    # --- cache write (short TTL on failure so we retry sooner) ---
    ttl = _RELEASE_TTL if data else _RELEASE_TTL_MISS
    if rc is not None:
        try:
            rc.setex(key, ttl, json.dumps(data))
        except Exception:
            pass
    else:
        _release_fallback['ts'] = now
        _release_fallback['data'] = data
    return data


@system_bp.route('/app-version', methods=['GET'])
@token_required
def app_version(current_user):
    """Return the running image's build manifest (version, git_sha, build_date,
    patched_packages) so the client can detect updates. Includes ``latest_release``
    when the optional GitHub update check is enabled."""
    data = dict(_load_build_info())
    if current_app.config.get('UPDATE_CHECK_ENABLED', False):
        rel = _fetch_latest_release()
        if rel:
            data['latest_release'] = rel
    return jsonify(data)


@system_bp.route('/due', methods=['GET'])
@token_required
def get_due_surface(current_user):
    """Unified "Due & Expiring" list (F4).

    Merges overdue+upcoming reminders, service next-due, tax/insurance/document
    expiry, parking-permit expiry, and consumable replacement into one ranked
    feed, each item deep-linking to its record. Scoped to the current user.

    Query: ``?days=30`` sets the forward horizon (clamped to 1..365). Overdue
    items are always included.
    """
    days = request.args.get('days', 30, type=int) or 30
    days = max(1, min(days, 365))

    from app.services.due import build_due_items
    items = build_due_items(current_user.id, days=days)
    return jsonify({'items': items, 'count': len(items)})


# Kinds a user may dismiss from the "Coming up" feed. Must stay in sync with
# the kinds emitted by app.services.due.build_due_items.
_DISMISSIBLE_KINDS = frozenset((
    'reminder', 'service', 'tax', 'insurance', 'document',
    'parking', 'fine', 'consumable',
))


def _resolve_due_ref(user, kind, ref_id):
    """Resolve a due-feed item back to its OWNED source record.

    Returns ``(obj, effective_due_date)`` — ``(None, None)`` when the record
    does not exist or does not belong to ``user`` (callers answer 404 either
    way, so ownership is never disclosed). The effective due date mirrors
    build_due_items' per-kind date so a dismissal pins exactly the occurrence
    the user saw; it is always computed server-side, never taken from the
    client.
    """
    from app.models import (
        Reminder, ServiceEntry, TaxEntry, InsurancePolicy,
        Attachment, ParkingEntry, ConsumableEntry,
    )

    if kind == 'reminder':
        obj = Reminder.query.filter_by(id=ref_id, user_id=user.id).first()
        return obj, (obj.due_date if obj else None)
    if kind == 'service':
        obj = ServiceEntry.query.filter_by(id=ref_id, user_id=user.id).first()
        return obj, (obj.next_due_date if obj else None)
    if kind == 'tax':
        obj = TaxEntry.query.filter_by(id=ref_id, user_id=user.id).first()
        return obj, ((obj.next_due_date or obj.due_date) if obj else None)
    if kind == 'insurance':
        obj = InsurancePolicy.query.filter_by(id=ref_id, user_id=user.id).first()
        return obj, (obj.end_date if obj else None)
    if kind == 'document':
        obj = Attachment.query.filter_by(id=ref_id, user_id=user.id).first()
        return obj, (obj.expires_at if obj else None)
    if kind in ('parking', 'fine'):
        obj = ParkingEntry.query.filter_by(id=ref_id, user_id=user.id).first()
        # Fines carry no due date (dismissal hides the fine until un-dismissed
        # or its status changes on the record itself).
        return obj, (obj.permit_expires if (obj and kind == 'parking') else None)
    if kind == 'consumable':
        obj = ConsumableEntry.query.filter_by(id=ref_id, user_id=user.id).first()
        return obj, None
    return None, None


def _parse_dismiss_body():
    """Validate the dismiss/undismiss request body → (kind, ref_id) or (None, None)."""
    data = request.get_json(silent=True) or {}
    kind = (data.get('kind') or '').strip().lower()
    if kind not in _DISMISSIBLE_KINDS:
        return None, None
    try:
        ref_id = int(data.get('ref_id'))
    except (TypeError, ValueError):
        return None, None
    return kind, ref_id


@system_bp.route('/due/dismiss', methods=['POST'])
@token_required
def dismiss_due_item(current_user):
    """Dismiss ONE occurrence of a "Coming up" item (F40).

    Reminders use their native ``dismissed`` flag (which also silences their
    push/email pipeline); every other kind gets a DueDismissal row pinned to
    the item's current effective due date, so a future occurrence resurfaces.
    Idempotent.
    """
    from app import db
    from app.models import DueDismissal

    kind, ref_id = _parse_dismiss_body()
    if kind is None:
        return jsonify({'error': 'A valid kind and ref_id are required'}), 400

    obj, due = _resolve_due_ref(current_user, kind, ref_id)
    if obj is None:
        return jsonify({'error': 'Item not found'}), 404

    if kind == 'reminder':
        obj.dismissed = True
    else:
        exists = DueDismissal.query.filter_by(
            user_id=current_user.id, kind=kind, ref_id=ref_id, due_date=due,
        ).first()
        if not exists:
            db.session.add(DueDismissal(
                user_id=current_user.id, kind=kind, ref_id=ref_id, due_date=due,
            ))
    db.session.commit()
    return jsonify({'message': 'Dismissed', 'kind': kind, 'ref_id': ref_id})


@system_bp.route('/due/undismiss', methods=['POST'])
@token_required
def undismiss_due_item(current_user):
    """Undo a dismissal (the frontend's Undo action). Idempotent."""
    from app import db
    from app.models import DueDismissal

    kind, ref_id = _parse_dismiss_body()
    if kind is None:
        return jsonify({'error': 'A valid kind and ref_id are required'}), 400

    obj, _ = _resolve_due_ref(current_user, kind, ref_id)
    if obj is None:
        return jsonify({'error': 'Item not found'}), 404

    if kind == 'reminder':
        obj.dismissed = False
    else:
        DueDismissal.query.filter_by(
            user_id=current_user.id, kind=kind, ref_id=ref_id,
        ).delete(synchronize_session=False)
    db.session.commit()
    return jsonify({'message': 'Restored', 'kind': kind, 'ref_id': ref_id})


@system_bp.route('/forecast', methods=['GET'])
@token_required
def get_fleet_forecast(current_user):
    """Fleet-wide 12-month cost forecast (F11) — sums all non-archived vehicles.

    Query: ``?months=12`` (clamped 1..24). Owner-scoped; amounts in the user's
    display currency.
    """
    from app.models import Vehicle
    from app.routes.vehicles import _build_forecast
    months = request.args.get('months', 12, type=int)
    vehicles = Vehicle.query.filter_by(user_id=current_user.id, archived=False).all()
    return jsonify(_build_forecast(current_user, vehicles, months))

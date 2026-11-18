"""
GearCargo - Seasonal Checklists Routes
"""

import uuid
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, current_app
from sqlalchemy.orm.attributes import flag_modified

from app import db
from app.routes.auth import token_required

checklists_bp = Blueprint('checklists', __name__)

# Predefined checklist templates
SEASONAL_CHECKLISTS = {
    'winter': {
        'id': 'winter',
        'season_months': [10, 11, 12, 1, 2],  # Oct-Feb
        'items': [
            'winter_tires',
            'antifreeze',
            'battery_check',
            'heater_defroster',
            'wiper_blades',
            'washer_fluid',
            'emergency_kit',
            'lights_check',
        ]
    },
    'summer': {
        'id': 'summer',
        'season_months': [5, 6, 7, 8, 9],  # May-Sep
        'items': [
            'ac_check',
            'coolant_level',
            'tire_pressure',
            'oil_level',
            'brake_inspection',
            'spare_tire',
            'first_aid_kit',
            'roadside_kit',
        ]
    },
    'pre_purchase': {
        'id': 'pre_purchase',
        'season_months': None,  # Always available
        'items': [
            'exterior_inspection',
            'interior_inspection',
            'engine_check',
            'test_drive',
            'history_report',
            'mechanic_inspection',
            'documentation_check',
            'price_negotiation',
        ]
    },
    'state_inspection': {
        'id': 'state_inspection',
        'season_months': None,  # User-configurable
        'items': [
            'lights_signals',
            'brakes_test',
            'tires_condition',
            'steering_suspension',
            'exhaust_emissions',
            'windshield_wipers',
            'horn_mirrors',
            'seatbelts_safety',
        ]
    }
}


def _valid_month_list(raw):
    """Coerce arbitrary input into a sorted, de-duped list of month ints 1-12.

    Returns [] for anything unusable — callers treat [] as "no restriction"
    (year-round), so bad input can never hide a checklist entirely. Raises
    ValueError only when an explicit out-of-range month is supplied so the
    settings route can 400 on it.
    """
    if not raw:
        return []
    if not isinstance(raw, list):
        raise ValueError('months must be a list')
    out = set()
    for m in raw:
        try:
            mi = int(m)
        except (TypeError, ValueError):
            raise ValueError('months must be integers')
        if mi < 1 or mi > 12:
            raise ValueError('month out of range 1-12')
        out.add(mi)
    return sorted(out)


@checklists_bp.route('', methods=['GET'])
@token_required
def get_checklists(current_user):
    """Get user's seasonal checklist progress."""
    try:
        # Get user preferences
        user_prefs = current_user.preferences or {}
        checklist_progress = user_prefs.get('seasonal_checklists', {})
        checklist_settings = user_prefs.get('checklist_settings', {})
        
        # Determine current season
        current_month = datetime.now(timezone.utc).month
        
        # Build response with progress
        checklists = []
        for key, checklist in SEASONAL_CHECKLISTS.items():
            # F54 — state_inspection is user-configurable: its season is whatever
            # months the user picked (empty/unset => year-round, unchanged default).
            season_months = checklist['season_months']
            if key == 'state_inspection':
                season_months = _valid_month_list(
                    checklist_settings.get('state_inspection_months')) or None

            # Check if checklist is relevant for current season
            is_seasonal = season_months is not None
            is_in_season = not is_seasonal or current_month in season_months

            # Get user's completed items for this checklist
            user_progress = checklist_progress.get(key, {})
            completed_items = user_progress.get('completed', [])
            dismissed = user_progress.get('dismissed', False)
            last_completed = user_progress.get('last_completed')
            custom_items = user_progress.get('custom_items', [])

            # Build item list with completion status (built-ins then custom)
            items = []
            for item_id in checklist['items']:
                items.append({
                    'id': item_id,
                    'completed': item_id in completed_items,
                })
            # F54 — user's own items carry their label (not translated) + a flag.
            for ci in custom_items:
                cid = ci.get('id')
                if not cid:
                    continue
                items.append({
                    'id': cid,
                    'completed': cid in completed_items,
                    'custom': True,
                    'label': ci.get('label', ''),
                })

            total_count = len(items)
            completed_count = sum(1 for it in items if it['completed'])

            checklists.append({
                'id': key,
                'is_seasonal': is_seasonal,
                'is_in_season': is_in_season,
                'season_months': season_months,
                'items': items,
                'completed_count': completed_count,
                'total_count': total_count,
                'progress_percent': round((completed_count / total_count) * 100) if total_count > 0 else 0,
                'dismissed': dismissed,
                'last_completed': last_completed,
            })
        
        return jsonify({
            'success': True,
            'checklists': checklists,
            'settings': checklist_settings,
        })
        
    except Exception as e:
        current_app.logger.error(f"Failed to get checklists: {e}")
        return jsonify({'error': 'Failed to load checklists'}), 500


@checklists_bp.route('/<checklist_id>/items/<item_id>', methods=['POST', 'DELETE'])
@token_required
def toggle_checklist_item(current_user, checklist_id, item_id):
    """Toggle a checklist item completion status."""
    try:
        if checklist_id not in SEASONAL_CHECKLISTS:
            return jsonify({'error': 'Invalid checklist'}), 400

        # Get current preferences
        if not current_user.preferences:
            current_user.preferences = {}

        prefs = dict(current_user.preferences)
        if 'seasonal_checklists' not in prefs:
            prefs['seasonal_checklists'] = {}

        if checklist_id not in prefs['seasonal_checklists']:
            prefs['seasonal_checklists'][checklist_id] = {'completed': [], 'dismissed': False}

        # F54 — an item is valid if it's a built-in id OR one of this checklist's
        # own custom items. Custom ids are never accepted for other checklists.
        custom_ids = {ci.get('id') for ci in
                      prefs['seasonal_checklists'][checklist_id].get('custom_items', [])}
        builtin_ids = SEASONAL_CHECKLISTS[checklist_id]['items']
        if item_id not in builtin_ids and item_id not in custom_ids:
            return jsonify({'error': 'Invalid checklist item'}), 400

        total_items = len(builtin_ids) + len(custom_ids)
        completed = prefs['seasonal_checklists'][checklist_id].get('completed', [])

        if request.method == 'POST':
            # Mark as completed
            if item_id not in completed:
                completed.append(item_id)
                # Check if all items completed
                if len(completed) >= total_items:
                    prefs['seasonal_checklists'][checklist_id]['last_completed'] = datetime.now(timezone.utc).isoformat()
        else:
            # Mark as incomplete
            if item_id in completed:
                completed.remove(item_id)
        
        prefs['seasonal_checklists'][checklist_id]['completed'] = completed
        current_user.preferences = prefs
        flag_modified(current_user, 'preferences')
        db.session.commit()
        
        return jsonify({
            'success': True,
            'item_id': item_id,
            'completed': item_id in completed,
            'checklist_completed_count': len(completed),
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to toggle checklist item: {e}")
        return jsonify({'error': 'Failed to update checklist'}), 500


_MAX_CUSTOM_ITEMS = 20
_MAX_CUSTOM_LABEL = 80


@checklists_bp.route('/settings', methods=['PUT'])
@token_required
def update_checklist_settings(current_user):
    """F54 — persist user-configurable checklist settings.

    Currently: state_inspection_months (list of ints 1-12; empty clears it →
    the checklist reverts to year-round). Stored under
    preferences['checklist_settings'].
    """
    try:
        data = request.get_json(silent=True) or {}
        prefs = dict(current_user.preferences or {})
        settings = dict(prefs.get('checklist_settings', {}))

        if 'state_inspection_months' in data:
            try:
                months = _valid_month_list(data.get('state_inspection_months'))
            except ValueError as ve:
                return jsonify({'error': str(ve)}), 400
            settings['state_inspection_months'] = months

        prefs['checklist_settings'] = settings
        current_user.preferences = prefs
        flag_modified(current_user, 'preferences')
        db.session.commit()

        return jsonify({'success': True, 'settings': settings})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to update checklist settings: {e}")
        return jsonify({'error': 'Failed to update settings'}), 500


@checklists_bp.route('/<checklist_id>/custom-items', methods=['POST', 'DELETE'])
@token_required
def manage_custom_checklist_item(current_user, checklist_id):
    """F54 — add or remove a user's own checklist item.

    POST  {'label': '...'}  → append a custom item (id 'custom_<hex>').
    DELETE {'id': 'custom_..'} → remove it and clear any completion for it.
    """
    try:
        if checklist_id not in SEASONAL_CHECKLISTS:
            return jsonify({'error': 'Invalid checklist'}), 400

        data = request.get_json(silent=True) or {}
        prefs = dict(current_user.preferences or {})
        prefs.setdefault('seasonal_checklists', {})
        prefs['seasonal_checklists'].setdefault(
            checklist_id, {'completed': [], 'dismissed': False})
        entry = prefs['seasonal_checklists'][checklist_id]
        custom_items = list(entry.get('custom_items', []))

        if request.method == 'POST':
            label = (data.get('label') or '').strip()
            if not label:
                return jsonify({'error': 'Label is required'}), 400
            if len(label) > _MAX_CUSTOM_LABEL:
                return jsonify({'error': f'Label too long (max {_MAX_CUSTOM_LABEL})'}), 400
            if len(custom_items) >= _MAX_CUSTOM_ITEMS:
                return jsonify({'error': f'Too many custom items (max {_MAX_CUSTOM_ITEMS})'}), 400
            new_item = {'id': f'custom_{uuid.uuid4().hex[:12]}', 'label': label}
            custom_items.append(new_item)
            entry['custom_items'] = custom_items
        else:
            item_id = (data.get('id') or '').strip()
            if not item_id:
                return jsonify({'error': 'Item id is required'}), 400
            custom_items = [ci for ci in custom_items if ci.get('id') != item_id]
            entry['custom_items'] = custom_items
            # Drop any lingering completion for the removed item.
            entry['completed'] = [c for c in entry.get('completed', []) if c != item_id]

        current_user.preferences = prefs
        flag_modified(current_user, 'preferences')
        db.session.commit()

        return jsonify({
            'success': True,
            'checklist_id': checklist_id,
            'custom_items': custom_items,
            'item': new_item if request.method == 'POST' else None,
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to manage custom checklist item: {e}")
        return jsonify({'error': 'Failed to update checklist'}), 500


@checklists_bp.route('/<checklist_id>/dismiss', methods=['POST', 'DELETE'])
@token_required
def dismiss_checklist(current_user, checklist_id):
    """Dismiss or restore a checklist."""
    try:
        if checklist_id not in SEASONAL_CHECKLISTS:
            return jsonify({'error': 'Invalid checklist'}), 400
        
        if not current_user.preferences:
            current_user.preferences = {}
        
        prefs = dict(current_user.preferences)
        if 'seasonal_checklists' not in prefs:
            prefs['seasonal_checklists'] = {}
        
        if checklist_id not in prefs['seasonal_checklists']:
            prefs['seasonal_checklists'][checklist_id] = {'completed': [], 'dismissed': False}
        
        # Toggle dismissed status
        prefs['seasonal_checklists'][checklist_id]['dismissed'] = (request.method == 'POST')
        
        current_user.preferences = prefs
        db.session.commit()
        
        return jsonify({
            'success': True,
            'checklist_id': checklist_id,
            'dismissed': prefs['seasonal_checklists'][checklist_id]['dismissed'],
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to dismiss checklist: {e}")
        return jsonify({'error': 'Failed to update checklist'}), 500


@checklists_bp.route('/<checklist_id>/reset', methods=['POST'])
@token_required
def reset_checklist(current_user, checklist_id):
    """Reset a checklist (clear all completed items)."""
    try:
        if checklist_id not in SEASONAL_CHECKLISTS:
            return jsonify({'error': 'Invalid checklist'}), 400
        
        if not current_user.preferences:
            current_user.preferences = {}
        
        prefs = dict(current_user.preferences)
        if 'seasonal_checklists' not in prefs:
            prefs['seasonal_checklists'] = {}
        
        prefs['seasonal_checklists'][checklist_id] = {
            'completed': [],
            'dismissed': False,
            'last_completed': None
        }
        
        current_user.preferences = prefs
        db.session.commit()
        
        return jsonify({
            'success': True,
            'checklist_id': checklist_id,
            'message': 'Checklist reset successfully',
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to reset checklist: {e}")
        return jsonify({'error': 'Failed to reset checklist'}), 500

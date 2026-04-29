"""
GearCargo - AI Predictions Routes
"""

from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, current_app
import requests

from sqlalchemy.orm.attributes import flag_modified

from app import db
from app.models import Vehicle, FuelEntry, ServiceEntry, RepairEntry, PredictionAlert
from app.routes.auth import token_required

predictions_bp = Blueprint('predictions', __name__)


def get_ollama_url():
    """Get Ollama API URL from config."""
    return current_app.config.get('OLLAMA_URL') or current_app.config.get('OLLAMA_BASE_URL', 'http://host.docker.internal:11434')


def ollama_enabled():
    """Check if Ollama is enabled."""
    return current_app.config.get('OLLAMA_ENABLED', False)


@predictions_bp.route('/generate', methods=['POST'])
@token_required
def generate_predictions(current_user):
    """Generate AI predictions for a vehicle."""
    if not ollama_enabled():
        return jsonify({'error': 'AI predictions are not enabled'}), 503
    
    data = request.get_json()
    vehicle_id = data.get('vehicle_id')
    
    if not vehicle_id:
        return jsonify({'error': 'Vehicle ID required'}), 400
    
    vehicle = Vehicle.query.filter_by(
        id=vehicle_id,
        user_id=current_user.id
    ).first()
    
    if not vehicle:
        return jsonify({'error': 'Vehicle not found'}), 404
    
    # Gather vehicle data
    fuel_entries = FuelEntry.query.filter_by(vehicle_id=vehicle_id).order_by(
        FuelEntry.entry_date.desc()
    ).limit(50).all()
    
    service_entries = ServiceEntry.query.filter_by(vehicle_id=vehicle_id).order_by(
        ServiceEntry.entry_date.desc()
    ).limit(20).all()
    
    repair_entries = RepairEntry.query.filter_by(vehicle_id=vehicle_id).order_by(
        RepairEntry.entry_date.desc()
    ).limit(20).all()
    
    # Build context for AI
    context = f"""
    Vehicle: {vehicle.year} {vehicle.make} {vehicle.model}
    Current Mileage: {vehicle.current_mileage}
    Fuel Type: {vehicle.fuel_type}
    
    Recent Fuel Entries (last {len(fuel_entries)}):
    {_format_fuel_data(fuel_entries)}
    
    Recent Services (last {len(service_entries)}):
    {_format_service_data(service_entries)}
    
    Recent Repairs (last {len(repair_entries)}):
    {_format_repair_data(repair_entries)}
    """
    
    prompt = f"""Based on this vehicle data, provide maintenance predictions and alerts.
    
    {context}
    
    Analyze patterns and predict:
    1. Next likely service needed
    2. Potential issues based on history
    3. Fuel efficiency trends
    4. Cost optimization suggestions
    
    Respond in JSON format with structure:
    {{
        "predictions": [
            {{
                "type": "service|repair|fuel|maintenance",
                "title": "Brief title",
                "description": "Detailed description",
                "confidence": 0.0-1.0,
                "urgency": "low|medium|high",
                "estimated_cost": number or null,
                "recommended_action": "action to take"
            }}
        ]
    }}
    """
    
    try:
        ollama_url = get_ollama_url()
        model = current_app.config.get('OLLAMA_MODEL', 'llama3')
        
        response = requests.post(
            f"{ollama_url}/api/generate",
            json={
                'model': model,
                'prompt': prompt,
                'stream': False,
                'format': 'json'
            },
            timeout=120
        )
        
        if response.status_code != 200:
            return jsonify({'error': 'AI service unavailable'}), 503
        
        result = response.json()
        ai_response = result.get('response', '{}')
        
        # Parse AI response
        import json
        try:
            predictions_data = json.loads(ai_response)
        except json.JSONDecodeError:
            predictions_data = {'predictions': []}
        
        # Save predictions
        saved_predictions = []
        for pred in predictions_data.get('predictions', []):
            alert = PredictionAlert(
                user_id=current_user.id,
                vehicle_id=vehicle_id,
                alert_type=pred.get('type', 'maintenance'),
                title=pred.get('title', 'Prediction'),
                description=pred.get('description'),
                confidence_score=pred.get('confidence', 0.5),
                urgency=pred.get('urgency', 'medium'),
                estimated_cost=pred.get('estimated_cost'),
                recommended_action=pred.get('recommended_action'),
                source_data={'prompt': prompt[:500]},
            )
            db.session.add(alert)
            saved_predictions.append(alert)
        
        db.session.commit()
        
        return jsonify({
            'predictions': [p.to_dict() for p in saved_predictions],
            'model_used': model,
        })
        
    except requests.RequestException as e:
        current_app.logger.error(f"AI service error: {str(e)}")
        return jsonify({'error': 'AI service unavailable. Please try again later.'}), 503


def _format_fuel_data(entries):
    """Format fuel entries for AI context."""
    if not entries:
        return "No fuel data"
    
    lines = []
    for e in entries[:10]:
        lines.append(f"- {e.entry_date}: {e.volume}L @ {e.price_per_unit}/L, "
                    f"mileage: {e.mileage}, efficiency: {e.fuel_efficiency or 'N/A'}")
    return "\n".join(lines)


def _format_service_data(entries):
    """Format service entries for AI context."""
    if not entries:
        return "No service data"
    
    lines = []
    for e in entries[:10]:
        lines.append(f"- {e.entry_date}: {e.service_type} - {e.description or 'N/A'}, "
                    f"cost: {e.cost}, mileage: {e.mileage}")
    return "\n".join(lines)


def _format_repair_data(entries):
    """Format repair entries for AI context."""
    if not entries:
        return "No repair data"
    
    lines = []
    for e in entries[:10]:
        lines.append(f"- {e.entry_date}: {e.repair_type} ({e.severity}) - "
                    f"{e.description or 'N/A'}, cost: {e.cost}")
    return "\n".join(lines)


@predictions_bp.route('', methods=['GET'])
@token_required
def get_predictions(current_user):
    """Get saved predictions."""
    vehicle_id = request.args.get('vehicle_id', type=int)
    status = request.args.get('status')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    query = PredictionAlert.query.filter_by(user_id=current_user.id)
    
    if vehicle_id:
        query = query.filter(PredictionAlert.vehicle_id == vehicle_id)
    
    if status:
        query = query.filter(PredictionAlert.status == status)
    
    predictions = query.order_by(PredictionAlert.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return jsonify({
        'predictions': [p.to_dict() for p in predictions.items],
        'total': predictions.total,
        'pages': predictions.pages,
        'current_page': page,
    })


@predictions_bp.route('/<int:prediction_id>', methods=['GET'])
@token_required
def get_prediction(current_user, prediction_id):
    """Get a specific prediction."""
    prediction = PredictionAlert.query.filter_by(
        id=prediction_id,
        user_id=current_user.id
    ).first()
    
    if not prediction:
        return jsonify({'error': 'Prediction not found'}), 404
    
    return jsonify(prediction.to_dict())


@predictions_bp.route('/<int:prediction_id>/dismiss', methods=['POST'])
@token_required
def dismiss_prediction(current_user, prediction_id):
    """Dismiss a prediction."""
    prediction = PredictionAlert.query.filter_by(
        id=prediction_id,
        user_id=current_user.id
    ).first()
    
    if not prediction:
        return jsonify({'error': 'Prediction not found'}), 404
    
    prediction.status = 'dismissed'
    prediction.dismissed_at = datetime.now(timezone.utc)
    db.session.commit()
    
    return jsonify({
        'message': 'Prediction dismissed',
        'prediction': prediction.to_dict()
    })


@predictions_bp.route('/<int:prediction_id>/acknowledge', methods=['POST'])
@token_required
def acknowledge_prediction(current_user, prediction_id):
    """Acknowledge a prediction."""
    prediction = PredictionAlert.query.filter_by(
        id=prediction_id,
        user_id=current_user.id
    ).first()
    
    if not prediction:
        return jsonify({'error': 'Prediction not found'}), 404
    
    prediction.status = 'acknowledged'
    prediction.acknowledged_at = datetime.now(timezone.utc)
    db.session.commit()
    
    return jsonify({
        'message': 'Prediction acknowledged',
        'prediction': prediction.to_dict()
    })


@predictions_bp.route('/status', methods=['GET'])
@token_required
def get_ai_status(current_user):
    """Get AI/Ollama status."""
    if not ollama_enabled():
        return jsonify({
            'enabled': False,
            'status': 'disabled',
            'message': 'AI predictions are disabled'
        })
    
    try:
        ollama_url = get_ollama_url()
        response = requests.get(f"{ollama_url}/api/tags", timeout=5)
        
        if response.status_code == 200:
            models = response.json().get('models', [])
            return jsonify({
                'enabled': True,
                'status': 'online',
                'url': ollama_url,
                'models': [m.get('name') for m in models],
                'current_model': current_app.config.get('OLLAMA_MODEL', 'llama3')
            })
        else:
            return jsonify({
                'enabled': True,
                'status': 'error',
                'message': 'Cannot connect to AI service'
            })
            
    except requests.RequestException:
        return jsonify({
            'enabled': True,
            'status': 'offline',
            'message': 'AI service is not reachable'
        })


# ==========================================
# Seasonal Checklists API
# ==========================================

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


@predictions_bp.route('/checklists', methods=['GET'])
@token_required
def get_checklists(current_user):
    """Get user's seasonal checklist progress."""
    try:
        # Get user preferences
        user_prefs = current_user.preferences or {}
        checklist_progress = user_prefs.get('seasonal_checklists', {})
        checklist_settings = user_prefs.get('checklist_settings', {})
        
        # Determine current season
        from datetime import datetime
        current_month = datetime.now().month
        
        # Build response with progress
        checklists = []
        for key, checklist in SEASONAL_CHECKLISTS.items():
            # Check if checklist is relevant for current season
            is_seasonal = checklist['season_months'] is not None
            is_in_season = not is_seasonal or current_month in checklist['season_months']
            
            # Get user's completed items for this checklist
            user_progress = checklist_progress.get(key, {})
            completed_items = user_progress.get('completed', [])
            dismissed = user_progress.get('dismissed', False)
            last_completed = user_progress.get('last_completed')
            
            # Build item list with completion status
            items = []
            for item_id in checklist['items']:
                items.append({
                    'id': item_id,
                    'completed': item_id in completed_items
                })
            
            completed_count = len(completed_items)
            total_count = len(checklist['items'])
            
            checklists.append({
                'id': key,
                'is_seasonal': is_seasonal,
                'is_in_season': is_in_season,
                'season_months': checklist['season_months'],
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


@predictions_bp.route('/checklists/<checklist_id>/items/<item_id>', methods=['POST', 'DELETE'])
@token_required
def toggle_checklist_item(current_user, checklist_id, item_id):
    """Toggle a checklist item completion status."""
    try:
        if checklist_id not in SEASONAL_CHECKLISTS:
            return jsonify({'error': 'Invalid checklist'}), 400
        
        if item_id not in SEASONAL_CHECKLISTS[checklist_id]['items']:
            return jsonify({'error': 'Invalid checklist item'}), 400
        
        # Get current preferences
        if not current_user.preferences:
            current_user.preferences = {}
        
        prefs = dict(current_user.preferences)
        if 'seasonal_checklists' not in prefs:
            prefs['seasonal_checklists'] = {}
        
        if checklist_id not in prefs['seasonal_checklists']:
            prefs['seasonal_checklists'][checklist_id] = {'completed': [], 'dismissed': False}
        
        completed = prefs['seasonal_checklists'][checklist_id].get('completed', [])
        
        if request.method == 'POST':
            # Mark as completed
            if item_id not in completed:
                completed.append(item_id)
                # Check if all items completed
                if len(completed) == len(SEASONAL_CHECKLISTS[checklist_id]['items']):
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


@predictions_bp.route('/checklists/<checklist_id>/dismiss', methods=['POST', 'DELETE'])
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


@predictions_bp.route('/checklists/<checklist_id>/reset', methods=['POST'])
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

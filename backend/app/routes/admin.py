"""
GearCargo - Admin Routes
"""

from datetime import datetime, timedelta, timezone
from flask import Blueprint, request, jsonify, current_app
from sqlalchemy import func, desc

from app import db
from app.models import (User, Vehicle, Entry, Backup, ActivityLog, BlockedIP, BlockedDevice,
                         NotificationLog, BackupSchedule, Todo, EmailConsentLog)
from app.routes.auth import admin_required

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/stats', methods=['GET'])
@admin_required
def get_system_stats(current_user):
    """Get system-wide statistics."""
    total_users = User.query.count()
    active_users = User.query.filter_by(is_active=True).count()
    total_vehicles = Vehicle.query.count()
    total_entries = Entry.query.count()
    
    # Recent activity
    today = datetime.now(timezone.utc).date()
    week_ago = today - timedelta(days=7)
    
    new_users_week = User.query.filter(
        User.created_at >= week_ago
    ).count()
    
    new_entries_week = Entry.query.filter(
        Entry.created_at >= week_ago
    ).count()
    
    return jsonify({
        'users': {
            'total': total_users,
            'active': active_users,
            'new_this_week': new_users_week,
        },
        'vehicles': {
            'total': total_vehicles,
        },
        'entries': {
            'total': total_entries,
            'new_this_week': new_entries_week,
        },
    })


@admin_bp.route('/users', methods=['GET'])
@admin_required
def get_users(current_user):
    """Get all users."""
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)  # Cap at 100
    search = request.args.get('search', '')
    
    query = User.query
    
    if search:
        # Escape LIKE special characters to prevent pattern manipulation
        safe_search = search.replace('%', r'\%').replace('_', r'\_')
        query = query.filter(
            (User.email.ilike(f'%{safe_search}%')) |
            (User.username.ilike(f'%{safe_search}%')) |
            (User.first_name.ilike(f'%{safe_search}%')) |
            (User.last_name.ilike(f'%{safe_search}%'))
        )
    
    users = query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return jsonify({
        'users': [u.to_dict() for u in users.items],
        'total': users.total,
        'pages': users.pages,
        'current_page': page,
    })


@admin_bp.route('/users', methods=['POST'])
@admin_required
def create_user(current_user):
    """Create a new user (admin only)."""
    data = request.get_json()
    
    # Validate required fields
    if not data.get('email') or not data.get('password'):
        return jsonify({'error': 'Email and password are required'}), 400
    
    # Check if email already exists
    if User.query.filter_by(email=data['email'].lower()).first():
        return jsonify({'error': 'Email already registered'}), 400
    
    # Parse display_name into first_name and last_name
    display_name = data.get('display_name', '').strip()
    first_name = None
    last_name = None
    if display_name:
        parts = display_name.split(' ', 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else None
    
    # Parse vehicle_limit
    vehicle_limit = data.get('vehicle_limit')
    if vehicle_limit is None or vehicle_limit == '' or vehicle_limit == 0:
        vehicle_limit = None  # Unlimited
    else:
        vehicle_limit = max(1, int(vehicle_limit))
    
    # Create new user
    user = User(
        email=data['email'].lower(),
        username=data.get('username', data['email'].split('@')[0]),
        first_name=first_name,
        last_name=last_name,
        is_admin=bool(data.get('is_admin', False)),
        is_active=bool(data.get('is_active', True)),
        vehicle_limit=vehicle_limit
    )
    user.set_password(data['password'])
    user.must_change_password = True  # S25: admin-set passwords are temporary; force change on first login
    
    db.session.add(user)
    db.session.commit()
    
    # Log user creation
    ActivityLog.log(
        event_type='user_created',
        event_category='admin',
        user_id=current_user.id,
        description=f'User {user.email} created by {current_user.email}' + (' as admin' if user.is_admin else ''),
        success=True,
        extra_data={'created_user_id': user.id, 'new_is_admin': user.is_admin}
    )
    
    # Send verification email (if email is enabled)
    if current_app.config.get('MAIL_ENABLED'):
        try:
            from app.services.email_service import email_verification_service
            token = user.generate_verification_token()
            email_verification_service.send_verification_email(user, token)
        except Exception as e:
            current_app.logger.warning(f"Failed to send verification email: {e}")
    
    return jsonify({
        'message': 'User created successfully',
        'user': user.to_dict()
    }), 201


@admin_bp.route('/users/<int:user_id>', methods=['GET'])
@admin_required
def get_user(current_user, user_id):
    """Get specific user details."""
    user = User.query.get_or_404(user_id)
    
    # Get user stats
    vehicles = Vehicle.query.filter_by(user_id=user_id).count()
    entries = Entry.query.join(Vehicle).filter(Vehicle.user_id == user_id).count()
    
    user_dict = user.to_dict()
    user_dict['stats'] = {
        'vehicles': vehicles,
        'entries': entries,
    }
    
    return jsonify(user_dict)


@admin_bp.route('/users/<int:user_id>', methods=['PUT'])
@admin_required
def update_user(current_user, user_id):
    """Update user (admin actions)."""
    user = User.query.get_or_404(user_id)
    
    # Prevent admin from modifying themselves
    if user.id == current_user.id:
        return jsonify({'error': 'Cannot modify your own account here'}), 400
    
    data = request.get_json()
    
    # Handle is_admin field with security checks
    if 'is_admin' in data:
        new_is_admin = bool(data['is_admin'])
        
        # SECURITY: Prevent removing the last admin
        if user.is_admin and not new_is_admin:
            admin_count = User.query.filter_by(is_admin=True, is_active=True).count()
            if admin_count <= 1:
                return jsonify({'error': 'Cannot remove admin status from the last admin'}), 400
        
        # Log admin status changes
        if user.is_admin != new_is_admin:
            ActivityLog.log(
                event_type='admin_status_change',
                event_category='admin',
                user_id=current_user.id,
                description=f'Admin status for {user.email} changed to {new_is_admin} by {current_user.email}',
                success=True,
                extra_data={'target_user_id': user.id, 'new_is_admin': new_is_admin}
            )
        
        user.is_admin = new_is_admin
    
    # Handle is_active field with security checks
    if 'is_active' in data:
        new_is_active = bool(data['is_active'])
        
        # SECURITY: Prevent deactivating the last active admin
        if user.is_admin and user.is_active and not new_is_active:
            admin_count = User.query.filter_by(is_admin=True, is_active=True).count()
            if admin_count <= 1:
                return jsonify({'error': 'Cannot deactivate the last active admin'}), 400
        
        user.is_active = new_is_active
    
    # Handle vehicle_limit field
    if 'vehicle_limit' in data:
        limit = data['vehicle_limit']
        # Allow None/null for unlimited, or a positive integer
        if limit is None or limit == '' or limit == 0:
            user.vehicle_limit = None  # Unlimited
        else:
            user.vehicle_limit = max(1, int(limit))
    
    db.session.commit()
    
    return jsonify({
        'message': 'User updated',
        'user': user.to_dict()
    })


@admin_bp.route('/users/<int:user_id>', methods=['DELETE'])
@admin_required
def delete_user(current_user, user_id):
    """Delete a user."""
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        return jsonify({'error': 'Cannot delete your own account'}), 400
    
    # SECURITY: Prevent deleting the last admin
    if user.is_admin:
        admin_count = User.query.filter_by(is_admin=True, is_active=True).count()
        if admin_count <= 1:
            return jsonify({'error': 'Cannot delete the last admin user'}), 400
    
    # Log the deletion before making changes (user_id = admin who did it, not the deleted user)
    ActivityLog.log(
        event_type='user_deleted',
        event_category='admin',
        user_id=current_user.id,
        description=f'User {user.email} deleted by {current_user.email}',
        success=True,
        extra_data={'deleted_user_id': user.id, 'deleted_email': user.email, 'was_admin': user.is_admin}
    )

    try:
        # Step 1: Delete notification logs first — they FK to push_subscriptions,
        # reminders, prediction_alerts, and vehicles which will be cascade-deleted later.
        NotificationLog.query.filter_by(user_id=user_id).delete(synchronize_session=False)

        # Step 2: Delete backup schedule — not covered by User.backups cascade.
        BackupSchedule.query.filter_by(user_id=user_id).delete(synchronize_session=False)

        # Step 3: Delete todos — FK to both users and vehicles, not in any cascade.
        Todo.query.filter_by(user_id=user_id).delete(synchronize_session=False)

        # Step 4: Delete GDPR consent log — FK to users, append-only but user is being removed.
        EmailConsentLog.query.filter_by(user_id=user_id).delete(synchronize_session=False)

        # Step 5: Null out nullable FK references so blocked-entity records are preserved
        # for audit purposes even after the target user is gone.
        BlockedIP.query.filter_by(target_user_id=user_id).update(
            {'target_user_id': None}, synchronize_session=False
        )
        BlockedDevice.query.filter_by(target_user_id=user_id).update(
            {'target_user_id': None}, synchronize_session=False
        )

        # Step 6: Preserve activity-log records for audit trail; just detach from the user.
        ActivityLog.query.filter_by(user_id=user_id).update(
            {'user_id': None}, synchronize_session=False
        )

        # Step 7: ORM-level delete — SQLAlchemy cascades in FK-safe order:
        #   User → vehicles → (fuel/service/repair/tax/parking entries, reminders,
        #                       predictions, attachments, insurance_policies)
        #        → reminders, backups, push_subscriptions
        db.session.delete(user)
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.error('Failed to delete user %s', user_id, exc_info=True)
        return jsonify({'error': 'Failed to delete user. Please try again later.'}), 500

    return jsonify({'message': 'User deleted'})


@admin_bp.route('/settings', methods=['GET'])
@admin_required
def get_settings(current_user):
    """Get system settings including live Ollama status and prediction stats."""
    import requests as req_lib
    from app.models.prediction import PredictionAlert
    from app.models.app_setting import AppSetting

    ollama_enabled = bool(current_app.config.get('OLLAMA_ENABLED', False))
    ollama_url_raw = (current_app.config.get('OLLAMA_URL') or
                      current_app.config.get('OLLAMA_BASE_URL', '')).rstrip('/')

    # Live Ollama connectivity probe (non-blocking, 3 s timeout)
    ollama_live: dict = {'status': 'disabled'}
    if ollama_enabled and ollama_url_raw:
        try:
            from app.services.ollama import validate_ollama_url
            validated_url = validate_ollama_url(ollama_url_raw)
            resp = req_lib.get(f"{validated_url}/api/tags", timeout=3)
            checked_at = datetime.now(timezone.utc).isoformat()
            if resp.status_code == 200:
                raw_models = resp.json().get('models', [])
                ollama_live = {
                    'status': 'online',
                    'models': [
                        {
                            'name': m.get('name', ''),
                            'size': m.get('size'),
                            'digest': (m.get('digest') or '')[:12] or None,
                        }
                        for m in raw_models
                    ],
                    'current_model': current_app.config.get('OLLAMA_MODEL', ''),
                    'checked_at': checked_at,
                }
            else:
                ollama_live = {'status': 'error', 'checked_at': checked_at}
        except ValueError:
            ollama_live = {'status': 'error', 'message': 'Invalid Ollama URL configured'}
        except req_lib.RequestException:
            ollama_live = {
                'status': 'offline',
                'checked_at': datetime.now(timezone.utc).isoformat(),
            }

    # Aggregate prediction stats
    try:
        total_predictions = PredictionAlert.query.count()
        active_predictions = PredictionAlert.query.filter_by(
            dismissed=False, actioned=False
        ).count()
        last_alert = (
            PredictionAlert.query
            .order_by(PredictionAlert.created_at.desc())
            .first()
        )
        prediction_stats = {
            'total': total_predictions,
            'active': active_predictions,
            'last_generated_at': (
                last_alert.created_at.isoformat() if last_alert else None
            ),
        }
    except Exception:
        prediction_stats = {'total': 0, 'active': 0, 'last_generated_at': None}

    # Per-task model settings — read from DB (admin UI) → env var → empty string.
    # No hardcoded model names: the admin must configure what is available.
    def _task_model(task_key: str) -> str:
        db_val = AppSetting.get(f'ollama_model_{task_key}') or ''
        if db_val:
            return db_val
        env_key = f'OLLAMA_MODEL_{task_key.upper()}'
        return (current_app.config.get(env_key) or '').strip()

    global_model = (AppSetting.get('ollama_model_global')
                    or current_app.config.get('OLLAMA_MODEL')
                    or '')

    task_models = {
        'global':   global_model,
        'predict':  _task_model('predict')  or global_model,
        'ocr':      _task_model('ocr')      or global_model,
        'anomaly':  _task_model('anomaly')  or global_model,
        'reminder': _task_model('reminder') or global_model,
    }

    if ollama_live.get('status') == 'online':
        ollama_live['task_models'] = task_models

    # AI response cache stats
    from app.services.ollama import ai_cache_stats, ollama_downtime_info
    ai_cache = ai_cache_stats()
    ollama_downtime = ollama_downtime_info()

    return jsonify({
        'app_name': current_app.config.get('APP_NAME', 'GearCargo'),
        'ollama_enabled': ollama_enabled,
        'ollama_url': ollama_url_raw,
        'max_upload_size': current_app.config.get('MAX_CONTENT_LENGTH', 10485760),
        'registration_enabled': current_app.config.get('REGISTRATION_ENABLED', True),
        'ollama_live': ollama_live,
        'prediction_stats': prediction_stats,
        'task_models': task_models,
        'ai_cache': ai_cache,
        'ollama_downtime': ollama_downtime,
    })


_VALID_MODEL_RE = __import__('re').compile(r'^[a-zA-Z0-9][\w.\-:/]{0,99}$')


@admin_bp.route('/settings', methods=['PUT'])
@admin_required
def update_settings(current_user):
    """Update runtime-configurable settings (currently: per-task Ollama models)."""
    from app.models.app_setting import AppSetting
    from app import db

    data = request.get_json(silent=True) or {}
    task_models = data.get('task_models')

    if not isinstance(task_models, dict):
        return jsonify({'error': 'task_models must be an object'}), 400

    allowed_tasks = {'global', 'predict', 'ocr', 'anomaly', 'reminder'}
    saved = {}
    for task, model_name in task_models.items():
        if task not in allowed_tasks:
            continue
        if model_name is None or model_name == '':
            # Empty string means "reset to global default"
            AppSetting.set(f'ollama_model_{task}', None)
            saved[task] = None
            continue
        if not isinstance(model_name, str) or not _VALID_MODEL_RE.match(model_name):
            return jsonify({'error': f'Invalid model name for task {task!r}'}), 400
        AppSetting.set(f'ollama_model_{task}', model_name)
        saved[task] = model_name

    db.session.commit()
    return jsonify({'saved': saved})


@admin_bp.route('/ai-cache', methods=['DELETE'])
@admin_required
def flush_ai_cache(current_user):
    """Flush all Redis AI response cache entries.

    This forces every AI task (predictions, OCR, anomaly, reminder) to
    re-call Ollama on the next request, bypassing cached results.
    Useful when the configured model has changed or when you want
    fresh results immediately.
    """
    from app.services.ollama import ai_cache_flush, ai_cache_stats
    deleted = ai_cache_flush()
    after = ai_cache_stats()
    return jsonify({'deleted': deleted, 'remaining': after.get('keys', 0)})


@admin_bp.route('/logs', methods=['GET'])
@admin_required
def get_logs(current_user):
    """Get system activity logs with filtering."""
    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 100)  # Cap at 100

    # Filters
    event_type = request.args.get('event_type')
    event_category = request.args.get('category')
    user_id = request.args.get('user_id', type=int)
    success = request.args.get('success')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    search = request.args.get('search', '')
    country = request.args.get('country')
    
    # Build query
    query = ActivityLog.query
    
    # Apply filters
    if event_type:
        query = query.filter(ActivityLog.event_type == event_type)
    
    if event_category:
        query = query.filter(ActivityLog.event_category == event_category)
    
    if user_id:
        query = query.filter(ActivityLog.user_id == user_id)
    
    if success is not None:
        success_bool = success.lower() in ('true', '1', 'yes')
        query = query.filter(ActivityLog.success == success_bool)
    
    if start_date:
        try:
            start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            query = query.filter(ActivityLog.created_at >= start)
        except:
            pass
    
    if end_date:
        try:
            end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            query = query.filter(ActivityLog.created_at <= end)
        except:
            pass
    
    if country:
        query = query.filter(ActivityLog.country_code == country.upper())
    
    if search:
        safe_search = search.replace('%', r'\%').replace('_', r'\_')
        query = query.filter(
            (ActivityLog.ip_address.ilike(f'%{safe_search}%')) |
            (ActivityLog.description.ilike(f'%{safe_search}%')) |
            (ActivityLog.city.ilike(f'%{safe_search}%')) |
            (ActivityLog.country.ilike(f'%{safe_search}%'))
        )
    
    # Order by most recent first
    query = query.order_by(desc(ActivityLog.created_at))
    
    # Paginate
    logs = query.paginate(page=page, per_page=per_page, error_out=False)
    
    # Get unique event types for filter dropdown
    event_types = db.session.query(ActivityLog.event_type).distinct().all()
    event_types = [et[0] for et in event_types if et[0]]
    
    # Get unique categories for filter dropdown
    categories = db.session.query(ActivityLog.event_category).distinct().all()
    categories = [c[0] for c in categories if c[0]]
    
    # Get unique countries for filter dropdown
    countries = db.session.query(
        ActivityLog.country_code, 
        ActivityLog.country
    ).distinct().filter(ActivityLog.country_code.isnot(None)).all()
    countries = [{'code': c[0], 'name': c[1]} for c in countries if c[0]]
    
    # Get statistics
    total_logs = ActivityLog.query.count()
    today = datetime.now(timezone.utc).date()
    today_logs = ActivityLog.query.filter(
        func.date(ActivityLog.created_at) == today
    ).count()
    failed_logins_today = ActivityLog.query.filter(
        ActivityLog.event_type == 'login_failed',
        func.date(ActivityLog.created_at) == today
    ).count()
    
    return jsonify({
        'logs': [log.to_dict() for log in logs.items],
        'total': logs.total,
        'pages': logs.pages,
        'current_page': page,
        'per_page': per_page,
        'filters': {
            'event_types': event_types,
            'categories': categories,
            'countries': countries,
        },
        'stats': {
            'total_logs': total_logs,
            'today_logs': today_logs,
            'failed_logins_today': failed_logins_today,
        }
    })


@admin_bp.route('/maintenance/cleanup', methods=['POST'])
@admin_required
def run_cleanup(current_user):
    """Run maintenance cleanup tasks."""
    from datetime import datetime
    import os
    
    data = request.get_json() or {}
    preview_only = data.get('preview', False)
    
    # Configuration for cleanup
    backup_retention_days = 30
    activity_log_retention_days = 90
    
    cutoff_backups = datetime.now(timezone.utc) - timedelta(days=backup_retention_days)
    cutoff_logs = datetime.now(timezone.utc) - timedelta(days=activity_log_retention_days)
    
    results = {
        'preview': preview_only,
        'items': []
    }
    
    # 1. Old backups (older than 30 days)
    old_backups = Backup.query.filter(
        Backup.created_at < cutoff_backups
    ).all()
    
    backup_size = 0
    for backup in old_backups:
        if backup.file_path and os.path.exists(backup.file_path):
            try:
                backup_size += os.path.getsize(backup.file_path)
            except OSError:
                pass
    
    results['items'].append({
        'type': 'old_backups',
        'label': 'Old backups (>30 days)',
        'count': len(old_backups),
        'size': backup_size
    })
    
    if not preview_only and old_backups:
        for backup in old_backups:
            # Delete file if exists
            if backup.file_path and os.path.exists(backup.file_path):
                try:
                    os.remove(backup.file_path)
                except OSError:
                    pass
            db.session.delete(backup)
    
    # 2. Old activity logs (older than 90 days)
    old_logs_count = ActivityLog.query.filter(
        ActivityLog.created_at < cutoff_logs
    ).count()
    
    results['items'].append({
        'type': 'old_activity_logs',
        'label': 'Old activity logs (>90 days)',
        'count': old_logs_count,
        'size': 0
    })
    
    if not preview_only and old_logs_count > 0:
        ActivityLog.query.filter(
            ActivityLog.created_at < cutoff_logs
        ).delete()
    
    # 3. Orphaned attachments (files without DB record)
    attachments_dir = os.path.join(os.getcwd(), 'volumes', 'attachments')
    orphaned_files = []
    orphaned_size = 0
    
    if os.path.exists(attachments_dir):
        from app.models import Attachment
        for root, dirs, files in os.walk(attachments_dir):
            for filename in files:
                file_path = os.path.join(root, filename)
                # Check if this file is referenced in any attachment
                attachment = Attachment.query.filter(
                    Attachment.filepath.like(f'%{filename}')
                ).first()
                
                if not attachment:
                    orphaned_files.append(file_path)
                    try:
                        orphaned_size += os.path.getsize(file_path)
                    except OSError:
                        pass
    
    results['items'].append({
        'type': 'orphaned_attachments',
        'label': 'Orphaned attachment files',
        'count': len(orphaned_files),
        'size': orphaned_size
    })
    
    if not preview_only and orphaned_files:
        for file_path in orphaned_files:
            try:
                os.remove(file_path)
            except OSError:
                pass
    
    # Calculate totals
    total_count = sum(item['count'] for item in results['items'])
    total_size = sum(item['size'] for item in results['items'])
    
    results['total_count'] = total_count
    results['total_size'] = total_size
    results['message'] = 'Preview of items to clean' if preview_only else 'Cleanup completed successfully'
    
    if not preview_only:
        db.session.commit()
        
        # Log the cleanup action
        ActivityLog.log(
            event_type='maintenance_cleanup',
            event_category='admin',
            user_id=current_user.id,
            description=f'Ran maintenance cleanup: {total_count} items removed',
            success=True,
            extra_data={
                'deleted_backups': results['items'][0]['count'],
                'deleted_logs': results['items'][1]['count'],
                'deleted_orphans': results['items'][2]['count'],
                'freed_space': total_size
            }
        )
    
    return jsonify(results)


# ============================================================
# BLOCKED IPS AND DEVICES MANAGEMENT
# ============================================================

@admin_bp.route('/blocked/ips', methods=['GET'])
@admin_required
def get_blocked_ips(current_user):
    """Get all blocked IPs with optional filters."""
    # Query parameters
    active_only = request.args.get('active_only', 'true').lower() == 'true'
    block_type = request.args.get('type')  # 'auto' or 'manual'
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 100)  # S17: cap at 100
    
    # Build query
    query = BlockedIP.query
    
    if active_only:
        query = query.filter_by(is_active=True)
    
    if block_type:
        query = query.filter_by(block_type=block_type)
    
    # Order by most recent first
    query = query.order_by(desc(BlockedIP.created_at))
    
    # Paginate
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    return jsonify({
        'blocked_ips': [ip.to_dict() for ip in pagination.items],
        'total': pagination.total,
        'pages': pagination.pages,
        'current_page': page,
        'per_page': per_page,
        'stats': {
            'total_blocked': BlockedIP.query.filter_by(is_active=True).count(),
            'auto_blocked': BlockedIP.query.filter_by(is_active=True, block_type='auto').count(),
            'manual_blocked': BlockedIP.query.filter_by(is_active=True, block_type='manual').count(),
        }
    })


@admin_bp.route('/blocked/devices', methods=['GET'])
@admin_required
def get_blocked_devices(current_user):
    """Get all blocked devices with optional filters."""
    # Query parameters
    active_only = request.args.get('active_only', 'true').lower() == 'true'
    block_type = request.args.get('type')
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 100)  # S17: cap at 100
    
    # Build query
    query = BlockedDevice.query
    
    if active_only:
        query = query.filter_by(is_active=True)
    
    if block_type:
        query = query.filter_by(block_type=block_type)
    
    # Order by most recent first
    query = query.order_by(desc(BlockedDevice.created_at))
    
    # Paginate
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    return jsonify({
        'blocked_devices': [d.to_dict() for d in pagination.items],
        'total': pagination.total,
        'pages': pagination.pages,
        'current_page': page,
        'per_page': per_page,
        'stats': {
            'total_blocked': BlockedDevice.query.filter_by(is_active=True).count(),
            'auto_blocked': BlockedDevice.query.filter_by(is_active=True, block_type='auto').count(),
            'manual_blocked': BlockedDevice.query.filter_by(is_active=True, block_type='manual').count(),
        }
    })


@admin_bp.route('/blocked/ip/<int:block_id>/unblock', methods=['POST'])
@admin_required
def unblock_ip(current_user, block_id):
    """Unblock an IP address."""
    data = request.get_json() or {}
    reason = data.get('reason', 'Unblocked by admin')
    
    blocked = BlockedIP.query.get_or_404(block_id)
    
    if not blocked.is_active:
        return jsonify({'error': 'IP is not currently blocked'}), 400
    
    blocked.is_active = False
    blocked.unblocked_at = datetime.now(timezone.utc)
    blocked.unblocked_by_id = current_user.id
    blocked.unblock_reason = reason
    blocked.failed_attempts = 0  # Reset counter
    
    db.session.commit()
    
    # Log the action
    ActivityLog.log(
        event_type='ip_unblocked',
        event_category='admin',
        user_id=current_user.id,
        description=f'Admin unblocked IP: {blocked.ip_address}',
        success=True,
        extra_data={
            'ip_address': blocked.ip_address,
            'reason': reason,
            'previous_block_type': blocked.block_type
        }
    )
    
    return jsonify({
        'message': f'IP {blocked.ip_address} has been unblocked',
        'blocked_ip': blocked.to_dict()
    })


@admin_bp.route('/blocked/device/<int:block_id>/unblock', methods=['POST'])
@admin_required
def unblock_device(current_user, block_id):
    """Unblock a device."""
    data = request.get_json() or {}
    reason = data.get('reason', 'Unblocked by admin')
    
    blocked = BlockedDevice.query.get_or_404(block_id)
    
    if not blocked.is_active:
        return jsonify({'error': 'Device is not currently blocked'}), 400
    
    blocked.is_active = False
    blocked.unblocked_at = datetime.now(timezone.utc)
    blocked.unblocked_by_id = current_user.id
    blocked.unblock_reason = reason
    blocked.failed_attempts = 0  # Reset counter
    
    db.session.commit()
    
    # Log the action
    ActivityLog.log(
        event_type='device_unblocked',
        event_category='admin',
        user_id=current_user.id,
        description=f'Admin unblocked device: {blocked.device_fingerprint[:8]}...',
        success=True,
        extra_data={
            'device_fingerprint': blocked.device_fingerprint,
            'browser': blocked.browser,
            'os': blocked.os,
            'reason': reason,
            'previous_block_type': blocked.block_type
        }
    )
    
    return jsonify({
        'message': 'Device has been unblocked',
        'blocked_device': blocked.to_dict()
    })


@admin_bp.route('/blocked/ip', methods=['POST'])
@admin_required
def block_ip_manually(current_user):
    """Manually block an IP address."""
    data = request.get_json()
    
    ip_address = data.get('ip_address')
    reason = data.get('reason', 'Manually blocked by admin')
    expires_hours = data.get('expires_hours')  # Optional expiry
    
    if not ip_address:
        return jsonify({'error': 'IP address is required'}), 400
    
    # Check if already exists
    existing = BlockedIP.query.filter_by(ip_address=ip_address).first()
    
    if existing:
        if existing.is_active:
            return jsonify({'error': 'IP is already blocked'}), 400
        
        # Re-block the existing record
        existing.is_active = True
        existing.block_type = 'manual'
        existing.reason = reason
        existing.blocked_by_id = current_user.id
        existing.unblocked_at = None
        existing.unblocked_by_id = None
        existing.unblock_reason = None
        
        if expires_hours:
            existing.expires_at = datetime.now(timezone.utc) + timedelta(hours=expires_hours)
        else:
            existing.expires_at = None
        
        blocked = existing
    else:
        # Create new block
        blocked = BlockedIP(
            ip_address=ip_address,
            reason=reason,
            block_type='manual',
            blocked_by_id=current_user.id,
            is_active=True,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=expires_hours) if expires_hours else None
        )
        db.session.add(blocked)
    
    db.session.commit()
    
    # Log the action
    ActivityLog.log(
        event_type='ip_blocked_manual',
        event_category='admin',
        user_id=current_user.id,
        description=f'Admin manually blocked IP: {ip_address}',
        success=True,
        extra_data={
            'ip_address': ip_address,
            'reason': reason,
            'expires_hours': expires_hours
        }
    )
    
    return jsonify({
        'message': f'IP {ip_address} has been blocked',
        'blocked_ip': blocked.to_dict()
    }), 201


@admin_bp.route('/blocked/device', methods=['POST'])
@admin_required
def block_device_manually(current_user):
    """Manually block a device by its fingerprint or user agent."""
    data = request.get_json()
    
    user_agent = data.get('user_agent')
    device_fingerprint = data.get('device_fingerprint')
    reason = data.get('reason', 'Manually blocked by admin')
    expires_hours = data.get('expires_hours')
    
    if not user_agent and not device_fingerprint:
        return jsonify({'error': 'User agent or device fingerprint is required'}), 400
    
    # Generate fingerprint if not provided
    if not device_fingerprint and user_agent:
        device_fingerprint = BlockedDevice.generate_fingerprint(user_agent)
    
    # Check if already exists
    existing = BlockedDevice.query.filter_by(device_fingerprint=device_fingerprint).first()
    
    if existing:
        if existing.is_active:
            return jsonify({'error': 'Device is already blocked'}), 400
        
        # Re-block
        existing.is_active = True
        existing.block_type = 'manual'
        existing.reason = reason
        existing.blocked_by_id = current_user.id
        existing.unblocked_at = None
        existing.unblocked_by_id = None
        existing.unblock_reason = None
        
        if expires_hours:
            existing.expires_at = datetime.now(timezone.utc) + timedelta(hours=expires_hours)
        else:
            existing.expires_at = None
        
        blocked = existing
    else:
        # Create new block
        blocked = BlockedDevice(
            device_fingerprint=device_fingerprint,
            user_agent=user_agent,
            reason=reason,
            block_type='manual',
            blocked_by_id=current_user.id,
            is_active=True,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=expires_hours) if expires_hours else None
        )
        db.session.add(blocked)
    
    db.session.commit()
    
    # Log the action
    ActivityLog.log(
        event_type='device_blocked_manual',
        event_category='admin',
        user_id=current_user.id,
        description=f'Admin manually blocked device: {device_fingerprint[:8]}...',
        success=True,
        extra_data={
            'device_fingerprint': device_fingerprint,
            'user_agent': user_agent,
            'reason': reason,
            'expires_hours': expires_hours
        }
    )
    
    return jsonify({
        'message': 'Device has been blocked',
        'blocked_device': blocked.to_dict()
    }), 201


@admin_bp.route('/blocked/failed-logins', methods=['GET'])
@admin_required
def get_failed_logins(current_user):
    """Get failed login attempts with full details."""
    # Query parameters
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 100)  # S17: cap at 100
    days = request.args.get('days', 7, type=int)  # Last N days
    email_filter = request.args.get('email')
    ip_filter = request.args.get('ip')
    
    # Build query
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    query = ActivityLog.query.filter(
        ActivityLog.event_type.in_(['login_failed', 'login_blocked_lockout', 'login_blocked_ip', 'login_blocked_device', '2fa_failed']),
        ActivityLog.created_at >= cutoff,
        ActivityLog.success == False
    )
    
    if email_filter:
        query = query.filter(ActivityLog.extra_data['email'].astext.ilike(f'%{email_filter}%'))
    
    if ip_filter:
        query = query.filter(ActivityLog.ip_address.ilike(f'%{ip_filter}%'))
    
    # Order by most recent first
    query = query.order_by(desc(ActivityLog.created_at))
    
    # Paginate
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    # Count by type for summary
    type_counts = db.session.query(
        ActivityLog.event_type,
        func.count(ActivityLog.id)
    ).filter(
        ActivityLog.event_type.in_(['login_failed', 'login_blocked_lockout', 'login_blocked_ip', 'login_blocked_device', '2fa_failed']),
        ActivityLog.created_at >= cutoff,
        ActivityLog.success == False
    ).group_by(ActivityLog.event_type).all()
    
    type_summary = {t: c for t, c in type_counts}
    
    # Get unique IPs that have failed
    unique_ips = db.session.query(
        ActivityLog.ip_address,
        func.count(ActivityLog.id).label('count')
    ).filter(
        ActivityLog.event_type == 'login_failed',
        ActivityLog.created_at >= cutoff,
        ActivityLog.ip_address.isnot(None)
    ).group_by(ActivityLog.ip_address).order_by(desc('count')).limit(10).all()
    
    return jsonify({
        'failed_logins': [log.to_dict() for log in pagination.items],
        'total': pagination.total,
        'pages': pagination.pages,
        'current_page': page,
        'per_page': per_page,
        'summary': {
            'total_failed': pagination.total,
            'by_type': type_summary,
            'top_ips': [{'ip': ip, 'count': count} for ip, count in unique_ips if ip],
            'days_included': days
        }
    })


@admin_bp.route('/blocked/summary', methods=['GET'])
@admin_required
def get_blocked_summary(current_user):
    """Get summary of all blocked entities and recent failed logins."""
    # Blocked IPs
    blocked_ips_active = BlockedIP.query.filter_by(is_active=True).count()
    blocked_ips_auto = BlockedIP.query.filter_by(is_active=True, block_type='auto').count()
    blocked_ips_manual = BlockedIP.query.filter_by(is_active=True, block_type='manual').count()
    
    # Blocked devices
    blocked_devices_active = BlockedDevice.query.filter_by(is_active=True).count()
    blocked_devices_auto = BlockedDevice.query.filter_by(is_active=True, block_type='auto').count()
    blocked_devices_manual = BlockedDevice.query.filter_by(is_active=True, block_type='manual').count()
    
    # Recent failed logins (last 24 hours)
    cutoff_24h = datetime.now(timezone.utc) - timedelta(hours=24)
    failed_24h = ActivityLog.query.filter(
        ActivityLog.event_type == 'login_failed',
        ActivityLog.created_at >= cutoff_24h
    ).count()
    
    # Recent failed logins (last 7 days)
    cutoff_7d = datetime.now(timezone.utc) - timedelta(days=7)
    failed_7d = ActivityLog.query.filter(
        ActivityLog.event_type == 'login_failed',
        ActivityLog.created_at >= cutoff_7d
    ).count()
    
    # Most recent blocks
    recent_ip_blocks = BlockedIP.query.filter_by(is_active=True).order_by(
        desc(BlockedIP.created_at)
    ).limit(5).all()
    
    recent_device_blocks = BlockedDevice.query.filter_by(is_active=True).order_by(
        desc(BlockedDevice.created_at)
    ).limit(5).all()
    
    return jsonify({
        'blocked_ips': {
            'total': blocked_ips_active,
            'auto': blocked_ips_auto,
            'manual': blocked_ips_manual,
            'recent': [ip.to_dict() for ip in recent_ip_blocks]
        },
        'blocked_devices': {
            'total': blocked_devices_active,
            'auto': blocked_devices_auto,
            'manual': blocked_devices_manual,
            'recent': [d.to_dict() for d in recent_device_blocks]
        },
        'failed_logins': {
            'last_24h': failed_24h,
            'last_7d': failed_7d
        }
    })


@admin_bp.route('/maintenance/ocr-backfill', methods=['POST'])
@admin_required
def ocr_backfill(current_user):
    """Bulk-requeue OCR for all unprocessed image attachments.

    Safe to call at any time — only images with ocr_processed=False AND a file
    that exists on disk are re-queued.  Already-processed images are skipped.
    Returns immediately; OCR runs in background threads (max 2 concurrent to
    avoid saturating the NAS CPU).
    """
    import os
    import threading
    from app.models.attachment import Attachment
    from app.routes.attachments import _run_ocr_background

    _OCR_CONCURRENCY = 2
    _sem = threading.Semaphore(_OCR_CONCURRENCY)
    _app = current_app._get_current_object()

    def _throttled(att):
        with _sem:
            _run_ocr_background(_app, att.id, att.filepath)

    pending = Attachment.query.filter_by(ocr_processed=False).all()

    queued = 0
    skipped_no_file = 0
    for att in pending:
        if not att.is_image:
            continue
        if not att.filepath or not os.path.exists(att.filepath):
            skipped_no_file += 1
            continue
        threading.Thread(
            target=_throttled,
            args=(att,),
            daemon=False,
            name=f'ocr-admin-backfill-{att.id}',
        ).start()
        queued += 1

    current_app.logger.info(
        'Admin OCR backfill: queued=%d skipped_no_file=%d triggered_by=%s',
        queued, skipped_no_file, current_user.email,
    )
    return jsonify({
        'queued': queued,
        'skipped_no_file': skipped_no_file,
        'message': f'OCR re-queued for {queued} image(s) (max {_OCR_CONCURRENCY} concurrent). Results will appear shortly.',
    })


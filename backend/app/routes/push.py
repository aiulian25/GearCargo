"""
GearCargo - Push Notifications Routes
"""

from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, current_app
from pywebpush import webpush, WebPushException
import json

from app import db
from app.models import PushSubscription, NotificationLog
from app.routes.auth import token_required

push_bp = Blueprint('push', __name__)


@push_bp.route('/vapid-key', methods=['GET'])
def get_vapid_key():
    """Get VAPID public key for push subscriptions."""
    vapid_key = current_app.config.get('VAPID_PUBLIC_KEY')
    
    if not vapid_key:
        return jsonify({'error': 'Push notifications not configured'}), 503
    
    return jsonify({'public_key': vapid_key})


@push_bp.route('/subscribe', methods=['POST'])
@token_required
def subscribe(current_user):
    """Subscribe to push notifications."""
    data = request.get_json()
    
    subscription = data.get('subscription')
    if not subscription:
        return jsonify({'error': 'Subscription data required'}), 400
    
    endpoint = subscription.get('endpoint')
    keys = subscription.get('keys', {})
    
    if not endpoint or not keys.get('p256dh') or not keys.get('auth'):
        return jsonify({'error': 'Invalid subscription data'}), 400
    
    # Check if subscription already exists
    existing = PushSubscription.query.filter_by(endpoint=endpoint).first()
    
    if existing:
        if existing.user_id == current_user.id:
            # Legitimate re-registration from the same user — refresh keys and device info.
            existing.p256dh_key = keys['p256dh']
            existing.auth_key = keys['auth']
            existing.active = True
            existing.device_name = data.get('device_name')
            existing.device_type = data.get('device_type')
            existing.browser = data.get('browser')
            existing.os = data.get('os')
            db.session.commit()

            return jsonify({
                'message': 'Subscription updated',
                'subscription': existing.to_dict()
            })
        else:
            # Endpoint already belongs to a different user — this is either a stale record
            # from a shared device whose previous owner did not unsubscribe cleanly, or a
            # deliberate attempt to hijack another user's push endpoint.
            # In both cases: evict the stale record so the current user gets a clean
            # registration below. Never silently transfer ownership across users.
            current_app.logger.warning(
                '[Security] Push endpoint re-registration: evicting stale record '
                'for user_id=%s, new owner user_id=%s',
                existing.user_id, current_user.id
            )
            db.session.delete(existing)
            db.session.flush()   # enforce deletion before the INSERT below
    
    # Create new subscription
    push_sub = PushSubscription(
        user_id=current_user.id,
        endpoint=endpoint,
        p256dh_key=keys['p256dh'],
        auth_key=keys['auth'],
        device_name=data.get('device_name'),
        device_type=data.get('device_type'),
        browser=data.get('browser'),
        os=data.get('os'),
    )
    
    db.session.add(push_sub)
    db.session.commit()
    
    return jsonify({
        'message': 'Successfully subscribed to push notifications',
        'subscription': push_sub.to_dict()
    }), 201


@push_bp.route('/unsubscribe', methods=['POST'])
@token_required
def unsubscribe(current_user):
    """Unsubscribe from push notifications."""
    data = request.get_json()
    endpoint = data.get('endpoint')
    
    if not endpoint:
        return jsonify({'error': 'Endpoint required'}), 400
    
    subscription = PushSubscription.query.filter_by(
        user_id=current_user.id,
        endpoint=endpoint
    ).first()
    
    if not subscription:
        return jsonify({'error': 'Subscription not found'}), 404
    
    db.session.delete(subscription)
    db.session.commit()
    
    return jsonify({'message': 'Successfully unsubscribed'})


@push_bp.route('/subscriptions', methods=['GET'])
@token_required
def get_subscriptions(current_user):
    """Get user's push subscriptions."""
    subscriptions = PushSubscription.query.filter_by(
        user_id=current_user.id,
        active=True
    ).all()
    
    return jsonify({
        'subscriptions': [s.to_dict() for s in subscriptions]
    })


@push_bp.route('/subscriptions/<int:sub_id>', methods=['DELETE'])
@token_required
def delete_subscription(current_user, sub_id):
    """Delete a specific push subscription."""
    subscription = PushSubscription.query.filter_by(
        id=sub_id,
        user_id=current_user.id
    ).first()
    
    if not subscription:
        return jsonify({'error': 'Subscription not found'}), 404
    
    db.session.delete(subscription)
    db.session.commit()
    
    return jsonify({'message': 'Subscription deleted'})


@push_bp.route('/test', methods=['POST'])
@token_required
def test_notification(current_user):
    """Send a test push notification."""
    data = request.get_json(silent=True) or {}
    
    subscriptions = PushSubscription.query.filter_by(
        user_id=current_user.id,
        active=True
    ).all()
    
    if not subscriptions:
        return jsonify({'error': 'No active subscriptions found'}), 404
    
    vapid_private = current_app.config.get('VAPID_PRIVATE_KEY')
    vapid_email = current_app.config.get('VAPID_EMAIL', 'admin@gearcargo.local')
    
    if not vapid_private:
        return jsonify({'error': 'Push notifications not configured'}), 503
    
    notification_data = {
        'title': data.get('title', 'GearCargo Test'),
        'body': data.get('body', 'This is a test notification'),
        'icon': '/icons/logo-192.png',
        'badge': '/icons/badge-72.png',
        'tag': 'test',
        'data': {
            'url': '/',
            'type': 'test'
        }
    }
    
    sent = 0
    failed = 0
    
    for sub in subscriptions:
        try:
            webpush(
                subscription_info=sub.get_subscription_info(),
                data=json.dumps(notification_data),
                vapid_private_key=vapid_private,
                vapid_claims={
                    'sub': f'mailto:{vapid_email}'
                }
            )
            sub.mark_used()
            sent += 1
            
        except WebPushException as e:
            sub.mark_error(str(e))
            failed += 1
            
            # Remove subscription if it's gone
            if e.response and e.response.status_code in [404, 410]:
                db.session.delete(sub)
    
    db.session.commit()
    
    return jsonify({
        'message': 'Test notification sent',
        'sent': sent,
        'failed': failed
    })


@push_bp.route('/history', methods=['GET'])
@token_required
def get_notification_history(current_user):
    """Get notification history."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    logs = NotificationLog.query.filter_by(
        user_id=current_user.id
    ).order_by(NotificationLog.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return jsonify({
        'notifications': [n.to_dict() for n in logs.items],
        'total': logs.total,
        'pages': logs.pages,
        'current_page': page,
    })


def send_push_to_user(user_id, title, body, data=None, tag=None):
    """Send push notification to all user's subscriptions."""
    from flask import current_app
    
    subscriptions = PushSubscription.query.filter_by(
        user_id=user_id,
        active=True
    ).all()
    
    if not subscriptions:
        return 0
    
    vapid_private = current_app.config.get('VAPID_PRIVATE_KEY')
    vapid_email = current_app.config.get('VAPID_EMAIL', 'admin@gearcargo.local')
    
    if not vapid_private:
        return 0
    
    notification_data = {
        'title': title,
        'body': body,
        'icon': '/icons/logo-192.png',
        'badge': '/icons/badge-72.png',
        'tag': tag or 'gearcargo',
        'data': data or {}
    }
    
    sent = 0
    
    for sub in subscriptions:
        try:
            webpush(
                subscription_info=sub.get_subscription_info(),
                data=json.dumps(notification_data),
                vapid_private_key=vapid_private,
                vapid_claims={
                    'sub': f'mailto:{vapid_email}'
                }
            )
            sub.mark_used()
            sent += 1
            
            # Log notification
            log = NotificationLog(
                user_id=user_id,
                subscription_id=sub.id,
                notification_type=data.get('type', 'general') if data else 'general',
                title=title,
                body=body,
                data=data,
                channel='push',
                status='sent',
                sent_at=datetime.now(timezone.utc)
            )
            db.session.add(log)
            
        except WebPushException as e:
            sub.mark_error(str(e))
            if e.response and e.response.status_code in [404, 410]:
                db.session.delete(sub)
    
    db.session.commit()
    return sent

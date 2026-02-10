"""
GearCargo - Attachments Routes
"""

import os
import uuid
import hashlib
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app, send_file
from werkzeug.utils import secure_filename

from app import db
from app.models import Vehicle, Entry, Attachment
from app.routes.auth import token_required, token_required_query_param

attachments_bp = Blueprint('attachments', __name__)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx', 'xls', 'xlsx'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_upload_folder():
    """Get upload folder path."""
    return current_app.config.get('UPLOAD_FOLDER', '/app/uploads')


@attachments_bp.route('', methods=['GET'])
@token_required
def get_attachments(current_user):
    """Get user's attachments."""
    vehicle_id = request.args.get('vehicle_id', type=int)
    entry_id = request.args.get('entry_id', type=int)
    category = request.args.get('category')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    query = Attachment.query.filter_by(user_id=current_user.id)
    
    if vehicle_id:
        query = query.filter(Attachment.vehicle_id == vehicle_id)
    
    if entry_id:
        query = query.filter(Attachment.entry_id == entry_id)
    
    if category:
        query = query.filter(Attachment.category == category)
    
    attachments = query.order_by(Attachment.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return jsonify({
        'attachments': [a.to_dict() for a in attachments.items],
        'total': attachments.total,
        'pages': attachments.pages,
        'current_page': page,
    })


@attachments_bp.route('', methods=['POST'])
@token_required
def upload_attachment(current_user):
    """Upload a new attachment."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'File type not allowed'}), 400
    
    # Check file size
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    
    if size > MAX_FILE_SIZE:
        return jsonify({'error': 'File too large (max 10MB)'}), 400
    
    # Validate vehicle if provided
    vehicle_id = request.form.get('vehicle_id', type=int)
    if vehicle_id:
        vehicle = Vehicle.query.filter_by(
            id=vehicle_id,
            user_id=current_user.id
        ).first()
        if not vehicle:
            return jsonify({'error': 'Vehicle not found'}), 404
    
    # Validate entry if provided (but skip for insurance documents which use InsurancePolicy not Entry)
    entry_id = request.form.get('entry_id', type=int)
    category = request.form.get('category', 'document')
    
    if entry_id and category != 'insurance_document':
        entry = Entry.query.filter_by(id=entry_id, user_id=current_user.id).first()
        if not entry:
            return jsonify({'error': 'Entry not found'}), 404
    elif entry_id and category == 'insurance_document':
        # Validate insurance policy exists
        from app.models.insurance import InsurancePolicy
        policy = InsurancePolicy.query.filter_by(id=entry_id, user_id=current_user.id).first()
        if not policy:
            return jsonify({'error': 'Insurance policy not found'}), 404
    
    # Generate unique filename
    original_filename = secure_filename(file.filename)
    ext = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else ''
    unique_filename = f"{uuid.uuid4().hex}.{ext}"
    
    # Create user folder
    user_folder = os.path.join(get_upload_folder(), str(current_user.id))
    os.makedirs(user_folder, exist_ok=True)
    
    filepath = os.path.join(user_folder, unique_filename)
    
    # Save file
    file.save(filepath)
    
    # Get MIME type
    import mimetypes
    mime_type = mimetypes.guess_type(original_filename)[0] or 'application/octet-stream'
    
    # Create attachment record
    attachment = Attachment(
        user_id=current_user.id,
        vehicle_id=vehicle_id,
        entry_id=entry_id if category != 'insurance_document' else None,  # Don't link to entry_id for insurance
        filename=unique_filename,
        original_filename=original_filename,
        filepath=filepath,
        file_type=mime_type,
        file_size=size,
        description=request.form.get('description'),
        category=category,
        tags=request.form.get('tags', '').split(',') if request.form.get('tags') else None,
    )
    
    db.session.add(attachment)
    db.session.flush()  # Get the attachment ID
    
    # Link attachment to insurance policy if applicable
    if category == 'insurance_document' and entry_id:
        from app.models.insurance import InsurancePolicy
        policy = InsurancePolicy.query.get(entry_id)
        if policy:
            policy.document_attachment_id = attachment.id
    
    db.session.commit()
    
    return jsonify({
        'message': 'File uploaded successfully',
        'attachment': attachment.to_dict()
    }), 201


@attachments_bp.route('/<int:attachment_id>', methods=['GET'])
@token_required
def get_attachment(current_user, attachment_id):
    """Get attachment info."""
    attachment = Attachment.query.filter_by(
        id=attachment_id,
        user_id=current_user.id
    ).first()
    
    if not attachment:
        return jsonify({'error': 'Attachment not found'}), 404
    
    return jsonify(attachment.to_dict())


@attachments_bp.route('/<int:attachment_id>/download', methods=['GET'])
@token_required
def download_attachment(current_user, attachment_id):
    """Download attachment file."""
    attachment = Attachment.query.filter_by(
        id=attachment_id,
        user_id=current_user.id
    ).first()
    
    if not attachment:
        return jsonify({'error': 'Attachment not found'}), 404
    
    if not os.path.exists(attachment.filepath):
        return jsonify({'error': 'File not found on server'}), 404
    
    return send_file(
        attachment.filepath,
        mimetype=attachment.file_type,
        as_attachment=True,
        download_name=attachment.original_filename
    )


@attachments_bp.route('/<int:attachment_id>/view', methods=['GET'])
@token_required_query_param
def view_attachment(current_user, attachment_id):
    """View attachment file inline (not as download)."""
    attachment = Attachment.query.filter_by(
        id=attachment_id,
        user_id=current_user.id
    ).first()
    
    if not attachment:
        return jsonify({'error': 'Attachment not found'}), 404
    
    if not os.path.exists(attachment.filepath):
        return jsonify({'error': 'File not found on server'}), 404
    
    return send_file(
        attachment.filepath,
        mimetype=attachment.file_type,
        as_attachment=False,
        download_name=attachment.original_filename
    )


@attachments_bp.route('/<int:attachment_id>', methods=['PUT'])
@token_required
def update_attachment(current_user, attachment_id):
    """Update attachment metadata."""
    attachment = Attachment.query.filter_by(
        id=attachment_id,
        user_id=current_user.id
    ).first()
    
    if not attachment:
        return jsonify({'error': 'Attachment not found'}), 404
    
    data = request.get_json()
    
    allowed = ['description', 'category', 'tags', 'expires_at']
    
    for field in allowed:
        if field in data:
            if field == 'expires_at' and data[field]:
                setattr(attachment, field, datetime.fromisoformat(data[field]).date())
            else:
                setattr(attachment, field, data[field])
    
    db.session.commit()
    
    return jsonify({
        'message': 'Attachment updated',
        'attachment': attachment.to_dict()
    })


@attachments_bp.route('/<int:attachment_id>', methods=['DELETE'])
@token_required
def delete_attachment(current_user, attachment_id):
    """Delete an attachment."""
    attachment = Attachment.query.filter_by(
        id=attachment_id,
        user_id=current_user.id
    ).first()
    
    if not attachment:
        return jsonify({'error': 'Attachment not found'}), 404
    
    # Delete file from disk
    if os.path.exists(attachment.filepath):
        os.remove(attachment.filepath)
    
    db.session.delete(attachment)
    db.session.commit()
    
    return jsonify({'message': 'Attachment deleted'})


@attachments_bp.route('/expiring', methods=['GET'])
@token_required
def get_expiring_attachments(current_user):
    """Get attachments with expiring or expired documents."""
    from datetime import date, timedelta
    
    days = request.args.get('days', 30, type=int)
    include_expired = request.args.get('include_expired', 'true').lower() == 'true'
    cutoff = date.today() + timedelta(days=days)
    today = date.today()
    
    # Get expiring soon (within X days but not yet expired)
    expiring_soon = Attachment.query.filter(
        Attachment.user_id == current_user.id,
        Attachment.expires_at.isnot(None),
        Attachment.expires_at <= cutoff,
        Attachment.expires_at >= today
    ).order_by(Attachment.expires_at.asc()).all()
    
    # Get already expired
    expired = []
    if include_expired:
        expired = Attachment.query.filter(
            Attachment.user_id == current_user.id,
            Attachment.expires_at.isnot(None),
            Attachment.expires_at < today
        ).order_by(Attachment.expires_at.desc()).all()
    
    return jsonify({
        'expiring_soon': [a.to_dict() for a in expiring_soon],
        'expired': [a.to_dict() for a in expired],
        'expiring_count': len(expiring_soon),
        'expired_count': len(expired),
        'total_count': len(expiring_soon) + len(expired),
        # Legacy: keep 'attachments' for backward compatibility
        'attachments': [a.to_dict() for a in expiring_soon]
    })


@attachments_bp.route('/stats', methods=['GET'])
@token_required
def get_attachment_stats(current_user):
    """Get attachment statistics."""
    attachments = Attachment.query.filter_by(user_id=current_user.id).all()
    
    total_size = sum(a.file_size or 0 for a in attachments)
    
    # By category
    by_category = {}
    for a in attachments:
        cat = a.category or 'other'
        if cat not in by_category:
            by_category[cat] = {'count': 0, 'size': 0}
        by_category[cat]['count'] += 1
        by_category[cat]['size'] += a.file_size or 0
    
    # By type
    by_type = {'images': 0, 'pdfs': 0, 'documents': 0, 'other': 0}
    for a in attachments:
        if a.is_image:
            by_type['images'] += 1
        elif a.is_pdf:
            by_type['pdfs'] += 1
        elif a.file_type and 'document' in a.file_type:
            by_type['documents'] += 1
        else:
            by_type['other'] += 1
    
    return jsonify({
        'total_count': len(attachments),
        'total_size': total_size,
        'total_size_human': _human_size(total_size),
        'by_category': by_category,
        'by_type': by_type,
    })


def _human_size(size):
    """Convert bytes to human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"

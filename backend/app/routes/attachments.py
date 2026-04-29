"""
GearCargo - Attachments Routes
"""

import os
import uuid
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app, send_file
from werkzeug.utils import secure_filename

from app import db
from app.models import Vehicle, Entry, Attachment
from app.routes.auth import token_required, token_required_query_param

attachments_bp = Blueprint('attachments', __name__)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx', 'xls', 'xlsx'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# S13: Canonical extension → MIME mapping for every extension in ALLOWED_EXTENSIONS.
# This replaces mimetypes.guess_type() (OS-dependent, could be manipulated) with a
# tight, predictable table. Only types listed here are ever stored in the DB or served.
#
# NOTE: docx/xlsx full IANA MIME types (71/65 chars) exceed the DB String(50) column.
# They are served as application/octet-stream (forced download) regardless since they
# are not in _INLINE_SAFE_MIME_TYPES — storing this shorter value is also correct.
_EXTENSION_TO_MIME = {
    'jpg':  'image/jpeg',            # 10 chars
    'jpeg': 'image/jpeg',            # 10 chars
    'png':  'image/png',             #  9 chars
    'gif':  'image/gif',             #  9 chars
    'pdf':  'application/pdf',       # 15 chars
    'doc':  'application/msword',    # 18 chars
    'docx': 'application/octet-stream',  # 24 chars — full IANA type is 71 chars, too long for String(50)
    'xls':  'application/vnd.ms-excel', # 24 chars
    'xlsx': 'application/octet-stream',  # 24 chars — full IANA type is 65 chars, too long for String(50)
}

# S13: Only these MIME types may be served inline (without Content-Disposition: attachment).
# image/svg+xml is intentionally excluded — SVG supports <script> elements and is a
# fully capable XSS vector when served inline. All other types fall back to
# application/octet-stream + Content-Disposition: attachment.
_INLINE_SAFE_MIME_TYPES = frozenset({
    'image/jpeg',
    'image/png',
    'image/gif',
    'image/webp',   # covered by magic-byte check at upload; safe to render inline
    'application/pdf',
})


def safe_attachment_mime(filename: str) -> str:
    """Return a safe, canonical MIME type for an attachment filename.

    S13 fix: derives the MIME type exclusively from the file extension using
    the _EXTENSION_TO_MIME allowlist. Never trusts the DB-stored file_type
    column or mimetypes.guess_type() with attacker-controlled input.

    Returns 'application/octet-stream' for any extension not in the table,
    which forces the browser to download the file instead of rendering it.
    Called at both serve time (view/download endpoints) and backup-restore
    time so that a crafted backup ZIP cannot smuggle 'text/html' or
    'image/svg+xml' into the DB.
    """
    if not filename:
        return 'application/octet-stream'
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    return _EXTENSION_TO_MIME.get(ext, 'application/octet-stream')


def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# Magic-byte signatures used to verify actual file content (prevents extension spoofing).
_FILE_SIGNATURES = [
    (b'\xff\xd8\xff',                       'jpeg'),           # JPEG
    (b'\x89PNG\r\n\x1a\n',                  'png'),            # PNG
    (b'GIF87a',                              'gif'),            # GIF 87a
    (b'GIF89a',                              'gif'),            # GIF 89a
    (b'\x25\x50\x44\x46',                   'pdf'),            # %PDF
    (b'\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1', 'office_legacy'),  # OLE2 — DOC / XLS
    (b'PK\x03\x04',                         'office_openxml'), # ZIP  — DOCX / XLSX
]

# The only magic-byte type that is valid for each allowed extension.
_EXTENSION_TO_TYPE = {
    'jpg':  'jpeg',
    'jpeg': 'jpeg',
    'png':  'png',
    'gif':  'gif',
    'pdf':  'pdf',
    'doc':  'office_legacy',
    'xls':  'office_legacy',
    'docx': 'office_openxml',
    'xlsx': 'office_openxml',
}


def _validate_file_magic(file_obj, extension):
    """
    Read the first 12 bytes of the upload and confirm the content matches
    the claimed file extension.  Returns True when the file is safe to accept.
    Always resets the stream to position 0 before returning.
    """
    header = file_obj.read(12)
    file_obj.seek(0)

    detected = None
    for sig, file_type in _FILE_SIGNATURES:
        if header.startswith(sig):
            detected = file_type
            break

    expected = _EXTENSION_TO_TYPE.get(extension)
    return detected is not None and detected == expected


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

    # Validate actual file content via magic bytes (prevents extension spoofing)
    ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
    if not _validate_file_magic(file, ext):
        return jsonify({'error': 'File content does not match the declared file type'}), 400

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
    # ext is also set earlier for the magic-byte check; re-derive from secure name to be safe
    unique_filename = f"{uuid.uuid4().hex}.{ext}"
    
    # Create user folder
    user_folder = os.path.join(get_upload_folder(), str(current_user.id))
    os.makedirs(user_folder, exist_ok=True)
    
    filepath = os.path.join(user_folder, unique_filename)

    # Write to a temp path first — promoted to the final name only after DB commit
    temp_path = filepath + '.tmp'
    try:
        file.save(temp_path)
        os.chmod(temp_path, 0o640)
    except OSError as e:
        current_app.logger.error(
            f"Failed to write attachment temp file for user {current_user.id}: {e}"
        )
        return jsonify({'error': 'Failed to save file'}), 500

    # Get MIME type from the canonical extension map — never trust mimetypes.guess_type()
    # with user-controlled input. safe_attachment_mime() looks up the extension in
    # _EXTENSION_TO_MIME and returns application/octet-stream for anything unknown.
    mime_type = safe_attachment_mime(original_filename)

    # Build DB record in memory (file not yet at its permanent path)
    attachment = Attachment(
        user_id=current_user.id,
        vehicle_id=vehicle_id,
        entry_id=entry_id if category != 'insurance_document' else None,
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

    try:
        db.session.flush()  # Obtain attachment.id without committing yet
    except Exception as e:
        db.session.rollback()
        try:
            os.remove(temp_path)
        except OSError:
            pass
        current_app.logger.error(
            f"DB flush failed during attachment upload for user {current_user.id}: {e}"
        )
        return jsonify({'error': 'Failed to save attachment'}), 500

    # Link attachment to insurance policy if applicable
    if category == 'insurance_document' and entry_id:
        from app.models.insurance import InsurancePolicy
        policy = InsurancePolicy.query.get(entry_id)
        if policy:
            policy.document_attachment_id = attachment.id

    # Commit — on failure clean up the temp file and leave disk state unchanged
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        try:
            os.remove(temp_path)
        except OSError:
            pass
        current_app.logger.error(
            f"DB commit failed during attachment upload for user {current_user.id}: {e}"
        )
        return jsonify({'error': 'Failed to save attachment'}), 500

    # DB committed — atomically activate the file at its permanent path
    try:
        os.rename(temp_path, filepath)
    except OSError:
        import shutil
        try:
            shutil.move(temp_path, filepath)
        except OSError as e2:
            current_app.logger.error(
                f"Attachment file activation failed after successful DB commit "
                f"for user {current_user.id}, attachment {attachment.id}: {e2}. "
                f"Temp file left at {temp_path}"
            )

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
        # S13: Re-derive MIME from the stored filename extension using the
        # canonical allowlist. Never trust attachment.file_type from the DB —
        # a crafted backup ZIP could have stored 'text/html' or 'image/svg+xml'
        # in that column. For downloads the Content-Disposition: attachment
        # header already prevents inline rendering, but using the safe MIME
        # is defence-in-depth.
        mimetype=safe_attachment_mime(attachment.original_filename),
        as_attachment=True,
        download_name=attachment.original_filename
    )


@attachments_bp.route('/<int:attachment_id>/token', methods=['GET'])
@token_required
def get_attachment_token(current_user, attachment_id):
    """Return a short-lived HMAC-signed URL for viewing an attachment (S20).

    The signed URL replaces the old ``?token=<JWT>`` pattern: the user's JWT
    is never placed in a URL. The signed URL is valid for 5 minutes and is
    bound to the specific attachment id and user id.
    """
    attachment = Attachment.query.filter_by(
        id=attachment_id,
        user_id=current_user.id
    ).first()

    if not attachment:
        return jsonify({'error': 'Attachment not found'}), 404

    from app.utils import sign_attachment_url
    signed_url = sign_attachment_url(attachment_id, current_user.id)
    return jsonify({'url': signed_url})


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

    # S13: Re-derive the MIME type from the original filename extension using
    # the strict allowlist. Never trust attachment.file_type from the DB —
    # a crafted backup ZIP could have stored 'text/html' or 'image/svg+xml'
    # in that column, causing the browser to execute arbitrary scripts when
    # the file is served inline in the app origin.
    #
    # Only MIME types in _INLINE_SAFE_MIME_TYPES are served inline.
    # Everything else is served with Content-Disposition: attachment +
    # application/octet-stream so the browser downloads rather than renders.
    safe_mime = safe_attachment_mime(attachment.original_filename)
    inline = safe_mime in _INLINE_SAFE_MIME_TYPES

    return send_file(
        attachment.filepath,
        mimetype=safe_mime if inline else 'application/octet-stream',
        as_attachment=not inline,
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

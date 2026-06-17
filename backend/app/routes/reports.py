"""
GearCargo - Reports Routes
PDF report generation for vehicle expenses
"""

from datetime import datetime, timedelta, timezone
from flask import Blueprint, request, jsonify, send_file, current_app

from app import db
from app.models import Vehicle, ReportShare
from app.routes.auth import token_required
from app.services.pdf_report_service import (
    generate_pdf_report, get_report_filename, get_period_dates
)
from app.utils.security_audit import security_audit

reports_bp = Blueprint('reports', __name__)

VALID_PERIODS = ['current_month', 'last_month', '3_months', 'year', 'custom']
MAX_SHARE_DAYS = 90
DEFAULT_SHARE_DAYS = 7


def _resolve_report_vehicles(user, vehicle_ids):
    """Resolve a share/report's vehicle selection to the user's OWN vehicles only.

    vehicle_ids None/'all'/[] → all of the user's non-archived vehicles.
    A list → only the ids that actually belong to the user (ownership enforced).
    """
    if not vehicle_ids or vehicle_ids == 'all':
        return (Vehicle.query
                .filter_by(user_id=user.id, archived=False)
                .order_by(Vehicle.created_at).all())
    if not isinstance(vehicle_ids, list):
        vehicle_ids = [vehicle_ids]
    safe_ids = []
    for vid in vehicle_ids:
        try:
            safe_ids.append(int(vid))
        except (TypeError, ValueError):
            continue
    if not safe_ids:
        return []
    return (Vehicle.query
            .filter(Vehicle.id.in_(safe_ids), Vehicle.user_id == user.id)
            .order_by(Vehicle.created_at).all())


def _report_summary(user, vehicles, period, year, month):
    """Aggregate expense totals/counts for a set of vehicles + period.

    Shared by the authenticated preview and the public shared-report view so the
    numbers are always identical. Returns only aggregate, non-sensitive data.
    """
    from app.services.pdf_report_service import get_vehicle_entries

    start_date, end_date, period_label = get_period_dates(period, year, month)
    currency = getattr(user, 'currency', 'EUR') or 'EUR'

    cats = ['fuel', 'service', 'repair', 'tax', 'parking', 'insurance']
    totals = {k: 0 for k in cats}
    totals['grand_total'] = 0
    counts = {k: 0 for k in cats}

    for vehicle in vehicles:
        entries = get_vehicle_entries(vehicle, start_date, end_date, currency)
        for key in cats:
            totals[key] += entries['totals'][key]
            counts[key] += len(entries[key])
        totals['grand_total'] += entries['totals']['grand_total']
    counts['total'] = sum(counts[k] for k in cats)

    return {
        'period_label': period_label,
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d'),
        'vehicle_count': len(vehicles),
        # Only make/model/name — no VIN, plate, addresses, or owner identity.
        'vehicles': [{'name': v.name or f'{v.make} {v.model}'.strip(),
                      'make': v.make, 'model': v.model} for v in vehicles],
        'entry_counts': counts,
        'totals': totals,
        'currency': currency,
    }


@reports_bp.route('/generate', methods=['POST'])
@token_required
def generate_report(current_user):
    """
    Generate a PDF report for vehicle expenses.
    
    Request body:
    {
        "vehicle_ids": [1, 2, 3] or "all",
        "period": "current_month" | "last_month" | "3_months" | "year" | "custom",
        "year": 2024,  // optional, for 'year' or 'custom' period
        "month": 6     // optional, for 'custom' period (1-12)
    }
    """
    try:
        data = request.get_json() or {}
        
        # Get vehicle selection
        vehicle_ids = data.get('vehicle_ids', 'all')
        period = data.get('period', 'current_month')
        year = data.get('year')
        month = data.get('month')
        
        # Get vehicles
        if vehicle_ids == 'all' or not vehicle_ids:
            vehicles = Vehicle.query.filter_by(
                user_id=current_user.id,
                archived=False
            ).order_by(Vehicle.created_at).all()
        else:
            if isinstance(vehicle_ids, list):
                vehicles = Vehicle.query.filter(
                    Vehicle.id.in_(vehicle_ids),
                    Vehicle.user_id == current_user.id
                ).order_by(Vehicle.created_at).all()
            else:
                # Single vehicle ID
                vehicle = Vehicle.query.filter_by(
                    id=vehicle_ids,
                    user_id=current_user.id
                ).first()
                vehicles = [vehicle] if vehicle else []
        
        if not vehicles:
            return jsonify({'error': 'No vehicles found'}), 404
        
        # Validate period
        valid_periods = ['current_month', 'last_month', '3_months', 'year', 'custom']
        if period not in valid_periods:
            period = 'current_month'
        
        # Validate year and month for custom period
        if period == 'custom':
            if not year or not month:
                return jsonify({'error': 'Year and month required for custom period'}), 400
            if month < 1 or month > 12:
                return jsonify({'error': 'Month must be between 1 and 12'}), 400
        
        if period == 'year' and not year:
            year = datetime.now().year
        
        # Get language from user preferences
        language = getattr(current_user, 'language', 'en') or 'en'
        
        # Generate PDF
        current_app.logger.info(f"Generating PDF report for user {current_user.id}, vehicles: {[v.id for v in vehicles]}, period: {period}")
        
        pdf_buffer = generate_pdf_report(
            user=current_user,
            vehicles=vehicles,
            period=period,
            year=year,
            month=month,
            language=language
        )
        
        # Generate filename
        filename = get_report_filename(vehicles, period, year, month)
        
        current_app.logger.info(f"PDF report generated successfully: {filename}")
        
        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        current_app.logger.error(f"Error generating PDF report: {str(e)}")
        return jsonify({'error': 'Failed to generate report. Please try again later.'}), 500


@reports_bp.route('/preview', methods=['POST'])
@token_required
def preview_report_info(current_user):
    """
    Get preview information about a report before generating.
    Returns entry counts and totals for the selected period.
    """
    try:
        data = request.get_json() or {}
        
        vehicle_ids = data.get('vehicle_ids', 'all')
        period = data.get('period', 'current_month')
        year = data.get('year')
        month = data.get('month')
        
        # Get vehicles
        if vehicle_ids == 'all' or not vehicle_ids:
            vehicles = Vehicle.query.filter_by(
                user_id=current_user.id,
                archived=False
            ).all()
        else:
            if isinstance(vehicle_ids, list):
                vehicles = Vehicle.query.filter(
                    Vehicle.id.in_(vehicle_ids),
                    Vehicle.user_id == current_user.id
                ).all()
            else:
                vehicle = Vehicle.query.filter_by(
                    id=vehicle_ids,
                    user_id=current_user.id
                ).first()
                vehicles = [vehicle] if vehicle else []
        
        if not vehicles:
            return jsonify({'error': 'No vehicles found'}), 404
        
        # Get period dates
        start_date, end_date, period_label = get_period_dates(period, year, month)
        
        # Import here to avoid circular imports
        from app.services.pdf_report_service import get_vehicle_entries
        
        # Get currency
        currency = getattr(current_user, 'currency', 'EUR') or 'EUR'
        
        # Calculate totals
        totals = {
            'fuel': 0,
            'service': 0,
            'repair': 0,
            'tax': 0,
            'parking': 0,
            'insurance': 0,
            'grand_total': 0
        }
        
        entry_counts = {
            'fuel': 0,
            'service': 0,
            'repair': 0,
            'tax': 0,
            'parking': 0,
            'insurance': 0,
            'total': 0
        }
        
        for vehicle in vehicles:
            entries = get_vehicle_entries(vehicle, start_date, end_date, currency)
            for key in ['fuel', 'service', 'repair', 'tax', 'parking', 'insurance']:
                totals[key] += entries['totals'][key]
                entry_counts[key] += len(entries[key])
            totals['grand_total'] += entries['totals']['grand_total']
        
        entry_counts['total'] = sum([entry_counts[k] for k in ['fuel', 'service', 'repair', 'tax', 'parking', 'insurance']])
        
        return jsonify({
            'period_label': period_label,
            'start_date': start_date.strftime('%Y-%m-%d'),
            'end_date': end_date.strftime('%Y-%m-%d'),
            'vehicle_count': len(vehicles),
            'vehicles': [{'id': v.id, 'name': f"{v.make} {v.model}"} for v in vehicles],
            'entry_counts': entry_counts,
            'totals': totals,
            'currency': currency
        })
        
    except Exception as e:
        current_app.logger.error(f"Error previewing report: {str(e)}")
        return jsonify({'error': 'Failed to preview report. Please try again later.'}), 500


@reports_bp.route('/periods', methods=['GET'])
@token_required
def get_available_periods(current_user):
    """
    Get available time periods for report generation.
    """
    current_year = datetime.now().year
    
    periods = [
        {'id': 'current_month', 'name': 'Current Month', 'requires_date': False},
        {'id': 'last_month', 'name': 'Last Month', 'requires_date': False},
        {'id': '3_months', 'name': 'Last 3 Months', 'requires_date': False},
        {'id': 'year', 'name': 'Full Year', 'requires_date': True, 'date_type': 'year'},
        {'id': 'custom', 'name': 'Custom Month', 'requires_date': True, 'date_type': 'month'},
    ]
    
    # Available years (from 5 years ago to current)
    years = list(range(current_year - 5, current_year + 1))
    years.reverse()
    
    # Months
    months = [
        {'id': 1, 'name': 'January'},
        {'id': 2, 'name': 'February'},
        {'id': 3, 'name': 'March'},
        {'id': 4, 'name': 'April'},
        {'id': 5, 'name': 'May'},
        {'id': 6, 'name': 'June'},
        {'id': 7, 'name': 'July'},
        {'id': 8, 'name': 'August'},
        {'id': 9, 'name': 'September'},
        {'id': 10, 'name': 'October'},
        {'id': 11, 'name': 'November'},
        {'id': 12, 'name': 'December'},
    ]
    
    return jsonify({
        'periods': periods,
        'years': years,
        'months': months,
        'current_year': current_year,
        'current_month': datetime.now().month
    })


# ==========================================================================
# Shareable read-only report links (F05) — signed, expiring, revocable.
# ==========================================================================

@reports_bp.route('/shares', methods=['POST'])
@token_required
def create_report_share(current_user):
    """Create a signed, expiring share link for a report. The raw token is
    returned ONCE; only its hash is stored."""
    data = request.get_json() or {}

    period = data.get('period', 'current_month')
    if period not in VALID_PERIODS:
        return jsonify({'error': 'Invalid period'}), 400

    year = data.get('year')
    month = data.get('month')
    if period == 'custom' and (not year or not month or month < 1 or month > 12):
        return jsonify({'error': 'Year and valid month required for custom period'}), 400

    # Normalise + ownership-validate the vehicle selection up front.
    raw_ids = data.get('vehicle_ids', 'all')
    vehicles = _resolve_report_vehicles(current_user, raw_ids)
    if not vehicles:
        return jsonify({'error': 'No vehicles found'}), 404
    stored_ids = None if (not raw_ids or raw_ids == 'all') else [v.id for v in vehicles]

    try:
        days = int(data.get('expires_in_days', DEFAULT_SHARE_DAYS))
    except (TypeError, ValueError):
        days = DEFAULT_SHARE_DAYS
    days = max(1, min(MAX_SHARE_DAYS, days))

    label = (data.get('label') or '').strip()[:120] or None

    raw_token, token_hash, prefix = ReportShare.new_token()
    share = ReportShare(
        user_id=current_user.id,
        token_hash=token_hash,
        token_prefix=prefix,
        label=label,
        vehicle_ids=stored_ids,
        period=period,
        year=year,
        month=month,
        expires_at=datetime.utcnow() + timedelta(days=days),
    )
    db.session.add(share)
    db.session.commit()

    security_audit.data_export(current_user.id, current_user.email, 'report_share_created')

    app_url = (current_app.config.get('APP_URL') or '').rstrip('/')
    share_url = f'{app_url}/shared/report/{raw_token}'

    resp = share.to_dict()
    resp['token'] = raw_token       # shown once, never persisted
    resp['url'] = share_url
    return jsonify(resp), 201


@reports_bp.route('/shares', methods=['GET'])
@token_required
def list_report_shares(current_user):
    """List the current user's share links (no raw tokens)."""
    shares = (ReportShare.query
              .filter_by(user_id=current_user.id)
              .order_by(ReportShare.created_at.desc())
              .all())
    return jsonify({'shares': [s.to_dict() for s in shares]})


@reports_bp.route('/shares/<int:share_id>', methods=['DELETE'])
@token_required
def revoke_report_share(current_user, share_id):
    """Revoke (immediately disable) a share link."""
    share = ReportShare.query.filter_by(id=share_id, user_id=current_user.id).first()
    if not share:
        return jsonify({'error': 'Share not found'}), 404
    if not share.revoked:
        share.revoked = True
        share.revoked_at = datetime.utcnow()
        db.session.commit()
        security_audit.data_export(current_user.id, current_user.email, 'report_share_revoked')
    return jsonify({'message': 'Share link revoked'})


def _lookup_active_share(token):
    """Resolve a raw token to a ReportShare. Returns (share, error_response).

    error_response is a ready (json, status) tuple when the link is invalid;
    distinguishing expired/revoked is safe since the caller already holds the
    secret token.
    """
    if not token or len(token) < 20:
        return None, (jsonify({'error': 'Invalid link', 'status': 'invalid'}), 404)
    share = ReportShare.query.filter_by(token_hash=ReportShare.hash_token(token)).first()
    if not share:
        return None, (jsonify({'error': 'Link not found', 'status': 'invalid'}), 404)
    if share.revoked:
        return None, (jsonify({'error': 'This link has been revoked', 'status': 'revoked'}), 410)
    if share.is_expired():
        return None, (jsonify({'error': 'This link has expired', 'status': 'expired'}), 410)
    return share, None


@reports_bp.route('/shared/<token>', methods=['GET'])
def view_shared_report(token):
    """PUBLIC (no auth): return the aggregate report for a valid share token.

    Rate-limited in create_app(). Discloses only aggregate financials and
    vehicle make/model/name — never owner identity, VIN, plate or attachments.
    """
    share, err = _lookup_active_share(token)
    if err:
        return err

    owner = share.user
    if not owner or not owner.is_active:
        return jsonify({'error': 'Link not found', 'status': 'invalid'}), 404

    try:
        vehicles = _resolve_report_vehicles(owner, share.vehicle_ids)
        summary = _report_summary(owner, vehicles, share.period, share.year, share.month)
    except Exception as e:
        current_app.logger.error(f'Shared report render failed: {e}')
        return jsonify({'error': 'Unable to load this report right now'}), 500

    # Access telemetry (best-effort; never blocks the response).
    try:
        share.access_count = (share.access_count or 0) + 1
        share.last_accessed_at = datetime.utcnow()
        db.session.commit()
    except Exception:
        db.session.rollback()

    summary['label'] = share.label
    summary['app_name'] = current_app.config.get('APP_NAME', 'GearCargo')
    summary['expires_at'] = share.expires_at.replace(tzinfo=timezone.utc).isoformat() if share.expires_at else None
    return jsonify(summary)


@reports_bp.route('/shared/<token>/pdf', methods=['GET'])
def download_shared_report_pdf(token):
    """PUBLIC (no auth): download the PDF for a valid share token. Rate-limited."""
    share, err = _lookup_active_share(token)
    if err:
        return err

    owner = share.user
    if not owner or not owner.is_active:
        return jsonify({'error': 'Link not found', 'status': 'invalid'}), 404

    try:
        vehicles = _resolve_report_vehicles(owner, share.vehicle_ids)
        if not vehicles:
            return jsonify({'error': 'No data'}), 404
        language = getattr(owner, 'language', 'en') or 'en'
        pdf_buffer = generate_pdf_report(
            user=owner, vehicles=vehicles, period=share.period,
            year=share.year, month=share.month, language=language,
        )
        filename = get_report_filename(vehicles, share.period, share.year, share.month)
        return send_file(pdf_buffer, mimetype='application/pdf',
                         as_attachment=True, download_name=filename)
    except Exception as e:
        current_app.logger.error(f'Shared report PDF failed: {e}')
        return jsonify({'error': 'Failed to generate report'}), 500

"""
GearCargo - Reports Routes
PDF report generation for vehicle expenses
"""

from datetime import datetime
from flask import Blueprint, request, jsonify, send_file, current_app

from app.models import Vehicle
from app.routes.auth import token_required
from app.services.pdf_report_service import (
    generate_pdf_report, get_report_filename, get_period_dates
)

reports_bp = Blueprint('reports', __name__)


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

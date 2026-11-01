"""
GearCargo - PDF Report Generation Service
Generates comprehensive vehicle expense reports in PDF format.
"""

import io
import os
import threading
from datetime import datetime, timedelta, timezone
from dateutil.relativedelta import relativedelta
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, HRFlowable
)
from reportlab.lib.enums import TA_CENTER
from flask import current_app

from app.models import (
    FuelEntry, ServiceEntry, RepairEntry,
    TaxEntry, ParkingEntry, InsurancePolicy
)


# Colors
BRAND_COLOR = colors.HexColor('#3B82F6')  # Blue
BRAND_COLOR_LIGHT = colors.HexColor('#EFF6FF')
HEADER_BG = colors.HexColor('#1E3A5F')
TEXT_COLOR = colors.HexColor('#1F2937')
TEXT_MUTED = colors.HexColor('#6B7280')
SUCCESS_COLOR = colors.HexColor('#10B981')
WARNING_COLOR = colors.HexColor('#F59E0B')
DANGER_COLOR = colors.HexColor('#EF4444')
_SHARED_FONT_LOCK = threading.Lock()


def vehicle_label(vehicle):
    """Make + model, falling back to the name the owner gave the car.

    R4-09: `f"{vehicle.make} {vehicle.model}"` rendered "None None" for a vehicle
    identified only by its name — in the report heading, the per-vehicle total
    row and the download filename.
    """
    return (f"{vehicle.make or ''} {vehicle.model or ''}".strip()
            or vehicle.name
            or 'Vehicle')


def get_period_dates(period, year=None, month=None):
    """
    Calculate start and end dates based on period type.
    
    Args:
        period: 'current_month', 'last_month', '3_months', 'year', or 'custom'
        year: Year for custom period
        month: Month for custom period (1-12)
    
    Returns:
        tuple: (start_date, end_date, period_label)
    """
    today = datetime.now(timezone.utc)
    
    if period == 'current_month':
        start_date = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # End of current month
        if today.month == 12:
            end_date = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end_date = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        end_date = end_date.replace(hour=23, minute=59, second=59)
        period_label = today.strftime('%B %Y')
        
    elif period == 'last_month':
        first_of_current = today.replace(day=1)
        end_date = first_of_current - timedelta(days=1)
        end_date = end_date.replace(hour=23, minute=59, second=59)
        start_date = end_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        period_label = start_date.strftime('%B %Y')
        
    elif period == '3_months':
        end_date = today.replace(hour=23, minute=59, second=59)
        start_date = today - relativedelta(months=3)
        start_date = start_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        period_label = f"{start_date.strftime('%B %Y')} - {end_date.strftime('%B %Y')}"
        
    elif period == 'year':
        if year:
            start_date = datetime(year, 1, 1, 0, 0, 0)
            end_date = datetime(year, 12, 31, 23, 59, 59)
            period_label = str(year)
        else:
            start_date = today.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            end_date = today.replace(month=12, day=31, hour=23, minute=59, second=59)
            period_label = str(today.year)
            
    elif period == 'custom' and year and month:
        start_date = datetime(year, month, 1, 0, 0, 0)
        if month == 12:
            end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = datetime(year, month + 1, 1) - timedelta(days=1)
        end_date = end_date.replace(hour=23, minute=59, second=59)
        period_label = start_date.strftime('%B %Y')
        
    else:
        # Default to current month
        start_date = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if today.month == 12:
            end_date = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end_date = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        end_date = end_date.replace(hour=23, minute=59, second=59)
        period_label = today.strftime('%B %Y')
    
    return start_date, end_date, period_label


def get_vehicle_entries(vehicle, start_date, end_date, currency='EUR', rates=None):
    """Detailed private rows from the same dated ledger used by JSON totals."""
    from app.services.expense_ledger import CATEGORIES, load_expenses, aggregate, convert
    rows = load_expenses([vehicle.id], start_date, end_date)
    ledger = aggregate(rows, currency, rates or {}, start_date, end_date)
    result = {key: [] for key in CATEGORIES}
    result['totals'] = {**ledger['totals'], 'converted': ledger['converted'],
                        'fx_applied': ledger['fx_applied']}
    result['ledger'] = ledger
    for row in rows:
        entry = row.source
        amount = convert(row.amount, row.currency, currency, rates or {})
        if row.category == 'fuel':
            parts = []
            if entry.liters is not None:
                parts.append(f'{entry.liters:.2f}L')
            if entry.price_per_liter is not None:
                parts.append(f'{entry.price_per_liter:.2f} {entry.currency or currency}/L')
            description = ' @ '.join(parts) or '-'
        elif row.category == 'insurance':
            description = f'{entry.provider} - {entry.policy_type or "Policy"} (scheduled estimate)'
        else:
            description = (getattr(entry, 'service_type', None) or
                getattr(entry, 'tax_type', None) or getattr(entry, 'location', None) or
                entry.description or entry.title or row.category)
            if row.category in ('service', 'tax'):
                description = description.replace('_', ' ')
        if amount is None:
            description += f' ({row.amount:.2f} {row.currency or "unknown currency"}; rate unavailable)'
        elif row.currency != currency and row.amount:
            description += f' ({row.amount:.2f} {row.currency})'
        odometer = getattr(entry, 'odometer', None)
        result[row.category].append({'date': row.date.strftime('%d/%m/%Y'),
            'description': description, 'amount': float(amount) if amount is not None else None,
            'odometer': f'{odometer:,} {vehicle.distance_unit or "km"}' if odometer else '-'})
    return result


def create_header_footer(canvas, doc, report_data):
    """Add header and footer to each page."""
    canvas.saveState()
    
    # Header - Logo and title (already handled in document flow for first page)
    # Just add page numbers in footer
    
    # Footer
    page_num = canvas.getPageNumber()
    footer_text = f"Page {page_num}"
    canvas.setFont('Helvetica', 9)
    canvas.setFillColor(TEXT_MUTED)
    canvas.drawCentredString(doc.width / 2 + doc.leftMargin, 0.5 * inch, footer_text)
    
    canvas.restoreState()


def generate_pdf_report(user, vehicles, period, year=None, month=None, language='en'):
    """
    Generate a comprehensive PDF report for vehicle expenses.
    
    Args:
        user: Current user object
        vehicles: List of vehicle objects or 'all'
        period: Time period ('current_month', 'last_month', '3_months', 'year', 'custom')
        year: Year for 'year' or 'custom' period
        month: Month for 'custom' period
        language: Language code for translations
    
    Returns:
        BytesIO buffer containing the PDF
    """
    # Get period dates
    start_date, end_date, period_label = get_period_dates(period, year, month)
    
    # Get currency from user preferences or default
    currency = (getattr(user, 'currency', None) or 'GBP').upper()

    # F1: fetch EUR-based rates once so every entry amount is converted into the
    # report currency before it is summed. Guarded so PDF generation never fails
    # just because rates are unavailable (affected amounts are excluded and flagged).
    rates = None
    try:
        from flask import current_app
        from app.services.currency import get_rates_cached
        rates = get_rates_cached(current_app._get_current_object())
    except Exception:
        rates = None

    # Create buffer
    buffer = io.BytesIO()
    
    # Create document
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch
    )
    
    # Styles
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=HEADER_BG,
        spaceAfter=6,
        alignment=TA_CENTER
    )
    
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=12,
        textColor=TEXT_MUTED,
        spaceAfter=20,
        alignment=TA_CENTER
    )
    
    section_title_style = ParagraphStyle(
        'SectionTitle',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=BRAND_COLOR,
        spaceBefore=20,
        spaceAfter=10,
        borderPadding=5,
        keepWithNext=True
    )
    
    vehicle_title_style = ParagraphStyle(
        'VehicleTitle',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=HEADER_BG,
        spaceBefore=25,
        spaceAfter=10
    )
    
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=10,
        textColor=TEXT_COLOR
    )
    
    footer_style = ParagraphStyle(
        'FooterStyle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=TEXT_MUTED,
        alignment=TA_CENTER,
        spaceBefore=30
    )
    
    thank_you_style = ParagraphStyle(
        'ThankYou',
        parent=styles['Normal'],
        fontSize=11,
        textColor=BRAND_COLOR,
        alignment=TA_CENTER,
        spaceBefore=40,
        spaceAfter=10
    )
    
    # Build document elements
    elements = []
    
    # ===== HEADER SECTION =====
    # The app mark. The old lookup joined root_path (the `app` package) with
    # `static`, but static sits beside it — the path never matched, so every
    # report silently rendered without a logo.
    from app.utils.branding import app_mark_path

    logo_paths = [path for path in
                  (app_mark_path('logo.png'), app_mark_path('logo-192.png'))
                  if path]
    
    logo_found = False
    for logo_path in logo_paths:
        try:
            if os.path.exists(logo_path):
                logo = Image(logo_path, width=1.2*inch, height=1.2*inch)
                logo.hAlign = 'CENTER'
                elements.append(logo)
                logo_found = True
                break
        except Exception as e:
            current_app.logger.warning(f"Failed to load logo from {logo_path}: {e}")
            continue
    
    if not logo_found:
        # Use styled text as fallback
        elements.append(Spacer(1, 0.2*inch))
    
    # App name
    elements.append(Paragraph("GearCargo", title_style))
    elements.append(Paragraph("Vehicle Expense Report", subtitle_style))
    
    # Horizontal line
    elements.append(HRFlowable(
        width="100%",
        thickness=2,
        color=BRAND_COLOR,
        spaceBefore=5,
        spaceAfter=15
    ))
    
    # Report info box
    generated_date = datetime.now(timezone.utc).strftime('%d %B %Y at %H:%M')
    
    # Build vehicle names list
    if isinstance(vehicles, list) and len(vehicles) > 0:
        vehicle_names = ', '.join([vehicle_label(v) + (f" ({v.license_plate})" if v.license_plate else '') for v in vehicles])
        vehicle_count = len(vehicles)
    else:
        vehicle_names = "All Vehicles"
        vehicle_count = 0
    
    info_data = [
        ['Report Period:', period_label],
        ['Generated:', generated_date],
        ['Vehicles:', vehicle_names if len(vehicle_names) < 60 else f"{vehicle_count} vehicles"],
        ['Prepared for:', user.email or user.username or 'User']
    ]
    
    info_table = Table(info_data, colWidths=[1.5*inch, 4.5*inch])
    info_table.setStyle(TableStyle([
        ('FONT', (0, 0), (0, -1), 'Helvetica-Bold', 10),
        ('FONT', (1, 0), (1, -1), 'Helvetica', 10),
        ('TEXTCOLOR', (0, 0), (-1, -1), TEXT_COLOR),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 0.3*inch))
    
    from app.services.expense_ledger import BASIS_LABEL
    from app.utils.timeutils import utc_today
    elements.append(Paragraph(BASIS_LABEL, normal_style))
    elements.append(Paragraph(f'As of {utc_today().isoformat()}. Current exchange rates are used.', normal_style))

    # ===== VEHICLE SECTIONS =====
    grand_totals = {
        'fuel': 0,
        'service': 0,
        'repair': 0,
        'tax': 0,
        'parking': 0,
        'insurance': 0,
        'consumable': 0,
        'grand_total': 0
    }
    
    for vehicle in vehicles:
        # Vehicle header
        vehicle_name = vehicle_label(vehicle)
        if vehicle.year:
            vehicle_name += f" ({vehicle.year})"
        if vehicle.license_plate:
            vehicle_name += f" - {vehicle.license_plate}"
        
        elements.append(Paragraph(f"{vehicle_name}", vehicle_title_style))
        
        # Get entries for this vehicle
        entries = get_vehicle_entries(vehicle, start_date, end_date, currency, rates)
        
        if not entries['totals']['converted']:
            elements.append(Paragraph('Partial totals: amounts with unknown currency or unavailable exchange rates are excluded.', normal_style))

        # Add to grand totals
        for key in grand_totals:
            grand_totals[key] += entries['totals'][key]
        
        # Categories to display
        categories = [
            ('fuel', 'Fuel Entries', ['Date', 'Description', 'Odometer', 'Amount']),
            ('service', 'Service & Maintenance', ['Date', 'Service Type', 'Odometer', 'Cost']),
            ('repair', 'Repairs', ['Date', 'Description', 'Odometer', 'Cost']),
            ('tax', 'Road Tax', ['Date', 'Tax Type', '-', 'Amount']),
            ('parking', 'Parking', ['Date', 'Location', '-', 'Cost']),
            ('consumable', 'Consumables', ['Date', 'Description', 'Odometer', 'Cost']),
            ('insurance', 'Insurance (scheduled estimates)', ['Date', 'Provider / Policy', '-', 'Premium']),
        ]
        
        has_entries = False
        
        for cat_key, cat_title, headers in categories:
            if entries[cat_key]:
                has_entries = True
                elements.append(Paragraph(cat_title, section_title_style))
                
                # Build table data
                table_data = [['Date', 'Description', 'Odometer', f'Amount ({currency})']]
                for entry in entries[cat_key]:
                    table_data.append([
                        entry['date'],
                        entry['description'][:40] + '...' if len(entry['description']) > 40 else entry['description'],
                        entry['odometer'],
                        f"{entry['amount']:,.2f}" if entry['amount'] is not None else "Excluded (FX)"
                    ])
                
                # Category subtotal
                table_data.append(['', '', 'Subtotal:', f"{entries['totals'][cat_key]:,.2f}"])
                
                # Create table
                cat_table = Table(table_data, colWidths=[1.1*inch, 3*inch, 1*inch, 1.1*inch], repeatRows=1)
                cat_table.setStyle(TableStyle([
                    # Header row
                    ('BACKGROUND', (0, 0), (-1, 0), BRAND_COLOR),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 9),
                    ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                    
                    # Data rows
                    ('FONT', (0, 1), (-1, -2), 'Helvetica', 9),
                    ('TEXTCOLOR', (0, 1), (-1, -2), TEXT_COLOR),
                    ('ALIGN', (0, 1), (0, -1), 'LEFT'),
                    ('ALIGN', (-1, 1), (-1, -1), 'RIGHT'),
                    ('ALIGN', (-2, 1), (-2, -1), 'CENTER'),
                    
                    # Subtotal row
                    ('FONT', (0, -1), (-1, -1), 'Helvetica-Bold', 9),
                    ('BACKGROUND', (0, -1), (-1, -1), BRAND_COLOR_LIGHT),
                    ('TEXTCOLOR', (-2, -1), (-1, -1), BRAND_COLOR),
                    
                    # Grid
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.Color(0.9, 0.9, 0.9)),
                    ('LINEBELOW', (0, 0), (-1, 0), 1, BRAND_COLOR),
                    
                    # Padding
                    ('TOPPADDING', (0, 0), (-1, -1), 6),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                    ('LEFTPADDING', (0, 0), (-1, -1), 6),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                    
                    # Alternate row colors
                    *[('BACKGROUND', (0, i), (-1, i), colors.Color(0.98, 0.98, 0.98)) 
                      for i in range(2, len(table_data)-1, 2)]
                ]))
                elements.append(cat_table)
                elements.append(Spacer(1, 0.15*inch))
        
        if not has_entries:
            elements.append(Paragraph(
                "No entries recorded for this period.",
                ParagraphStyle('NoData', parent=normal_style, textColor=TEXT_MUTED, fontStyle='italic')
            ))
        
        # Vehicle total
        elements.append(Spacer(1, 0.1*inch))
        vehicle_total_data = [[
            f"Total for {vehicle_label(vehicle)}:",
            f"{entries['totals']['grand_total']:,.2f} {currency}"
        ]]
        vehicle_total_table = Table(vehicle_total_data, colWidths=[4.5*inch, 1.7*inch])
        vehicle_total_table.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, -1), 'Helvetica-Bold', 11),
            ('TEXTCOLOR', (0, 0), (0, 0), HEADER_BG),
            ('TEXTCOLOR', (1, 0), (1, 0), SUCCESS_COLOR),
            ('ALIGN', (0, 0), (0, 0), 'RIGHT'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('BACKGROUND', (0, 0), (-1, -1), BRAND_COLOR_LIGHT),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ]))
        elements.append(vehicle_total_table)
        elements.append(Spacer(1, 0.3*inch))
    
    # ===== SUMMARY SECTION (if multiple vehicles) =====
    if len(vehicles) > 1:
        elements.append(HRFlowable(
            width="100%",
            thickness=1,
            color=BRAND_COLOR,
            spaceBefore=20,
            spaceAfter=20
        ))
        
        elements.append(Paragraph("Summary - All Vehicles", vehicle_title_style))
        
        summary_data = [
            ['Category', f'Total ({currency})'],
            ['Fuel', f"{grand_totals['fuel']:,.2f}"],
            ['Service & Maintenance', f"{grand_totals['service']:,.2f}"],
            ['Repairs', f"{grand_totals['repair']:,.2f}"],
            ['Road Tax', f"{grand_totals['tax']:,.2f}"],
            ['Parking', f"{grand_totals['parking']:,.2f}"],
            ['Consumables', f"{grand_totals['consumable']:,.2f}"],
            ['Insurance (scheduled estimates)', f"{grand_totals['insurance']:,.2f}"],
            ['GRAND TOTAL', f"{grand_totals['grand_total']:,.2f}"],
        ]
        
        summary_table = Table(summary_data, colWidths=[4*inch, 2.2*inch])
        summary_table.setStyle(TableStyle([
            # Header
            ('BACKGROUND', (0, 0), (-1, 0), HEADER_BG),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 10),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            
            # Data rows
            ('FONT', (0, 1), (-1, -2), 'Helvetica', 10),
            ('TEXTCOLOR', (0, 1), (-1, -2), TEXT_COLOR),
            ('ALIGN', (0, 1), (0, -1), 'LEFT'),
            ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
            
            # Grand total row
            ('FONT', (0, -1), (-1, -1), 'Helvetica-Bold', 12),
            ('BACKGROUND', (0, -1), (-1, -1), BRAND_COLOR),
            ('TEXTCOLOR', (0, -1), (-1, -1), colors.white),
            
            # Grid
            ('GRID', (0, 0), (-1, -1), 0.5, colors.Color(0.9, 0.9, 0.9)),
            ('LINEBELOW', (0, -2), (-1, -2), 1, BRAND_COLOR),
            
            # Padding
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
            
            # Alternate row colors
            *[('BACKGROUND', (0, i), (-1, i), colors.Color(0.98, 0.98, 0.98)) 
              for i in range(2, len(summary_data)-1, 2)]
        ]))
        elements.append(summary_table)
    
    # ===== FOOTER / THANK YOU NOTE =====
    elements.append(Spacer(1, 0.5*inch))
    elements.append(HRFlowable(
        width="60%",
        thickness=1,
        color=TEXT_MUTED,
        spaceBefore=20,
        spaceAfter=20
    ))
    
    thank_you_text = """
    Thank you for choosing GearCargo!<br/>
    <font size="9" color="#6B7280">
    Your trusted companion for vehicle expense tracking and management.<br/>
    This report was automatically generated. For questions or support, visit our app.
    </font>
    """
    elements.append(Paragraph(thank_you_text, thank_you_style))
    
    # Generation timestamp
    elements.append(Paragraph(
        f"Generated on {generated_date}",
        ParagraphStyle('Timestamp', parent=footer_style, fontSize=8)
    ))
    
    # Build PDF
    doc.build(elements, onFirstPage=lambda canvas, doc: create_header_footer(canvas, doc, None),
              onLaterPages=lambda canvas, doc: create_header_footer(canvas, doc, None))
    
    # Reset buffer position
    buffer.seek(0)
    
    return buffer


def get_report_filename(vehicles, period, year=None, month=None):
    """Generate a descriptive filename for the report."""
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d')
    
    if len(vehicles) == 1:
        vehicle_part = vehicle_label(vehicles[0]).replace(' ', '_')
    else:
        vehicle_part = f"{len(vehicles)}_vehicles"
    
    period_part = period.replace('_', '-')
    if year:
        period_part += f"_{year}"
    if month:
        period_part += f"_{month:02d}"
    
    return f"GearCargo_Report_{vehicle_part}_{period_part}_{timestamp}.pdf"


def get_shared_report_filename(report):
    """Public filenames contain dates only, never labels, identities or tokens."""
    from app.services.shared_report import SharedReport
    if not isinstance(report, SharedReport):
        raise TypeError('Public PDF requires a SharedReport')
    return f'GearCargo_Shared_Report_{report.start_date}_{report.end_date}.pdf'


def generate_shared_pdf_report(report):
    """Render only the same allowlisted values returned by public JSON.

    Intentionally separate from generate_pdf_report: no user/vehicle ORM object,
    entry accessor, private header, attachment or owner filename is available.
    """
    from pathlib import Path
    from xml.sax.saxutils import escape
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from app.services.shared_report import SharedReport, SHARED_CATEGORIES

    if not isinstance(report, SharedReport):
        raise TypeError('Public PDF requires a SharedReport')

    # Existing Linux runtime fonts cover the supported EN/RO/ES text. Keep the
    # private export's typography and behavior independent of this renderer.
    font, bold = 'Helvetica', 'Helvetica-Bold'
    directory = Path('/usr/share/fonts/truetype/dejavu')
    if (directory / 'DejaVuSans.ttf').is_file() and (directory / 'DejaVuSans-Bold.ttf').is_file():
        font, bold = 'SharedSans', 'SharedSansBold'
        with _SHARED_FONT_LOCK:
            if font not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(font, str(directory / 'DejaVuSans.ttf')))
            if bold not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(bold, str(directory / 'DejaVuSans-Bold.ttf')))

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=48, rightMargin=48,
                            topMargin=44, bottomMargin=52,
                            title='Shared Expense Report', author='GearCargo',
                            subject='Aggregate vehicle expense summary',
                            creator='GearCargo public report renderer', keywords='')
    styles = getSampleStyleSheet()
    body = ParagraphStyle('SharedBody', parent=styles['BodyText'], fontName=font,
                          fontSize=9, leading=14, textColor=TEXT_COLOR,
                          splitLongWords=True)
    title = ParagraphStyle('SharedTitle', parent=body, fontName=bold,
                           fontSize=22, leading=28, textColor=HEADER_BG, spaceAfter=12)
    heading = ParagraphStyle('SharedHeading', parent=body, fontName=bold,
                             fontSize=12, leading=17, spaceBefore=14, spaceAfter=8)
    small = ParagraphStyle('SharedSmall', parent=body, fontSize=8, leading=12,
                           textColor=TEXT_MUTED)

    def paragraph(value, style=body):
        # Labels/names are deliberately public free text, never ReportLab XML.
        return Paragraph(escape('' if value is None else str(value)), style)

    def table(rows, widths):
        result = Table(rows, colWidths=widths, repeatRows=1, hAlign='LEFT')
        result.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), BRAND_COLOR_LIGHT),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LINEBELOW', (0, 0), (-1, 0), .6, BRAND_COLOR),
            ('LINEBELOW', (0, 1), (-1, -1), .3, colors.HexColor('#E5E7EB')),
            ('LEFTPADDING', (0, 0), (-1, -1), 9),
            ('RIGHTPADDING', (0, 0), (-1, -1), 9),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        return result

    elements = [paragraph(report.app_name, small), paragraph(report.label or 'Expense Report', title),
                paragraph('Read-only shared report', small),
                HRFlowable(width='100%', thickness=1.5, color=BRAND_COLOR, spaceBefore=10, spaceAfter=12),
                paragraph(report.period_label),
                paragraph(f'{report.start_date} - {report.end_date}', small),
                paragraph(f'{report.entry_counts["total"]} entries | {len(report.vehicles)} vehicle(s)', small),
                paragraph(report.basis_label, small),
                paragraph(f'As of {report.as_of}. Current exchange rates are used.', small),
                paragraph('Expense totals', heading)]
    category_titles = {'fuel': 'Fuel', 'service': 'Service', 'repair': 'Repairs',
                       'tax': 'Tax', 'parking': 'Parking', 'consumable': 'Consumables', 'insurance': 'Insurance (estimate)'}
    rows = [[paragraph('Category'), paragraph('Entries'), paragraph(f'Amount ({report.currency})')]]
    for key in SHARED_CATEGORIES:
        rows.append([paragraph(category_titles[key]), paragraph(report.entry_counts[key]),
                     paragraph(f'{report.totals[key]:,.2f}')])
    rows.append([paragraph('Grand total'), paragraph(report.entry_counts['total']),
                 paragraph(f'{report.totals["grand_total"]:,.2f}')])
    elements.append(table(rows, [doc.width * .47, doc.width * .18, doc.width * .35]))
    if not report.converted:
        elements.append(paragraph('Partial totals: amounts with unknown currency or unavailable exchange rates are excluded.', small))
    elif report.fx_applied:
        elements.append(paragraph(f'Amounts converted to {report.currency}.', small))
    elements.append(paragraph('Vehicles', heading))
    rows = [[paragraph('Name'), paragraph('Make'), paragraph('Model')]]
    rows.extend([[paragraph(v.name), paragraph(v.make or '-'), paragraph(v.model or '-')]
                 for v in report.vehicles])
    elements.append(table(rows, [doc.width * .5, doc.width * .25, doc.width * .25]))
    elements += [Spacer(1, 16),
                 paragraph('This page and PDF share only vehicle names, makes/models, report dates, category totals and counts. Owner identity, plates, VINs, notes and attachments are excluded.', small),
                 paragraph('Names and report labels are shared as written. Downloaded copies cannot be recalled by revoking the link.', small)]
    if report.expires_at:
        elements.append(paragraph(f'Link expires: {report.expires_at}', small))

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont(font, 8)
        canvas.setFillColor(TEXT_MUTED)
        canvas.drawString(document.leftMargin, 28, 'Read-only shared report')
        canvas.drawRightString(A4[0] - document.rightMargin, 28, f'Page {canvas.getPageNumber()}')
        canvas.restoreState()

    doc.build(elements, onFirstPage=footer, onLaterPages=footer)
    buffer.seek(0)
    return buffer

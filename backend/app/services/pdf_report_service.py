"""
GearCargo - PDF Report Generation Service
Generates comprehensive vehicle expense reports in PDF format.
"""

import io
import os
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, PageBreak, HRFlowable
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from flask import current_app

from app import db
from app.models import (
    Vehicle, FuelEntry, ServiceEntry, RepairEntry,
    TaxEntry, ParkingEntry, InsurancePolicy, Reminder
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
    today = datetime.now()
    
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


def get_vehicle_entries(vehicle, start_date, end_date, currency='EUR'):
    """
    Get all entries for a vehicle within the date range.
    
    Returns dict with categorized entries and totals.
    """
    entries = {
        'fuel': [],
        'service': [],
        'repair': [],
        'tax': [],
        'parking': [],
        'insurance': [],
        'totals': {
            'fuel': 0,
            'service': 0,
            'repair': 0,
            'tax': 0,
            'parking': 0,
            'insurance': 0,
            'grand_total': 0
        }
    }
    
    # Fuel entries
    fuel_entries = FuelEntry.query.filter(
        FuelEntry.vehicle_id == vehicle.id,
        FuelEntry.date >= start_date,
        FuelEntry.date <= end_date
    ).order_by(FuelEntry.date).all()
    
    for entry in fuel_entries:
        entries['fuel'].append({
            'date': entry.date.strftime('%Y-%m-%d'),
            'description': f"{entry.liters:.2f}L @ {entry.price_per_liter:.2f} {currency}/L",
            'odometer': f"{entry.odometer:,} km" if entry.odometer else '-',
            'amount': float(entry.total_price) if entry.total_price else 0
        })
        entries['totals']['fuel'] += float(entry.total_price) if entry.total_price else 0
    
    # Service entries
    service_entries = ServiceEntry.query.filter(
        ServiceEntry.vehicle_id == vehicle.id,
        ServiceEntry.date >= start_date,
        ServiceEntry.date <= end_date
    ).order_by(ServiceEntry.date).all()
    
    for entry in service_entries:
        entries['service'].append({
            'date': entry.date.strftime('%Y-%m-%d'),
            'description': entry.service_type or 'Service',
            'odometer': f"{entry.odometer:,} km" if entry.odometer else '-',
            'amount': float(entry.amount) if entry.amount else 0
        })
        entries['totals']['service'] += float(entry.amount) if entry.amount else 0
    
    # Repair entries
    repair_entries = RepairEntry.query.filter(
        RepairEntry.vehicle_id == vehicle.id,
        RepairEntry.date >= start_date,
        RepairEntry.date <= end_date
    ).order_by(RepairEntry.date).all()
    
    for entry in repair_entries:
        entries['repair'].append({
            'date': entry.date.strftime('%Y-%m-%d'),
            'description': entry.description or 'Repair',
            'odometer': f"{entry.odometer:,} km" if entry.odometer else '-',
            'amount': float(entry.amount) if entry.amount else 0
        })
        entries['totals']['repair'] += float(entry.amount) if entry.amount else 0
    
    # Tax entries
    tax_entries = TaxEntry.query.filter(
        TaxEntry.vehicle_id == vehicle.id,
        TaxEntry.date >= start_date,
        TaxEntry.date <= end_date
    ).order_by(TaxEntry.date).all()
    
    for entry in tax_entries:
        entries['tax'].append({
            'date': entry.date.strftime('%Y-%m-%d') if entry.date else '-',
            'description': entry.tax_type or 'Road Tax',
            'odometer': '-',
            'amount': float(entry.amount) if entry.amount else 0
        })
        entries['totals']['tax'] += float(entry.amount) if entry.amount else 0
    
    # Parking entries
    parking_entries = ParkingEntry.query.filter(
        ParkingEntry.vehicle_id == vehicle.id,
        ParkingEntry.date >= start_date,
        ParkingEntry.date <= end_date
    ).order_by(ParkingEntry.date).all()
    
    for entry in parking_entries:
        entries['parking'].append({
            'date': entry.date.strftime('%Y-%m-%d'),
            'description': entry.location or 'Parking',
            'odometer': '-',
            'amount': float(entry.amount) if entry.amount else 0
        })
        entries['totals']['parking'] += float(entry.amount) if entry.amount else 0
    
    # Insurance entries (by start date within period)
    insurance_entries = InsurancePolicy.query.filter(
        InsurancePolicy.vehicle_id == vehicle.id,
        InsurancePolicy.start_date >= start_date,
        InsurancePolicy.start_date <= end_date
    ).order_by(InsurancePolicy.start_date).all()
    
    for entry in insurance_entries:
        entries['insurance'].append({
            'date': entry.start_date.strftime('%Y-%m-%d'),
            'description': f"{entry.provider or 'Insurance'} - {entry.policy_type or 'Policy'}",
            'odometer': '-',
            'amount': float(entry.premium) if entry.premium else 0
        })
        entries['totals']['insurance'] += float(entry.premium) if entry.premium else 0
    
    # Calculate grand total
    entries['totals']['grand_total'] = sum([
        entries['totals']['fuel'],
        entries['totals']['service'],
        entries['totals']['repair'],
        entries['totals']['tax'],
        entries['totals']['parking'],
        entries['totals']['insurance']
    ])
    
    return entries


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
    currency = getattr(user, 'currency', 'EUR') or 'EUR'
    
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
        borderPadding=5
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
    # Try multiple logo paths
    logo_paths = [
        os.path.join(current_app.root_path, 'static', 'icons', 'logo.png'),
        os.path.join(current_app.root_path, 'static', 'icons', 'logo-192.png'),
        os.path.join(current_app.root_path, 'static', 'icons', 'icon-192x192.png'),
    ]
    
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
    generated_date = datetime.now().strftime('%B %d, %Y at %H:%M')
    
    # Build vehicle names list
    if isinstance(vehicles, list) and len(vehicles) > 0:
        vehicle_names = ', '.join([f"{v.make} {v.model}" + (f" ({v.license_plate})" if v.license_plate else '') for v in vehicles])
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
    
    # ===== VEHICLE SECTIONS =====
    grand_totals = {
        'fuel': 0,
        'service': 0,
        'repair': 0,
        'tax': 0,
        'parking': 0,
        'insurance': 0,
        'grand_total': 0
    }
    
    for vehicle in vehicles:
        # Vehicle header
        vehicle_name = f"{vehicle.make} {vehicle.model}"
        if vehicle.year:
            vehicle_name += f" ({vehicle.year})"
        if vehicle.license_plate:
            vehicle_name += f" - {vehicle.license_plate}"
        
        elements.append(Paragraph(f"🚗 {vehicle_name}", vehicle_title_style))
        
        # Get entries for this vehicle
        entries = get_vehicle_entries(vehicle, start_date, end_date, currency)
        
        # Add to grand totals
        for key in grand_totals:
            grand_totals[key] += entries['totals'][key]
        
        # Categories to display
        categories = [
            ('fuel', '⛽ Fuel Entries', ['Date', 'Description', 'Odometer', 'Amount']),
            ('service', '🔧 Service & Maintenance', ['Date', 'Service Type', 'Odometer', 'Cost']),
            ('repair', '🛠️ Repairs', ['Date', 'Description', 'Odometer', 'Cost']),
            ('tax', '📋 Road Tax', ['Date', 'Tax Type', '-', 'Amount']),
            ('parking', '🅿️ Parking', ['Date', 'Location', '-', 'Cost']),
            ('insurance', '🛡️ Insurance', ['Date', 'Provider / Policy', '-', 'Premium']),
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
                        f"{entry['amount']:,.2f}"
                    ])
                
                # Category subtotal
                table_data.append(['', '', 'Subtotal:', f"{entries['totals'][cat_key]:,.2f}"])
                
                # Create table
                cat_table = Table(table_data, colWidths=[1.1*inch, 3*inch, 1*inch, 1.1*inch])
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
            f"Total for {vehicle.make} {vehicle.model}:",
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
        
        elements.append(Paragraph("📊 Summary - All Vehicles", vehicle_title_style))
        
        summary_data = [
            ['Category', f'Total ({currency})'],
            ['⛽ Fuel', f"{grand_totals['fuel']:,.2f}"],
            ['🔧 Service & Maintenance', f"{grand_totals['service']:,.2f}"],
            ['🛠️ Repairs', f"{grand_totals['repair']:,.2f}"],
            ['📋 Road Tax', f"{grand_totals['tax']:,.2f}"],
            ['🅿️ Parking', f"{grand_totals['parking']:,.2f}"],
            ['🛡️ Insurance', f"{grand_totals['insurance']:,.2f}"],
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
    doc.build(elements)
    
    # Reset buffer position
    buffer.seek(0)
    
    return buffer


def get_report_filename(vehicles, period, year=None, month=None):
    """Generate a descriptive filename for the report."""
    timestamp = datetime.now().strftime('%Y%m%d')
    
    if len(vehicles) == 1:
        vehicle_part = f"{vehicles[0].make}_{vehicles[0].model}".replace(' ', '_')
    else:
        vehicle_part = f"{len(vehicles)}_vehicles"
    
    period_part = period.replace('_', '-')
    if year:
        period_part += f"_{year}"
    if month:
        period_part += f"_{month:02d}"
    
    return f"GearCargo_Report_{vehicle_part}_{period_part}_{timestamp}.pdf"

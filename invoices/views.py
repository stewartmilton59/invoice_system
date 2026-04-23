from .models import District, Facility, Invoice, ActivityLog, UserProfile, Notification
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Sum, F, Value, DecimalField, ExpressionWrapper, Count, Q
from django.db.models.functions import Coalesce
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login as auth_login
from django.http import HttpResponse
from .forms import SearchForm, DateRangeForm, PaymentUpdateForm, SignupForm, DistrictForm, FacilityForm, InvoiceForm, UserUpdateForm, ProfileUpdateForm, ProfilePictureForm
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
import matplotlib.pyplot as plt
import base64
import io
from datetime import datetime, timedelta
from django.utils import timezone
import json
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm


@login_required
def profile_view(request):
    """View user profile"""
    return render(request, 'invoices/profile.html', {'user': request.user})

@login_required
def profile_settings(request):
    """Edit user profile settings"""
    if request.method == 'POST':
        user_form = UserUpdateForm(request.POST, instance=request.user)
        profile_form = ProfileUpdateForm(request.POST, request.FILES, instance=request.user.profile)

        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            messages.success(request, 'Your profile has been updated successfully!')
            return redirect('profile_settings')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        user_form = UserUpdateForm(instance=request.user)
        profile_form = ProfileUpdateForm(instance=request.user.profile)

    context = {
        'user_form': user_form,
        'profile_form': profile_form,
    }
    return render(request, 'invoices/profile_settings.html', context)

@login_required
def change_password(request):
    """Change user password"""
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  # Important!
            messages.success(request, 'Your password was successfully updated!')
            return redirect('profile_settings')
        else:
            messages.error(request, 'Please correct the error below.')
    else:
        form = PasswordChangeForm(request.user)

    return render(request, 'invoices/change_password.html', {'form': form})

@login_required
def upload_profile_picture(request):
    """Upload profile picture via AJAX"""
    if request.method == 'POST':
        form = ProfilePictureForm(request.POST, request.FILES, instance=request.user.profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile picture updated successfully!')
            return redirect('profile_settings')
        else:
            messages.error(request, 'Please select a valid image file.')

    return redirect('profile_settings')


# update invoice, facility, invoice
@login_required
@staff_member_required
def add_district(request):
    """Add a new district"""
    if request.method == 'POST':
        form = DistrictForm(request.POST)
        if form.is_valid():
            district = form.save()

            # Create activity log
            ActivityLog.objects.create(
                user=request.user,
                action='ADD_DISTRICT',
                message=f'Added new district: {district.name}'
            )

            messages.success(request, 'District added successfully!')
            return redirect('district_list')
    else:
        form = DistrictForm()

    return render(request, 'invoices/add_district.html', {'form': form, 'title': 'Add District'})

@login_required
@staff_member_required
def add_facility(request):
    """Add a new facility"""
    if request.method == 'POST':
        form = FacilityForm(request.POST)
        if form.is_valid():
            facility = form.save()

            # Create activity log
            ActivityLog.objects.create(
                user=request.user,
                action='ADD_FACILITY',
                message=f'Added new facility: {facility.name} in {facility.district.name} district'
            )

            messages.success(request, 'Facility added successfully!')
            return redirect('facility_list')
    else:
        form = FacilityForm()

    return render(request, 'invoices/add_facility.html', {'form': form, 'title': 'Add Facility'})

@login_required
@staff_member_required
def add_invoice(request):
    """Add a new invoice"""
    if request.method == 'POST':
        form = InvoiceForm(request.POST)
        if form.is_valid():
            invoice = form.save()

            # Create activity log
            ActivityLog.objects.create(
                user=request.user,
                action='ADD_INVOICE',
                message=f'Added new invoice #{invoice.invoice_number} for {invoice.facility.name}'
            )

            # Create notification for the user
            create_notification(
                user=request.user,
                title='New Invoice Added',
                message=f'Successfully added invoice #{invoice.invoice_number} for {invoice.facility.name}',
                notification_type='success',
                link=f'/facility/{invoice.facility.id}/'
            )

            messages.success(request, 'Invoice added successfully!')
            return redirect('all_invoices')
    else:
        form = InvoiceForm()

    return render(request, 'invoices/add_invoice.html', {'form': form, 'title': 'Add Invoice'})

@login_required
@staff_member_required
def district_list(request):
    """List all districts with edit/delete options"""
    districts = District.objects.all().order_by('name')
    return render(request, 'invoices/district_list.html', {'districts': districts})


@login_required
@staff_member_required
def facility_list(request):
    """List all facilities with edit/delete options"""
    facilities = Facility.objects.select_related('district').all().order_by('district__name', 'name')

    # Annotate facilities with invoice statistics
    facilities = facilities.annotate(
        invoice_count=Count('invoices'),
        total_invoiced=Coalesce(Sum('invoices__invoice_amount'), Value(0, output_field=DecimalField())),
        total_paid=Coalesce(Sum('invoices__amount_paid'), Value(0, output_field=DecimalField())),
        outstanding=ExpressionWrapper(
            Coalesce(Sum('invoices__invoice_amount'), Value(0)) - Coalesce(Sum('invoices__amount_paid'), Value(0)),
            output_field=DecimalField()
        )
    )

    # Get distinct districts for filter
    distinct_districts = District.objects.values_list('name', flat=True).distinct().order_by('name')

    # Calculate totals
    total_districts = District.objects.count()
    total_invoices = Invoice.objects.count()

    return render(request, 'invoices/facility_list.html', {
        'facilities': facilities,
        'distinct_districts': distinct_districts,
        'total_districts': total_districts,
        'total_invoices': total_invoices
    })


@login_required
@staff_member_required
def edit_district(request, district_id):
    """Edit an existing district"""
    district = get_object_or_404(District, pk=district_id)
    if request.method == 'POST':
        form = DistrictForm(request.POST, instance=district)
        if form.is_valid():
            old_name = district.name
            form.save()

            # Create activity log
            ActivityLog.objects.create(
                user=request.user,
                action='EDIT_DISTRICT',
                message=f'Edited district: {old_name} → {district.name}'
            )

            messages.success(request, 'District updated successfully!')
            return redirect('district_list')
    else:
        form = DistrictForm(instance=district)

    return render(request, 'invoices/add_district.html', {'form': form, 'title': 'Edit District', 'district': district})

@login_required
@staff_member_required
def edit_facility(request, facility_id):
    """Edit an existing facility"""
    facility = get_object_or_404(Facility, pk=facility_id)
    if request.method == 'POST':
        form = FacilityForm(request.POST, instance=facility)
        if form.is_valid():
            old_name = facility.name
            form.save()

            # Create activity log
            ActivityLog.objects.create(
                user=request.user,
                action='EDIT_FACILITY',
                message=f'Edited facility: {old_name} → {facility.name}'
            )

            messages.success(request, 'Facility updated successfully!')
            return redirect('facility_list')
    else:
        form = FacilityForm(instance=facility)

    return render(request, 'invoices/add_facility.html', {'form': form, 'title': 'Edit Facility', 'facility': facility})


@login_required
@staff_member_required
def delete_district(request, district_id):
    """Delete a district"""
    district = get_object_or_404(District, pk=district_id)
    if request.method == 'POST':
        district_name = district.name
        district.delete()

        # Create activity log
        ActivityLog.objects.create(
            user=request.user,
            action='DELETE_DISTRICT',
            message=f'Deleted district: {district_name}'
        )

        messages.success(request, f'District "{district_name}" deleted successfully!')
        return redirect('district_list')

    return render(request, 'invoices/confirm_delete.html', {
        'object': district,
        'object_type': 'District',
        'cancel_url': 'district_list'
    })

@login_required
@staff_member_required
def delete_facility(request, facility_id):
    """Delete a facility"""
    facility = get_object_or_404(Facility, pk=facility_id)
    if request.method == 'POST':
        facility_name = facility.name
        facility.delete()

        # Create activity log
        ActivityLog.objects.create(
            user=request.user,
            action='DELETE_FACILITY',
            message=f'Deleted facility: {facility_name}'
        )

        messages.success(request, f'Facility "{facility_name}" deleted successfully!')
        return redirect('facility_list')

    return render(request, 'invoices/confirm_delete.html', {
        'object': facility,
        'object_type': 'Facility',
        'cancel_url': 'facility_list'
    })

@login_required
@staff_member_required
def delete_invoice(request, invoice_id):
    """Delete an invoice"""
    invoice = get_object_or_404(Invoice, pk=invoice_id)
    if request.method == 'POST':
        invoice_number = invoice.invoice_number
        invoice.delete()

        # Create activity log
        ActivityLog.objects.create(
            user=request.user,
            action='DELETE_INVOICE',
            message=f'Deleted invoice #{invoice_number}'
        )

        messages.success(request, f'Invoice #{invoice_number} deleted successfully!')
        return redirect('all_invoices')

    return render(request, 'invoices/confirm_delete.html', {
        'object': invoice,
        'object_type': 'Invoice',
        'cancel_url': 'all_invoices'
    })

# upadte invoice, facility and disrtict

@login_required
@staff_member_required
def signup(request):
    if request.method == 'POST':
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            auth_login(request, user)

            # Create welcome notification
            create_notification(
                user=user,
                title='Welcome to the System!',
                message=f'Welcome {user.get_full_name or user.username}! Your account has been created successfully. Start managing your invoices today.',
                notification_type='success',
                link='/'
            )

            next_url = request.GET.get('next', '/')
            return redirect(next_url)
    else:
        form = SignupForm()
    return render(request, 'invoices/signup.html', {'form': form})


# ========== EXPORT FUNCTIONS ==========
@login_required
def export_to_excel(request):
    """Export all invoices to Excel"""
    invoices = Invoice.objects.select_related('facility__district').all().order_by('-invoice_date')

    data = []
    for inv in invoices:
        data.append({
            'Invoice Number': inv.invoice_number,
            'Facility': inv.facility.name,
            'District': inv.facility.district.name,
            'Invoice Date': inv.invoice_date,
            'Invoice Amount': float(inv.invoice_amount),
            'Payment Date': inv.payment_date or '',
            'Amount Paid': float(inv.amount_paid),
            'Balance': float(inv.balance)
        })

    df = pd.DataFrame(data)

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="invoices_{datetime.now().strftime("%Y%m%d")}.xlsx"'

    with pd.ExcelWriter(response, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='Invoices', index=False)

        # Format as currency
        workbook = writer.book
        worksheet = writer.sheets['Invoices']
        money_format = workbook.add_format({'num_format': '#,##0.00'})

        for col_num, col_name in enumerate(df.columns):
            if col_name in ['Invoice Amount', 'Amount Paid', 'Balance']:
                col_idx = col_num + 1
                worksheet.set_column(col_idx, col_idx, 15, money_format)

        # Add summary sheet
        summary_data = {
            'Metric': ['Total Invoiced', 'Total Paid', 'Total Outstanding', 'Number of Invoices'],
            'Value': [
                df['Invoice Amount'].sum(),
                df['Amount Paid'].sum(),
                df['Balance'].sum(),
                len(df)
            ]
        }
        summary_df = pd.DataFrame(summary_data)
        summary_df.to_excel(writer, sheet_name='Summary', index=False)

    return response

@login_required
def export_to_pdf(request):
    """Export all invoices to PDF"""
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="invoices_{datetime.now().strftime("%Y%m%d")}.pdf"'

    doc = SimpleDocTemplate(response, pagesize=landscape(letter))
    story = []

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        alignment=1,
        spaceAfter=20
    )
    title = Paragraph("Invoice Report", title_style)
    story.append(title)
    story.append(Spacer(1, 12))

    invoices = Invoice.objects.select_related('facility__district').all().order_by('-invoice_date')[:50]

    # Headers with proper order
    table_data = [['Invoice #', 'Facility', 'District', 'Date', 'Amount (TZS)', 'Paid (TZS)', 'Balance (TZS)', 'Payment Date']]

    for inv in invoices:
        # Format payment date (handle NULL/empty values)
        if inv.payment_date:
            payment_date = inv.payment_date.strftime('%Y-%m-%d')
        else:
            payment_date = ''  # Leave blank for unpaid invoices

        table_data.append([
            inv.invoice_number,
            inv.facility.name[:30],
            inv.facility.district.name[:20],
            inv.invoice_date.strftime('%Y-%m-%d'),
            f"{inv.invoice_amount:,.2f}",
            f"{inv.amount_paid:,.2f}",
            f"{inv.balance:,.2f}",
            payment_date
        ])

    # Set column widths for better display
    from reportlab.lib.units import inch
    col_widths = [1*inch, 2*inch, 1.2*inch, 0.9*inch, 1.1*inch, 1.1*inch, 1.1*inch, 1*inch]

    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ALIGN', (4, 1), (7, -1), 'RIGHT'),  # Right-align number columns
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))

    story.append(table)
    doc.build(story)
    return response

#####################################

@login_required
def export_filtered_excel(request):
    recent_activities = ActivityLog.objects.filter(user=request.user).order_by('-created_at')[:5]
    """Export filtered invoices to professional Excel format"""
    # Get filtered invoice IDs from session
    invoice_ids = request.session.get('filtered_invoice_ids', [])
    filter_params = request.session.get('filter_parameters', {})

    if not invoice_ids:
        messages.warning(request, 'No filtered invoices to export. Please apply a filter first.')
        return redirect('all_invoices')

    # Get the filtered invoices
    invoices = Invoice.objects.filter(id__in=invoice_ids).select_related('facility__district').order_by('-invoice_date')

    # Prepare data for export
    data = []
    for inv in invoices:
        data.append({
            'Invoice Number': inv.invoice_number,
            'Facility': inv.facility.name,
            'District': inv.facility.district.name,
            'Invoice Date': inv.invoice_date.strftime('%Y-%m-%d'),
            'Invoice Amount': float(inv.invoice_amount),
            'Payment Date': inv.payment_date.strftime('%Y-%m-%d') if inv.payment_date else 'Not Paid',
            'Amount Paid': float(inv.amount_paid),
            'Balance': float(inv.balance),
            'Payment Status': 'Paid' if inv.balance == 0 else 'Partial' if inv.amount_paid > 0 else 'Unpaid'
        })

    df = pd.DataFrame(data)

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"Invoice_Report_{timestamp}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    with pd.ExcelWriter(response, engine='xlsxwriter') as writer:

        # ========== SHEET 1: INVOICE REPORT ==========
        df.to_excel(writer, sheet_name='Invoice Report', index=False, startrow=4)

        workbook = writer.book
        worksheet = writer.sheets['Invoice Report']

        # Add company logo and header
        title_format = workbook.add_format({
            'bold': True,
            'font_size': 20,
            'font_color': '#2c3e50',
            'align': 'center',
            'valign': 'vcenter'
        })

        subtitle_format = workbook.add_format({
            'bold': True,
            'font_size': 12,
            'font_color': '#7f8c8d',
            'align': 'center'
        })

        # Merge cells for title
        worksheet.merge_range('A1:I1', 'ROBBY ONE PHARMACY', title_format)
        worksheet.merge_range('A2:I2', 'Financial Statement', subtitle_format)
        worksheet.merge_range('A3:I3', f'Report Generated: {datetime.now().strftime("%B %d, %Y at %I:%M %p")}', subtitle_format)

        # Define formats
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#2c3e50',
            'font_color': '#ffffff',
            'border': 1,
            'align': 'center',
            'valign': 'vcenter',
            'text_wrap': True
        })

        money_format = workbook.add_format({
            'num_format': '#,##0.00',
            'border': 1,
            'align': 'right',
            'valign': 'vcenter'
        })

        date_format = workbook.add_format({
            'num_format': 'yyyy-mm-dd',
            'border': 1,
            'align': 'center',
            'valign': 'vcenter'
        })

        text_format = workbook.add_format({
            'border': 1,
            'align': 'left',
            'valign': 'vcenter'
        })

        status_formats = {
            'Paid': workbook.add_format({'bg_color': '#d4edda', 'font_color': '#155724', 'border': 1, 'align': 'center'}),
            'Partial': workbook.add_format({'bg_color': '#fff3cd', 'font_color': '#856404', 'border': 1, 'align': 'center'}),
            'Unpaid': workbook.add_format({'bg_color': '#f8d7da', 'font_color': '#721c24', 'border': 1, 'align': 'center'})
        }

        # Write headers
        for col_num, column in enumerate(df.columns):
            worksheet.write(4, col_num, column, header_format)
            worksheet.set_column(col_num, col_num, 18 if column in ['Facility', 'District'] else 15)

        # Write data with conditional formatting
        for row_num, row_data in enumerate(data, start=5):
            for col_num, (key, value) in enumerate(row_data.items()):
                if key in ['Invoice Amount', 'Amount Paid', 'Balance']:
                    worksheet.write(row_num, col_num, value, money_format)
                elif key == 'Invoice Date':
                    if isinstance(value, str) and value:
                        worksheet.write(row_num, col_num, value, date_format)
                elif key == 'Payment Status':
                    status_format = status_formats.get(value, text_format)
                    worksheet.write(row_num, col_num, value, status_format)
                else:
                    worksheet.write(row_num, col_num, value, text_format)

        # Add totals row
        last_row = len(data) + 5
        total_format = workbook.add_format({'bold': True, 'bg_color': '#e9ecef', 'border': 1})
        worksheet.write(last_row, 3, 'TOTAL', total_format)
        worksheet.write(last_row, 4, f'=SUM(E6:E{last_row})', money_format)
        worksheet.write(last_row, 6, f'=SUM(G6:G{last_row})', money_format)
        worksheet.write(last_row, 7, f'=SUM(H6:H{last_row})', money_format)

        # ========== SHEET 2: FILTER PARAMETERS ==========
        filter_df = pd.DataFrame({
            'Parameter': ['Search Query', 'Start Date', 'End Date', 'Generated On', 'Total Records', 'Generated By'],
            'Value': [
                filter_params.get('query', 'None'),
                filter_params.get('start_date', 'None'),
                filter_params.get('end_date', 'None'),
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                len(data),
                request.user.get_full_name() or request.user.username
            ]
        })
        filter_df.to_excel(writer, sheet_name='Filter Parameters', index=False)

        filter_sheet = writer.sheets['Filter Parameters']
        filter_header = workbook.add_format({'bold': True, 'bg_color': '#34495e', 'font_color': '#ffffff'})
        for col_num, value in enumerate(filter_df.columns):
            filter_sheet.write(0, col_num, value, filter_header)
            filter_sheet.set_column(col_num, col_num, 25)

        # ========== SHEET 3: SUMMARY DASHBOARD ==========
        summary_data = {
            'Metric': [
                'Total Invoiced Amount',
                'Total Amount Paid',
                'Total Outstanding Balance',
                'Number of Invoices',
                'Paid Invoices',
                'Partial Payments',
                'Unpaid Invoices',
                'Collection Rate'
            ],
            'Value': [
                df['Invoice Amount'].sum(),
                df['Amount Paid'].sum(),
                df['Balance'].sum(),
                len(df),
                len(df[df['Payment Status'] == 'Paid']),
                len(df[df['Payment Status'] == 'Partial']),
                len(df[df['Payment Status'] == 'Unpaid']),
                f"{(df['Amount Paid'].sum() / df['Invoice Amount'].sum() * 100) if df['Invoice Amount'].sum() > 0 else 0:.2f}%"
            ]
        }
        summary_df = pd.DataFrame(summary_data)
        summary_df.to_excel(writer, sheet_name='Executive Summary', index=False)

        summary_sheet = writer.sheets['Executive Summary']
        summary_header = workbook.add_format({'bold': True, 'bg_color': '#27ae60', 'font_color': '#ffffff'})
        for col_num, value in enumerate(summary_df.columns):
            summary_sheet.write(0, col_num, value, summary_header)
            summary_sheet.set_column(col_num, col_num, 30)

        # Add conditional formatting for summary
        percent_format = workbook.add_format({'num_format': '0.00%'})

        # ========== SHEET 4: DISTRICT ANALYSIS ==========
        district_summary = df.groupby('District').agg({
            'Invoice Amount': 'sum',
            'Amount Paid': 'sum',
            'Balance': 'sum',
            'Invoice Number': 'count'
        }).reset_index()
        district_summary.columns = ['District', 'Total Invoiced', 'Total Paid', 'Outstanding Balance', 'Invoice Count']
        district_summary['Collection Rate'] = (district_summary['Total Paid'] / district_summary['Total Invoiced'] * 100).round(2)
        district_summary.to_excel(writer, sheet_name='District Analysis', index=False)

        # ========== SHEET 5: MONTHLY TREND ==========
        df['Month'] = pd.to_datetime(df['Invoice Date']).dt.strftime('%Y-%m')
        monthly_trend = df.groupby('Month').agg({
            'Invoice Amount': 'sum',
            'Amount Paid': 'sum',
            'Balance': 'sum'
        }).reset_index()
        monthly_trend.to_excel(writer, sheet_name='Monthly Trend', index=False)

        # Auto-filter for main sheet
        worksheet.autofilter(f'A4:I{last_row}')

        # Freeze panes
        worksheet.freeze_panes(5, 0)

    messages.success(request, f'Successfully exported {len(data)} professional invoice report(s).')
    return response

@login_required
def export_filtered_pdf(request):
    """Export filtered invoices to professional PDF format - Portrait Layout"""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, KeepTogether
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch, cm
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
    from reportlab.graphics.shapes import Drawing, Rect
    import io
    from datetime import datetime
    import os
    from django.conf import settings

    # Get filtered invoice IDs from session
    invoice_ids = request.session.get('filtered_invoice_ids', [])
    filter_params = request.session.get('filter_parameters', {})

    if not invoice_ids:
        messages.warning(request, 'No filtered invoices to export. Please apply a filter first.')
        return redirect('all_invoices')

    # Get the filtered invoices
    invoices = Invoice.objects.filter(id__in=invoice_ids).select_related('facility__district').order_by('-invoice_date')

    # Create PDF response
    response = HttpResponse(content_type='application/pdf')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"Invoice_Report_{timestamp}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    # Create PDF document with custom footer
    doc = SimpleDocTemplate(response, pagesize=A4,
                           rightMargin=0.5*inch, leftMargin=0.5*inch,
                           topMargin=0.7*inch, bottomMargin=0.8*inch)

    # Define styles
    styles = getSampleStyleSheet()

    # Title style - Financial Statement
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=20,
        alignment=TA_CENTER,
        spaceAfter=8,  # Space after Financial Statement
        spaceBefore=6,  # Space before Financial Statement (from company name)
        textColor=colors.HexColor('#2c3e50'),
        fontName='Helvetica-Bold'
    )

    # Company style - ROBBY ONE PHARMACY
    company_style = ParagraphStyle(
        'CompanyStyle',
        parent=styles['Normal'],
        fontSize=24,
        alignment=TA_CENTER,
        spaceAfter=2,  # Reduced space after company name
        spaceBefore=0,
        textColor=colors.HexColor('#2c3e50'),
        fontName='Helvetica-Bold'
    )

    # Subtitle style - Report Generated
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=10,
        alignment=TA_CENTER,
        spaceAfter=10,  # Space after report generated date
        spaceBefore=4,  # Space before report generated date (from Financial Statement)
        textColor=colors.HexColor('#7f8c8d')
    )

    # Section header style - CENTERED
    section_style = ParagraphStyle(
        'SectionHeader',
        parent=styles['Heading2'],
        fontSize=14,
        alignment=TA_CENTER,
        spaceAfter=12,
        spaceBefore=12,
        textColor=colors.HexColor('#3498db'),
        fontName='Helvetica-Bold'
    )

    # Create a list to hold story elements
    story = []

    # Create header container with icon and text properly aligned
    icon_path = os.path.join(settings.BASE_DIR, 'static', 'icon.png')

    if os.path.exists(icon_path):
        try:
            # Calculate total height of the text block
            # Company: 24pt ≈ 0.33 inches
            # Title: 20pt ≈ 0.28 inches
            # Subtitle: 10pt ≈ 0.14 inches
            # Spacing: company to title: 2pt + 6pt = 8pt ≈ 0.11 inches
            # title to subtitle: 8pt + 4pt = 12pt ≈ 0.17 inches
            # Total height ≈ 0.33 + 0.28 + 0.14 + 0.11 + 0.17 = 1.03 inches

            # Set icon height to match the text block height
            icon_height = 1.03 * inch  # Match the total text block height with spacing
            icon_width = icon_height  # Keep aspect ratio square

            icon_img = Image(icon_path, width=icon_width, height=icon_height)

            # Create a container for the text content (company name, title, date)
            text_content = []
            text_content.append(Paragraph("ROBBY ONE PHARMACY", company_style))
            text_content.append(Paragraph("Financial Statement", title_style))
            text_content.append(Paragraph(f"Report Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", subtitle_style))

            # Create a table to hold icon and text side by side
            header_data = [
                [icon_img, text_content]
            ]

            # Adjust column widths - give more space to text
            header_table = Table(header_data, colWidths=[1.0*inch, 5.0*inch])
            header_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (0, 0), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),  # Middle alignment for better balance
                ('LEFTPADDING', (0, 0), (0, 0), 0),
                ('RIGHTPADDING', (1, 0), (1, 0), 0),
                ('TOPPADDING', (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ]))
            header_table.hAlign = 'CENTER'
            story.append(header_table)

        except Exception as e:
            # If icon loading fails, just show text
            print(f"Error loading icon: {e}")
            story.append(Paragraph("ROBBY ONE PHARMACY", company_style))
            story.append(Paragraph("Financial Statement", title_style))
            story.append(Paragraph(f"Report Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", subtitle_style))
    else:
        # If icon doesn't exist, just show text with proper spacing
        story.append(Paragraph("ROBBY ONE PHARMACY", company_style))
        story.append(Paragraph("Financial Statement", title_style))
        story.append(Paragraph(f"Report Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", subtitle_style))

    story.append(Spacer(1, 0.05*inch))

    # Add a line separator
    separator_style = ParagraphStyle(
        'Separator',
        parent=styles['Normal'],
        fontSize=8,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#bdc3c7')
    )
    story.append(Paragraph("_" * 100, separator_style))
    story.append(Spacer(1, 0.2*inch))

    # Filter parameters section - CENTERED TITLE
    story.append(Paragraph("Report Parameters", section_style))

    # Create filter parameters table with consistent width
    filter_data = [
        ['Facility/Search:', filter_params.get('query', 'All Facilities')],
        ['Date Range:', f"{filter_params.get('start_date', 'All')} to {filter_params.get('end_date', 'All')}"],
        ['Generated By:', request.user.get_full_name() or request.user.username],
        ['Total Records:', str(invoices.count())],
        ['Generated On:', datetime.now().strftime('%Y-%m-%d %H:%M:%S')]
    ]

    # Set consistent table width
    filter_table = Table(filter_data, colWidths=[1.5*inch, 4*inch])
    filter_table.hAlign = 'CENTER'
    filter_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#ecf0f1')),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#2c3e50')),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#bdc3c7')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(filter_table)
    story.append(Spacer(1, 0.2*inch))

    # Executive Summary section - CENTERED TITLE
    story.append(Paragraph("Executive Summary", section_style))

    total_invoiced = sum(inv.invoice_amount for inv in invoices)
    total_paid = sum(inv.amount_paid for inv in invoices)
    total_balance = total_invoiced - total_paid

    paid_count = sum(1 for inv in invoices if inv.balance == 0)
    partial_count = sum(1 for inv in invoices if 0 < inv.amount_paid < inv.invoice_amount)
    unpaid_count = sum(1 for inv in invoices if inv.amount_paid == 0)

    collection_rate = (total_paid / total_invoiced * 100) if total_invoiced > 0 else 0

    # Create summary data in 2 columns
    summary_data = [
        ['Total Invoiced', f"TZS {total_invoiced:,.2f}"],
        ['Total Paid', f"TZS {total_paid:,.2f}"],
        ['Outstanding Balance', f"TZS {total_balance:,.2f}"],
        ['Collection Rate', f"{collection_rate:.1f}%"],
        ['Paid Invoices', f"{paid_count} ({paid_count/invoices.count()*100:.1f}%)"],
        ['Partial Payments', f"{partial_count} ({partial_count/invoices.count()*100:.1f}%)"],
        ['Unpaid Invoices', f"{unpaid_count} ({unpaid_count/invoices.count()*100:.1f}%)"],
        ['Total Invoices', str(invoices.count())]
    ]

    summary_table = Table(summary_data, colWidths=[2.2*inch, 2.2*inch])
    summary_table.hAlign = 'CENTER'

    summary_style = [
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498db')),
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#e8f4f8')),
        ('BACKGROUND', (0, 2), (-1, 2), colors.HexColor('#f8f9fa')),
        ('BACKGROUND', (0, 3), (-1, 3), colors.HexColor('#e8f4f8')),
        ('BACKGROUND', (0, 4), (-1, 4), colors.HexColor('#f8f9fa')),
        ('BACKGROUND', (0, 5), (-1, 5), colors.HexColor('#e8f4f8')),
        ('BACKGROUND', (0, 6), (-1, 6), colors.HexColor('#f8f9fa')),
        ('BACKGROUND', (0, 7), (-1, 7), colors.HexColor('#e8f4f8')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]
    summary_table.setStyle(TableStyle(summary_style))
    story.append(summary_table)
    story.append(Spacer(1, 0.3*inch))

    # Invoice details section
    story.append(Paragraph("Invoice Details", section_style))

    # Headers with Payment Date column
    table_data = [['Invoice #', 'Facility', 'District', 'Date', 'Amount', 'Paid', 'Balance', 'Pay Date', 'Status']]

    for inv in invoices:
        status = 'Paid' if inv.balance == 0 else 'Partial' if inv.amount_paid > 0 else 'Unpaid'
        payment_date = inv.payment_date.strftime('%Y-%m-%d') if inv.payment_date else '-'

        facility_name = inv.facility.name[:25] + '...' if len(inv.facility.name) > 25 else inv.facility.name
        district_name = inv.facility.district.name[:18] + '...' if len(inv.facility.district.name) > 18 else inv.facility.district.name

        table_data.append([
            inv.invoice_number,
            facility_name,
            district_name,
            inv.invoice_date.strftime('%Y-%m-%d'),
            f"{inv.invoice_amount:,.0f}",
            f"{inv.amount_paid:,.0f}",
            f"{inv.balance:,.0f}",
            payment_date,
            status
        ])

    col_widths = [0.8*inch, 1.6*inch, 1.1*inch, 0.7*inch, 0.8*inch, 0.8*inch, 0.8*inch, 0.7*inch, 0.7*inch]

    invoice_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    invoice_table.hAlign = 'CENTER'

    invoice_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('FONTSIZE', (0, 1), (-1, -1), 7),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('ALIGN', (4, 1), (6, -1), 'RIGHT'),
        ('ALIGN', (7, 1), (7, -1), 'CENTER'),
        ('ALIGN', (8, 1), (8, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#bdc3c7')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
    ]))

    # Add conditional colors for status column
    for i, row in enumerate(table_data[1:], start=1):
        status = row[8]
        if status == 'Paid':
            invoice_table.setStyle(TableStyle([
                ('BACKGROUND', (8, i), (8, i), colors.HexColor('#d4edda')),
                ('TEXTCOLOR', (8, i), (8, i), colors.HexColor('#155724')),
                ('FONTNAME', (8, i), (8, i), 'Helvetica-Bold'),
            ]))
        elif status == 'Partial':
            invoice_table.setStyle(TableStyle([
                ('BACKGROUND', (8, i), (8, i), colors.HexColor('#fff3cd')),
                ('TEXTCOLOR', (8, i), (8, i), colors.HexColor('#856404')),
            ]))
        elif status == 'Unpaid':
            invoice_table.setStyle(TableStyle([
                ('BACKGROUND', (8, i), (8, i), colors.HexColor('#f8d7da')),
                ('TEXTCOLOR', (8, i), (8, i), colors.HexColor('#721c24')),
                ('FONTNAME', (8, i), (8, i), 'Helvetica-Bold'),
            ]))

    story.append(invoice_table)

    # Add totals summary
    if invoices:
        story.append(Spacer(1, 0.15*inch))

        totals_data = [
            ['SUMMARY', 'Amount (TZS)'],
            ['Total Invoiced:', f"TZS {total_invoiced:,.2f}"],
            ['Total Paid:', f"TZS {total_paid:,.2f}"],
            ['Outstanding:', f"TZS {total_balance:,.2f}"],
        ]

        totals_table = Table(totals_data, colWidths=[1.8*inch, 1.8*inch])
        totals_table.hAlign = 'RIGHT'

        totals_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498db')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#e8f4f8')),
            ('BACKGROUND', (0, 2), (-1, 2), colors.HexColor('#f8f9fa')),
            ('BACKGROUND', (0, 3), (-1, 3), colors.HexColor('#e8f4f8')),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#bdc3c7')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ]))

        story.append(KeepTogether(totals_table))
        story.append(Spacer(1, 0.1*inch))

    # Build the PDF with custom footer
    def add_page_footer(canvas, doc):
        """Add footer to every page"""
        canvas.saveState()

        page_num = canvas.getPageNumber()

        footer_text = f"Generated by Robby One Pharmacy Invoice System • Page {page_num} • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        canvas.setFont('Helvetica', 7)
        canvas.setFillColor(colors.HexColor('#95a5a6'))

        canvas.drawCentredString(doc.width / 2 + doc.leftMargin,
                                 doc.bottomMargin - 15,
                                 footer_text)

        canvas.setStrokeColor(colors.HexColor('#e0e0e0'))
        canvas.setLineWidth(0.5)
        canvas.line(doc.leftMargin,
                   doc.bottomMargin - 8,
                   doc.width + doc.leftMargin,
                   doc.bottomMargin - 8)

        canvas.restoreState()

    doc.build(story, onFirstPage=add_page_footer, onLaterPages=add_page_footer)

    messages.success(request, f'Successfully exported {invoices.count()} professional invoice report(s).')
    return response

################################

@login_required
def clear_filters(request):
    """Clear filter session data"""
    if 'filtered_invoice_ids' in request.session:
        del request.session['filtered_invoice_ids']
    if 'filter_parameters' in request.session:
        del request.session['filter_parameters']
    messages.info(request, 'Filters cleared.')
    return redirect('all_invoices')


# ========== DASHBOARD ==========
def save_plot_to_base64():
    """Save current matplotlib plot to base64 string"""
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', dpi=100)
    buf.seek(0)
    image_base64 = base64.b64encode(buf.read()).decode('utf-8')
    plt.close()
    return image_base64

@login_required
def dashboard(request):
    """Dashboard with charts and statistics"""
    districts = District.objects.all()
    invoices = Invoice.objects.select_related('facility__district')

    total_invoiced = invoices.aggregate(Sum('invoice_amount'))['invoice_amount__sum'] or 0
    total_paid = invoices.aggregate(Sum('amount_paid'))['amount_paid__sum'] or 0
    total_outstanding = total_invoiced - total_paid
    total_invoices = invoices.count()

    district_data = []
    for district in districts:
        district_total = invoices.filter(facility__district=district).aggregate(Sum('invoice_amount'))['invoice_amount__sum'] or 0
        if district_total > 0:
            district_data.append({
                'name': district.name,
                'total': float(district_total)
            })

    plt.figure(figsize=(10, 6))
    plt.pie([d['total'] for d in district_data],
            labels=[d['name'] for d in district_data],
            autopct='%1.1f%%',
            startangle=90)
    plt.title('Invoices by District')
    pie_chart = save_plot_to_base64()

    today = datetime.now().date()
    twelve_months_ago = today - timedelta(days=365)

    monthly_data = invoices.filter(invoice_date__gte=twelve_months_ago).extra(
        {'month': "strftime('%%Y-%%m', invoice_date)"}
    ).values('month').annotate(
        total=Sum('invoice_amount'),
        paid=Sum('amount_paid')
    ).order_by('month')

    plt.figure(figsize=(12, 6))
    months = [d['month'] for d in monthly_data]
    totals = [float(d['total']) for d in monthly_data]
    paid = [float(d['paid']) for d in monthly_data]

    plt.plot(months, totals, marker='o', label='Invoiced', linewidth=2)
    plt.plot(months, paid, marker='s', label='Paid', linewidth=2)
    plt.xlabel('Month')
    plt.ylabel('Amount (TZS)')
    plt.title('Payment Trends Over Time')
    plt.legend()
    plt.xticks(rotation=45)
    plt.tight_layout()
    trend_chart = save_plot_to_base64()

    # Updated: Include facility ID in the queryset
    facility_balances = invoices.values('facility__id', 'facility__name', 'facility__district__name').annotate(
        total_invoiced=Sum('invoice_amount'),
        total_paid=Sum('amount_paid')
    ).annotate(
        balance=Sum('invoice_amount') - Sum('amount_paid')
    ).filter(balance__gt=0).order_by('-balance')[:10]

    # Create a list of facility objects with proper structure for the template
    facilities_list = []
    for facility in facility_balances:
        facilities_list.append({
            'id': facility['facility__id'],
            'name': facility['facility__name'],
            'district': {'name': facility['facility__district__name']},
            'total_invoiced': float(facility['total_invoiced']),
            'total_paid': float(facility['total_paid']),
            'balance': float(facility['balance'])
        })

    if facility_balances:
        plt.figure(figsize=(10, 6))
        facilities = [f"{f['facility__name']} ({f['facility__district__name']})" for f in facility_balances]
        balances = [float(f['balance']) for f in facility_balances]

        plt.barh(facilities, balances, color='coral')
        plt.xlabel('Outstanding Balance (TZS)')
        plt.title('Top 10 Facilities by Outstanding Balance')
        plt.tight_layout()
        balance_chart = save_plot_to_base64()
    else:
        balance_chart = None

    context = {
        'total_invoiced': total_invoiced,
        'total_paid': total_paid,
        'total_outstanding': total_outstanding,
        'total_invoices': total_invoices,
        'pie_chart': pie_chart,
        'trend_chart': trend_chart,
        'balance_chart': balance_chart,
        'facility_balances': facilities_list,  # Now includes facility IDs
    }

    return render(request, 'invoices/dashboard.html', context)


# ========== CORE VIEWS ==========
@login_required
def home(request):
    """Main dashboard view with all KPIs, charts, notifications, and activity logs"""

    # ========== 1. BASIC DATA FETCHING ==========
    # Get all districts with their totals
    districts = District.objects.annotate(
        total_invoices=Coalesce(Sum('facilities__invoices__invoice_amount'), Value(0, output_field=DecimalField())),
        total_paid=Coalesce(Sum('facilities__invoices__amount_paid'), Value(0, output_field=DecimalField())),
    ).annotate(
        balance=ExpressionWrapper(
            F('total_invoices') - F('total_paid'),
            output_field=DecimalField()
        )
    )

    # Overall totals
    total_invoiced = sum(d.total_invoices for d in districts)
    total_paid = sum(d.total_paid for d in districts)
    total_outstanding = total_invoiced - total_paid
    total_invoices = Invoice.objects.count()

    # ========== 2. CHART DATA ==========
    # Data for district pie chart (with IDs for navigation)
    district_data = [
        {'id': d.id, 'name': d.name, 'total': float(d.total_invoices)}
        for d in districts if d.total_invoices > 0
    ]
    district_ids = [d['id'] for d in district_data]

    # Monthly trend data (last 12 months)
    today = timezone.now().date()
    twelve_months_ago = today - timedelta(days=365)

    monthly_data = Invoice.objects.filter(invoice_date__gte=twelve_months_ago) \
        .extra({'month': "strftime('%%Y-%%m', invoice_date)"}) \
        .values('month') \
        .annotate(total=Sum('invoice_amount'), paid=Sum('amount_paid')) \
        .order_by('month')

    months = [d['month'] for d in monthly_data]
    monthly_totals = [float(d['total']) for d in monthly_data]
    monthly_paid = [float(d['paid']) for d in monthly_data]

    # Top 10 facilities by outstanding balance (with IDs for navigation)
    facility_balances = Invoice.objects.values('facility__id', 'facility__name', 'facility__district__name') \
        .annotate(total_invoiced=Sum('invoice_amount'), total_paid=Sum('amount_paid')) \
        .annotate(balance=Sum('invoice_amount') - Sum('amount_paid')) \
        .filter(balance__gt=0).order_by('-balance')[:10]

    facility_ids = [f['facility__id'] for f in facility_balances]
    facility_names = [f"{f['facility__name']} ({f['facility__district__name']})" for f in facility_balances]
    facility_balances_values = [float(f['balance']) for f in facility_balances]

    # Recent invoices (last 10)
    recent_invoices = Invoice.objects.select_related('facility__district').order_by('-invoice_date')[:10]

    # ========== 3. MONTHLY COMPARISON DATA ==========
    # Calculate first and last days of current and previous months
    first_of_this_month = today.replace(day=1)
    first_of_last_month = (first_of_this_month - timedelta(days=1)).replace(day=1)
    end_of_last_month = first_of_this_month - timedelta(days=1)

    def sum_invoices(start, end):
        """Helper function to sum invoice amounts within date range"""
        qs = Invoice.objects.filter(invoice_date__gte=start, invoice_date__lte=end)
        return qs.aggregate(total=Sum('invoice_amount'))['total'] or 0

    # Current month totals
    this_month_total = sum_invoices(first_of_this_month, today)
    last_month_total = sum_invoices(first_of_last_month, end_of_last_month)
    revenue_change = ((this_month_total - last_month_total) / last_month_total * 100) if last_month_total else 0

    # Paid amounts comparison
    paid_this_month = Invoice.objects.filter(
        invoice_date__gte=first_of_this_month,
        invoice_date__lte=today
    ).aggregate(Sum('amount_paid'))['amount_paid__sum'] or 0

    paid_last_month = Invoice.objects.filter(
        invoice_date__gte=first_of_last_month,
        invoice_date__lte=end_of_last_month
    ).aggregate(Sum('amount_paid'))['amount_paid__sum'] or 0
    paid_change = ((paid_this_month - paid_last_month) / paid_last_month * 100) if paid_last_month else 0

    # Outstanding amounts comparison
    outstanding_this_month = this_month_total - paid_this_month
    outstanding_last_month = last_month_total - paid_last_month
    outstanding_change = ((outstanding_this_month - outstanding_last_month) / outstanding_last_month * 100) if outstanding_last_month else 0

    # Invoice count comparison
    total_invoices_this_month = Invoice.objects.filter(
        invoice_date__gte=first_of_this_month,
        invoice_date__lte=today
    ).count()

    total_invoices_last_month = Invoice.objects.filter(
        invoice_date__gte=first_of_last_month,
        invoice_date__lte=end_of_last_month
    ).count()
    invoice_change = ((total_invoices_this_month - total_invoices_last_month) / total_invoices_last_month * 100) if total_invoices_last_month else 0

    # ========== 4. KEY PERFORMANCE INDICATORS (KPIs) ==========

    # Average days to payment (for invoices that have been paid)
    paid_invoices = Invoice.objects.filter(amount_paid__gt=0, payment_date__isnull=False)
    avg_days_to_pay = 0
    if paid_invoices.exists():
        total_days = sum((inv.payment_date - inv.invoice_date).days for inv in paid_invoices)
        avg_days_to_pay = total_days / paid_invoices.count()

    # Top performing district (by total invoiced)
    district_totals = {}
    for d in District.objects.all():
        total = Invoice.objects.filter(facility__district=d).aggregate(Sum('invoice_amount'))['invoice_amount__sum'] or 0
        district_totals[d.name] = total

    top_district_name = max(district_totals, key=district_totals.get) if district_totals else None
    top_district = {
        'name': top_district_name,
        'total': district_totals.get(top_district_name, 0)
    }

    # Collection efficiency (percentage of total paid)
    total_invoiced_all = sum(d.total_invoices for d in districts)
    total_paid_all = sum(d.total_paid for d in districts)
    collection_efficiency = (total_paid_all / total_invoiced_all * 100) if total_invoiced_all else 0

    # Cash flow projection (based on last month's collection)
    cash_flow_projection = paid_last_month

    # ========== 5. PAYMENT STATUS COUNTS ==========
    status_counts = {
        'Paid': Invoice.objects.filter(invoice_amount=F('amount_paid')).count(),
        'Partial': Invoice.objects.filter(amount_paid__gt=0).exclude(invoice_amount=F('amount_paid')).count(),
        'Unpaid': Invoice.objects.filter(amount_paid=0).count()
    }

    # ========== 6. MAP DATA (Placeholder - Replace with actual geographic mapping) ==========
    map_data = {}
    for d in districts:
        # Note: This is a placeholder. You'll need to map district names to actual country/region codes
        # For Tanzania, you might need a custom map or use district names as labels
        code = d.name[:2].upper()  # Placeholder - replace with actual region codes
        map_data[code] = {
            'name': d.name,
            'value': float(d.total_invoices)
        }

    # ========== 7. NOTIFICATIONS ==========
    # Get recent notifications for the current user
    recent_notifications = Notification.objects.filter(user=request.user).order_by('-created_at')[:5]
    unread_notifications_count = Notification.objects.filter(user=request.user, is_read=False).count()

    # ========== 8. ACTIVITY LOGS ==========
    # Get recent user activities
    recent_activities = ActivityLog.objects.filter(user=request.user).order_by('-created_at')[:5]

    # ========== 9. BUILD CONTEXT DICTIONARY ==========
    context = {
        # Basic data
        'districts': districts,
        'total_invoiced': total_invoiced,
        'total_paid': total_paid,
        'total_outstanding': total_outstanding,
        'total_invoices': total_invoices,

        # Chart data
        'district_data': json.dumps(district_data),
        'district_ids': json.dumps(district_ids),
        'months': json.dumps(months),
        'monthly_totals': json.dumps(monthly_totals),
        'monthly_paid': json.dumps(monthly_paid),
        'facility_ids': json.dumps(facility_ids),
        'facility_names': json.dumps(facility_names),
        'facility_balances': json.dumps(facility_balances_values),
        'invoices': recent_invoices,

        # Monthly comparisons
        'total_invoices_this_month': total_invoices_this_month,
        'invoice_change': invoice_change,
        'revenue_this_month': this_month_total,
        'revenue_change': revenue_change,
        'paid_this_month': paid_this_month,
        'paid_change': paid_change,
        'outstanding_this_month': outstanding_this_month,
        'outstanding_change': outstanding_change,

        # KPIs
        'avg_days_to_pay': avg_days_to_pay,
        'top_district': top_district,
        'collection_efficiency': collection_efficiency,
        'cash_flow_projection': cash_flow_projection,

        # Additional chart data
        'status_counts': json.dumps(status_counts),
        'map_data': json.dumps(map_data),

        # Notifications & Activity
        'recent_notifications': recent_notifications,
        'unread_notifications_count': unread_notifications_count,
        'recent_activities': recent_activities,
    }

    return render(request, 'invoices/home.html', context)

@login_required
def district_detail(request, district_id):
    district = get_object_or_404(District, pk=district_id)
    facilities = district.facilities.annotate(
        total_invoices=Coalesce(Sum('invoices__invoice_amount'), Value(0, output_field=DecimalField())),
        total_paid=Coalesce(Sum('invoices__amount_paid'), Value(0, output_field=DecimalField())),
    ).annotate(
        balance=ExpressionWrapper(
            F('total_invoices') - F('total_paid'),
            output_field=DecimalField(max_digits=12, decimal_places=2)
        )
    )

    # Calculate district totals
    total_invoiced = sum(f.total_invoices for f in facilities)
    total_paid = sum(f.total_paid for f in facilities)
    total_balance = total_invoiced - total_paid

    return render(request, 'invoices/district_detail.html', {
        'district': district,
        'facilities': facilities,
        'total_invoiced': total_invoiced,
        'total_paid': total_paid,
        'total_balance': total_balance
    })

@login_required
def facility_detail(request, facility_id):
    facility = get_object_or_404(Facility, pk=facility_id)
    invoices = facility.invoices.all().order_by('-invoice_date')
    total_invoice = sum(i.invoice_amount for i in invoices)
    total_paid = sum(i.amount_paid for i in invoices)
    total_balance = total_invoice - total_paid
    return render(request, 'invoices/facility_detail.html', {
        'facility': facility,
        'invoices': invoices,
        'total_invoice': total_invoice,
        'total_paid': total_paid,
        'total_balance': total_balance
    })

@login_required
def all_invoices(request):
    """List all invoices with search and date filters"""
    invoices = Invoice.objects.select_related('facility__district').all().order_by('-invoice_date')

    # Get filter parameters from request.GET
    search_query = request.GET.get('query', '')
    facility_id = request.GET.get('facility', '')
    district_id = request.GET.get('district', '')
    status_filter = request.GET.get('status', '')
    min_amount = request.GET.get('min_amount', '')
    max_amount = request.GET.get('max_amount', '')
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')

    # Apply search filter
    if search_query:
        invoices = invoices.filter(
            Q(invoice_number__icontains=search_query) |
            Q(facility__name__icontains=search_query) |
            Q(facility__district__name__icontains=search_query)
        )

    # Apply facility filter
    if facility_id:
        invoices = invoices.filter(facility_id=facility_id)

    # Apply district filter
    if district_id:
        invoices = invoices.filter(facility__district_id=district_id)

    # Apply payment status filter - Use database fields instead of balance property
    if status_filter:
        if status_filter == 'paid':
            # Paid means balance = 0, which means invoice_amount = amount_paid
            invoices = invoices.filter(invoice_amount=F('amount_paid'))
        elif status_filter == 'partial':
            # Partial means amount_paid > 0 AND amount_paid < invoice_amount
            invoices = invoices.filter(amount_paid__gt=0).filter(amount_paid__lt=F('invoice_amount'))
        elif status_filter == 'unpaid':
            # Unpaid means amount_paid = 0
            invoices = invoices.filter(amount_paid=0)

    # Apply amount range filter
    if min_amount:
        try:
            min_val = float(min_amount)
            invoices = invoices.filter(invoice_amount__gte=min_val)
        except ValueError:
            pass

    if max_amount:
        try:
            max_val = float(max_amount)
            invoices = invoices.filter(invoice_amount__lte=max_val)
        except ValueError:
            pass

    # Apply date range filter (only if dates are provided)
    if start_date:
        invoices = invoices.filter(invoice_date__gte=start_date)
    if end_date:
        invoices = invoices.filter(invoice_date__lte=end_date)

    # Calculate totals
    total_invoiced = invoices.aggregate(total=Sum('invoice_amount'))['total'] or 0
    total_paid = invoices.aggregate(total=Sum('amount_paid'))['total'] or 0
    total_balance = total_invoiced - total_paid

    # Store the filtered queryset IDs in session for export
    invoice_ids = list(invoices.values_list('id', flat=True))
    request.session['filtered_invoice_ids'] = invoice_ids

    # Prepare filter parameters for display
    filter_params = {
        'query': search_query,
        'facility': facility_id,
        'district': district_id,
        'status': status_filter,
        'min_amount': min_amount,
        'max_amount': max_amount,
        'start_date': start_date,
        'end_date': end_date,
        'total_count': len(invoice_ids)
    }
    request.session['filter_parameters'] = filter_params

    # Check if any filters are applied
    has_filters = bool(search_query or facility_id or district_id or status_filter or
                      min_amount or max_amount or start_date or end_date)

    # Get facilities and districts for dropdowns
    facilities = Facility.objects.all().order_by('name')
    districts = District.objects.all().order_by('name')

    return render(request, 'invoices/all_invoices.html', {
        'invoices': invoices,
        'total_invoiced': total_invoiced,
        'total_paid': total_paid,
        'total_balance': total_balance,
        'has_filters': has_filters,
        'filter_count': len(invoice_ids),
        'search_query': search_query,
        'facilities': facilities,
        'districts': districts,
    })


@login_required
def update_payment(request, invoice_id):
    """Update payment for an invoice"""
    invoice = get_object_or_404(Invoice, pk=invoice_id)

    if request.method == 'POST':
        form = PaymentUpdateForm(request.POST, instance=invoice)
        if form.is_valid():
            old_amount = invoice.amount_paid
            form.save()

            # Create activity log
            ActivityLog.objects.create(
                user=request.user,
                action='UPDATE_PAYMENT',
                message=f'Updated payment for invoice {invoice.invoice_number} from {old_amount:,.2f} to {invoice.amount_paid:,.2f}'
            )

            # Create notification
            if invoice.balance == 0:
                notification_message = f'Invoice #{invoice.invoice_number} is now fully paid!'
                notification_type = 'success'
            else:
                notification_message = f'Payment updated for invoice #{invoice.invoice_number} - New balance: {invoice.balance:,.2f}'
                notification_type = 'info'

            create_notification(
                user=request.user,
                title='Payment Updated',
                message=notification_message,
                notification_type=notification_type,
                link=f'/facility/{invoice.facility.id}/'
            )

            # Check if payment is overdue (30+ days old and unpaid)
            if invoice.balance > 0 and (timezone.now().date() - invoice.invoice_date).days > 30:
                create_notification(
                    user=request.user,
                    title='Payment Overdue',
                    message=f'Invoice #{invoice.invoice_number} is overdue by {(timezone.now().date() - invoice.invoice_date).days} days. Balance: {invoice.balance:,.2f}',
                    notification_type='warning',
                    link=f'/update-payment/{invoice.id}/'
                )

            messages.success(request, f'Payment updated for invoice {invoice.invoice_number}')
            return redirect('facility_detail', facility_id=invoice.facility.id)
    else:
        form = PaymentUpdateForm(instance=invoice)

    return render(request, 'invoices/update_payment.html', {
        'invoice': invoice,
        'form': form
    })


def custom_login(request):
    """Custom login view"""
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        if user is not None:
            auth_login(request, user)

            # Create activity log for login
            ActivityLog.objects.create(
                user=user,
                action='LOGIN',
                message=f'User logged into the system'
            )

            next_url = request.GET.get('next', '/')
            return redirect(next_url)
        else:
            return render(request, 'invoices/login.html', {
                'error': 'Invalid username or password'
            })
    return render(request, 'invoices/login.html')


from django.contrib.auth import logout as auth_logout

def custom_logout(request):
    """Custom logout view with activity logging"""
    if request.method == 'POST':
        user = request.user
        ActivityLog.objects.create(
            user=user,
            action='LOGOUT',
            message=f'User logged out of the system'
        )
        auth_logout(request)
        messages.success(request, 'You have been logged out successfully.')
        return redirect('login')
    return redirect('home')


def create_notification(user, title, message, notification_type='info', link=None):
    """Create a notification for a user"""
    Notification.objects.create(
        user=user,
        title=title,
        message=message,
        notification_type=notification_type,
        link=link
    )

def create_notification_for_all_users(title, message, notification_type='info', link=None):
    """Create a notification for all users"""
    for user in User.objects.all():
        create_notification(user, title, message, notification_type, link)

# notifications ===========================================================================================
@login_required
def notifications(request):
    """View unread notifications"""
    notifications = Notification.objects.filter(
        user=request.user, is_read=False
    ).order_by('-created_at')

    return render(request, 'invoices/notifications.html', {'notifications': notifications})

@login_required
def notification_detail(request, pk):
    """Open a single notification"""
    notification = get_object_or_404(Notification, pk=pk, user=request.user)

    # Mark as read when opened
    notification.is_read = True
    notification.save()

    # If you want it to disappear completely:
    # notification.delete()

    return render(request, 'invoices/notification_detail.html', {'notification': notification})

@login_required
def delete_notification(request, pk):
    """Delete a single notification instantly"""
    if request.method == 'POST':
        try:
            notification = get_object_or_404(Notification, pk=pk, user=request.user)
            notification.delete()
            return JsonResponse({'success': True, 'message': 'Notification deleted'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
    return JsonResponse({'success': False, 'error': 'Invalid request'}, status=400)

@login_required
def delete_old_notifications(request):
    """Delete notifications older than 30 days when user opens the bell"""
    if request.method == 'POST':
        # Delete notifications older than 3 days
        cutoff_date = timezone.now() - timedelta(days=3)
        deleted_count = Notification.objects.filter(
            user=request.user,
            created_at__lt=cutoff_date
        ).delete()[0]

        return JsonResponse({
            'success': True,
            'deleted_count': deleted_count,
            'message': f'Deleted {deleted_count} old notifications'
        })
    return JsonResponse({'success': False, 'error': 'Invalid request'}, status=400)

@login_required
def mark_all_as_read(request):
    """Mark all notifications as read when opening dropdown"""
    if request.method == 'POST':
        updated_count = Notification.objects.filter(
            user=request.user,
            is_read=False
        ).update(is_read=True)

        return JsonResponse({
            'success': True,
            'updated_count': updated_count
        })
    return JsonResponse({'success': False}, status=400)

# =======================================================================================================

@login_required
def mark_notification_read(request, notification_id):
    """Mark a single notification as read"""
    notification = get_object_or_404(Notification, id=notification_id, user=request.user)
    notification.is_read = True
    notification.save()
    return redirect(notification.link or 'home')
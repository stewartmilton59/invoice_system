from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Sum, Q, F, Value, DecimalField, ExpressionWrapper, Count
from django.db.models.functions import Coalesce, TruncMonth
from django.http import HttpResponse
from django.utils import timezone
from datetime import datetime, timedelta
import json
import pandas as pd

# ReportLab Imports
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

from .models import ReferralSource, ReferralInvoice
from .forms import ReferralSourceForm, ReferralInvoiceForm, ReferralPaymentUpdateForm
from invoices.models import ActivityLog
from invoices.views import create_notification


# ========== DASHBOARD VIEW ==========

@login_required
def referral_dashboard(request):
    # 1. Base KPI Totals
    totals = ReferralInvoice.objects.aggregate(
        p=Sum('purchase_amount'),
        a=Sum('amount_paid')
    )
    total_purchased = totals['p'] or 0
    total_paid = totals['a'] or 0
    total_outstanding = total_purchased - total_paid
    total_invoices = ReferralInvoice.objects.count()

    # Calculate Collection Rate for the Insight Alert
    collection_rate = (total_paid / total_purchased * 100) if total_purchased > 0 else 0

    # 2. Table Data: Top Referral Sources (Ranked by volume)
    sources_summary = ReferralSource.objects.annotate(
        total_purchased=Coalesce(Sum('invoices__purchase_amount'), Value(0, output_field=DecimalField())),
        total_paid=Coalesce(Sum('invoices__amount_paid'), Value(0, output_field=DecimalField())),
    ).annotate(
        balance=ExpressionWrapper(F('total_purchased') - F('total_paid'), output_field=DecimalField())
    ).order_by('-total_purchased')[:5]

    # 3. Donut Chart Data: Payment Status Distribution
    status_counts = {
        'Paid': ReferralInvoice.objects.filter(purchase_amount=F('amount_paid')).count(),
        'Partial': ReferralInvoice.objects.filter(amount_paid__gt=0, amount_paid__lt=F('purchase_amount')).count(),
        'Unpaid': ReferralInvoice.objects.filter(amount_paid=0).count(),
    }

    # 4. Trend Chart Data: Last 12 Months
    last_12_months = timezone.now() - timedelta(days=365)
    trend_data = ReferralInvoice.objects.filter(invoice_date__gte=last_12_months) \
        .annotate(month=TruncMonth('invoice_date')) \
        .values('month') \
        .annotate(p_total=Sum('purchase_amount'), a_total=Sum('amount_paid')) \
        .order_by('month')

    months = [d['month'].strftime("%b %Y") for d in trend_data]
    purchased_totals = [float(d['p_total']) for d in trend_data]
    paid_totals = [float(d['a_total']) for d in trend_data]

    context = {
        'total_purchased': total_purchased,
        'total_paid': total_paid,
        'total_outstanding': total_outstanding,
        'total_invoices': total_invoices,
        'collection_rate': collection_rate,
        'sources_summary': sources_summary,
        'status_counts': status_counts,
        'months': months,
        'purchased_totals': purchased_totals,
        'paid_totals': paid_totals,
    }
    return render(request, 'referrals/dashboard.html', context)


# ========== CRUD FOR REFERRAL SOURCES ==========

@login_required
@staff_member_required
def referral_source_list(request):
    sources = ReferralSource.objects.all().order_by('name').annotate(
        invoice_count=Count('invoices'),
        total_purchased=Coalesce(Sum('invoices__purchase_amount'), Value(0, output_field=DecimalField())),
        total_paid=Coalesce(Sum('invoices__amount_paid'), Value(0, output_field=DecimalField())),
        outstanding=ExpressionWrapper(
            Coalesce(Sum('invoices__purchase_amount'), Value(0)) - Coalesce(Sum('invoices__amount_paid'), Value(0)),
            output_field=DecimalField()
        )
    )
    return render(request, 'referrals/source_list.html', {'sources': sources})


@login_required
@staff_member_required
def referral_source_add(request):
    if request.method == 'POST':
        form = ReferralSourceForm(request.POST)
        if form.is_valid():
            source = form.save()
            ActivityLog.objects.create(
                user=request.user,
                action='ADD_REFERRAL_SOURCE',
                message=f'Added referral hospital: {source.name}'
            )
            messages.success(request, 'Referral hospital added successfully.')
            return redirect('referral:source_list')
    else:
        form = ReferralSourceForm()
    return render(request, 'referrals/source_form.html', {'form': form, 'title': 'Add Hospital'})


@login_required
@staff_member_required
def referral_source_edit(request, pk):
    source = get_object_or_404(ReferralSource, pk=pk)
    if request.method == 'POST':
        form = ReferralSourceForm(request.POST, instance=source)
        if form.is_valid():
            form.save()
            ActivityLog.objects.create(
                user=request.user,
                action='EDIT_REFERRAL_SOURCE',
                message=f'Edited referral hospital: {source.name}'
            )
            messages.success(request, 'Referral hospital updated successfully.')
            return redirect('referral:source_list')
    else:
        form = ReferralSourceForm(instance=source)
    return render(request, 'referrals/source_form.html', {'form': form, 'title': 'Edit Hospital', 'source': source})


@login_required
@staff_member_required
def referral_source_delete(request, pk):
    source = get_object_or_404(ReferralSource, pk=pk)
    if request.method == 'POST':
        name = source.name
        source.delete()
        ActivityLog.objects.create(
            user=request.user,
            action='DELETE_REFERRAL_SOURCE',
            message=f'Deleted referral hospital: {name}'
        )
        messages.success(request, f'Referral hospital "{name}" deleted successfully.')
        return redirect('referral:source_list')
    return render(request, 'invoices/confirm_delete.html', {
        'object': source,
        'object_type': 'Referral Hospital',
        'cancel_url': 'referral:source_list'
    })


# ========== CRUD FOR REFERRAL INVOICES ==========

@login_required
@staff_member_required
def referral_invoice_list(request):
    invoices = ReferralInvoice.objects.select_related('referral_source').all().order_by('-invoice_date')

    search_query = request.GET.get('query', '')
    source_id = request.GET.get('source', '')
    status_filter = request.GET.get('status', '')
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')

    if search_query:
        invoices = invoices.filter(
            Q(invoice_number__icontains=search_query) |
            Q(referral_source__name__icontains=search_query)
        )
    if source_id:
        invoices = invoices.filter(referral_source_id=source_id)
    if status_filter:
        if status_filter == 'paid':
            invoices = invoices.filter(purchase_amount=F('amount_paid'))
        elif status_filter == 'partial':
            invoices = invoices.filter(amount_paid__gt=0, amount_paid__lt=F('purchase_amount'))
        elif status_filter == 'unpaid':
            invoices = invoices.filter(amount_paid=0)
    if start_date:
        invoices = invoices.filter(invoice_date__gte=start_date)
    if end_date:
        invoices = invoices.filter(invoice_date__lte=end_date)

    totals = invoices.aggregate(p=Sum('purchase_amount'), a=Sum('amount_paid'))
    total_purchased = totals['p'] or 0
    total_paid = totals['a'] or 0
    total_balance = total_purchased - total_paid

    request.session['filtered_referral_invoice_ids'] = list(invoices.values_list('id', flat=True))

    # Store filter params for export use
    request.session['referral_filter_parameters'] = {
        'query': search_query,
        'start_date': start_date,
        'end_date': end_date,
    }

    sources = ReferralSource.objects.all().order_by('name')
    return render(request, 'referrals/invoice_list.html', {
        'invoices': invoices,
        'total_purchased': total_purchased,
        'total_paid': total_paid,
        'total_balance': total_balance,
        'sources': sources,
        'search_query': search_query,
        'status_filter': status_filter,
    })


@login_required
@staff_member_required
def referral_invoice_add(request):
    if request.method == 'POST':
        form = ReferralInvoiceForm(request.POST)
        if form.is_valid():
            invoice = form.save()
            ActivityLog.objects.create(
                user=request.user,
                action='ADD_REFERRAL_INVOICE',
                message=f'Added invoice #{invoice.invoice_number}'
            )
            messages.success(request, 'Referral invoice added successfully.')
            return redirect('referral:invoice_list')
    else:
        form = ReferralInvoiceForm()
    return render(request, 'referrals/invoice_form.html', {'form': form, 'title': 'Add Referral Invoice'})


@login_required
@staff_member_required
def referral_invoice_edit(request, pk):
    invoice = get_object_or_404(ReferralInvoice, pk=pk)
    if request.method == 'POST':
        form = ReferralInvoiceForm(request.POST, instance=invoice)
        if form.is_valid():
            form.save()
            messages.success(request, 'Referral invoice updated.')
            return redirect('referral:invoice_list')
    else:
        form = ReferralInvoiceForm(instance=invoice)
    return render(request, 'referrals/invoice_form.html', {'form': form, 'invoice': invoice, 'title': 'Edit Invoice'})


@login_required
@staff_member_required
def referral_invoice_delete(request, pk):
    invoice = get_object_or_404(ReferralInvoice, pk=pk)
    if request.method == 'POST':
        invoice.delete()
        messages.success(request, 'Invoice deleted.')
        return redirect('referral:invoice_list')
    return render(request, 'invoices/confirm_delete.html', {'object': invoice, 'cancel_url': 'referral:invoice_list'})


@login_required
def referral_invoice_detail(request, pk):
    invoice = get_object_or_404(ReferralInvoice, pk=pk)
    return render(request, 'referrals/invoice_detail.html', {'invoice': invoice})


@login_required
def referral_invoice_update_payment(request, pk):
    invoice = get_object_or_404(ReferralInvoice, pk=pk)
    if request.method == 'POST':
        form = ReferralPaymentUpdateForm(request.POST, instance=invoice)
        if form.is_valid():
            form.save()
            messages.success(request, f'Payment updated for {invoice.invoice_number}')
            return redirect('referral:invoice_detail', pk=invoice.id)
    else:
        form = ReferralPaymentUpdateForm(instance=invoice)
    return render(request, 'referrals/update_payment.html', {'invoice': invoice, 'form': form})


# ========== REFERRAL EXPORT FUNCTIONS ==========

@login_required
def generate_referral_invoice_pdf(request, pk):
    """Generate single referral invoice PDF"""
    invoice = get_object_or_404(ReferralInvoice, pk=pk)

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Invoice_{invoice.invoice_number}.pdf"'

    doc = SimpleDocTemplate(
        response,
        pagesize=A4,
        rightMargin=50,
        leftMargin=50,
        topMargin=50,
        bottomMargin=50
    )
    story = []
    styles = getSampleStyleSheet()

    # Company Header Styles
    title_style = ParagraphStyle(
        'CompanyTitle',
        parent=styles['Heading1'],
        fontSize=22,
        textColor=colors.HexColor('#2c3e50'),
        alignment=TA_CENTER,
        spaceAfter=5
    )

    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontSize=12,
        textColor=colors.HexColor('#7f8c8d'),
        alignment=TA_CENTER,
        spaceAfter=30
    )

    invoice_title = ParagraphStyle(
        'InvoiceTitle',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=colors.HexColor('#1b4332'),
        alignment=TA_CENTER,
        spaceBefore=20,
        spaceAfter=20
    )

    # Company Letterhead
    story.append(Paragraph("ROBBY ONE PHARMACY", title_style))
    story.append(Paragraph("Referral Services Invoice", subtitle_style))
    story.append(Spacer(1, 10))

    # Horizontal line
    line_data = [['']]
    line_table = Table(line_data, colWidths=[doc.width])
    line_table.setStyle(TableStyle([
        ('LINEBELOW', (0, 0), (-1, 0), 2, colors.HexColor('#1b4332')),
    ]))
    story.append(line_table)
    story.append(Spacer(1, 20))

    # Invoice Details
    status = 'Paid' if invoice.balance == 0 else 'Partial' if invoice.amount_paid > 0 else 'Unpaid'
    status_color = '#27ae60' if status == 'Paid' else '#f39c12' if status == 'Partial' else '#e74c3c'

    invoice_info = [
        ['Invoice Number:', invoice.invoice_number, 'Status:', Paragraph(f"<font color='{status_color}'>{status}</font>", styles['Normal'])],
        ['Invoice Date:', invoice.invoice_date.strftime('%B %d, %Y'), '', ''],
        ['Facility:', invoice.referral_source.name, '', ''],
        ['District:', getattr(invoice.referral_source, 'district', 'N/A'), '', ''],
    ]

    info_table = Table(invoice_info, colWidths=[1.5 * inch, 2.5 * inch, 1 * inch, 1.5 * inch])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#555555')),
        ('TEXTCOLOR', (2, 0), (2, 0), colors.HexColor('#555555')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 30))

    # Invoice Amount Table
    amount_data = [
        [Paragraph('<b>Description</b>', styles['Normal']), Paragraph('<b>Amount (TZS)</b>', styles['Normal'])],
        ['Invoice Amount', f"{invoice.purchase_amount:,.2f}"],
        ['Amount Paid', f"{invoice.amount_paid:,.2f}"],
        [Paragraph('<b>Outstanding Balance</b>', styles['Normal']), Paragraph(f"<b>{invoice.balance:,.2f}</b>", styles['Normal'])],
    ]

    amount_table = Table(amount_data, colWidths=[3 * inch, 2.5 * inch])
    amount_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1b4332')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f8f9fa')),
        ('PADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(amount_table)
    story.append(Spacer(1, 40))

    # Footer
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.grey,
        alignment=TA_CENTER
    )
    story.append(Paragraph("Thank you for your business!", footer_style))
    story.append(Paragraph(f"Generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", footer_style))

    doc.build(story)
    return response


@login_required
def export_referral_invoices_excel(request):
    """Export referral invoices to professional Excel format matching main invoices"""
    invoice_ids = request.session.get('filtered_referral_invoice_ids', [])
    filter_params = request.session.get('referral_filter_parameters', {})

    if invoice_ids:
        invoices = ReferralInvoice.objects.filter(id__in=invoice_ids).select_related('referral_source')
        export_type = "Filtered"
    else:
        invoices = ReferralInvoice.objects.all().select_related('referral_source')
        export_type = "Full"

    if not invoices.exists():
        messages.warning(request, "No data available to export.")
        return redirect('referral:dashboard')

    # Prepare data for export
    data = []
    for inv in invoices:
        district = getattr(inv.referral_source, 'district', 'N/A')
        if hasattr(district, 'name'):
            district = district.name

        data.append({
            'Invoice Number': inv.invoice_number,
            'Facility': inv.referral_source.name,
            'District': district,
            'Invoice Date': inv.invoice_date.strftime('%Y-%m-%d'),
            'Invoice Amount': float(inv.purchase_amount),
            'Payment Date': inv.payment_date.strftime('%Y-%m-%d') if inv.payment_date else 'Not Paid',
            'Amount Paid': float(inv.amount_paid),
            'Balance': float(inv.balance),
            'Payment Status': 'Paid' if inv.balance == 0 else 'Partial' if inv.amount_paid > 0 else 'Unpaid'
        })

    df = pd.DataFrame(data)

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"Referral_Invoice_Report_{timestamp}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    with pd.ExcelWriter(response, engine='xlsxwriter') as writer:
        # ========== SHEET 1: INVOICE REPORT ==========
        df.to_excel(writer, sheet_name='Invoice Report', index=False, startrow=4)

        workbook = writer.book
        worksheet = writer.sheets['Invoice Report']

        # Add company header
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

        worksheet.merge_range('A1:I1', 'ROBBY ONE PHARMACY', title_format)
        worksheet.merge_range('A2:I2', 'Referral Services - Financial Statement', subtitle_format)
        worksheet.merge_range('A3:I3', f'Report Generated: {datetime.now().strftime("%B %d, %Y at %I:%M %p")} | Type: {export_type}', subtitle_format)

        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#1b4332',
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
            'Paid': workbook.add_format({
                'bg_color': '#d4edda',
                'font_color': '#155724',
                'border': 1,
                'align': 'center',
                'bold': True
            }),
            'Partial': workbook.add_format({
                'bg_color': '#fff3cd',
                'font_color': '#856404',
                'border': 1,
                'align': 'center',
                'bold': True
            }),
            'Unpaid': workbook.add_format({
                'bg_color': '#f8d7da',
                'font_color': '#721c24',
                'border': 1,
                'align': 'center',
                'bold': True
            })
        }

        for col_num, column in enumerate(df.columns):
            worksheet.write(4, col_num, column, header_format)
            worksheet.set_column(col_num, col_num, 18 if column in ['Facility', 'District'] else 15)

        for row_num, row_data in enumerate(data, start=5):
            for col_num, (key, value) in enumerate(row_data.items()):
                if key in ['Invoice Amount', 'Amount Paid', 'Balance']:
                    worksheet.write(row_num, col_num, value, money_format)
                elif key in ['Invoice Date', 'Payment Date']:
                    if isinstance(value, str) and value not in ['Not Paid', '']:
                        worksheet.write(row_num, col_num, value, date_format)
                    else:
                        worksheet.write(row_num, col_num, value, text_format)
                elif key == 'Payment Status':
                    status_format = status_formats.get(value, text_format)
                    worksheet.write(row_num, col_num, value, status_format)
                else:
                    worksheet.write(row_num, col_num, value, text_format)

        last_row = len(data) + 5
        total_format = workbook.add_format({
            'bold': True,
            'bg_color': '#e9ecef',
            'border': 1,
            'font_color': '#1b4332'
        })
        worksheet.write(last_row, 3, 'TOTAL', total_format)
        worksheet.write(last_row, 4, f'=SUM(E6:E{last_row})', money_format)
        worksheet.write(last_row, 6, f'=SUM(G6:G{last_row})', money_format)
        worksheet.write(last_row, 7, f'=SUM(H6:H{last_row})', money_format)

        worksheet.autofilter(f'A4:I{last_row}')
        worksheet.freeze_panes(5, 0)

        # ========== SHEET 2: FILTER PARAMETERS (if filtered) ==========
        if invoice_ids:
            filter_df = pd.DataFrame({
                'Parameter': ['Search Query', 'Start Date', 'End Date', 'Generated On', 'Total Records', 'Generated By', 'Export Type'],
                'Value': [
                    filter_params.get('query', 'None'),
                    filter_params.get('start_date', 'None'),
                    filter_params.get('end_date', 'None'),
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    len(data),
                    request.user.get_full_name() or request.user.username,
                    'Referral - Filtered'
                ]
            })
            filter_df.to_excel(writer, sheet_name='Filter Parameters', index=False)

            filter_sheet = writer.sheets['Filter Parameters']
            filter_header = workbook.add_format({
                'bold': True,
                'bg_color': '#34495e',
                'font_color': '#ffffff',
                'border': 1
            })
            filter_value_format = workbook.add_format({
                'border': 1,
                'bg_color': '#f8f9fa'
            })

            for col_num, value in enumerate(filter_df.columns):
                filter_sheet.write(0, col_num, value, filter_header)
                filter_sheet.set_column(col_num, col_num, 25)

            for row_num, row in enumerate(filter_df.values, start=1):
                for col_num, value in enumerate(row):
                    filter_sheet.write(row_num, col_num, value, filter_value_format)

        # ========== SHEET 3: EXECUTIVE SUMMARY ==========
        total_invoiced = df['Invoice Amount'].sum()
        total_paid = df['Amount Paid'].sum()
        total_balance = df['Balance'].sum()
        collection_rate = (total_paid / total_invoiced * 100) if total_invoiced > 0 else 0

        summary_data = {
            'Metric': [
                'Total Invoiced Amount (TZS)',
                'Total Amount Paid (TZS)',
                'Total Outstanding Balance (TZS)',
                'Number of Invoices',
                'Paid Invoices',
                'Partial Payments',
                'Unpaid Invoices',
                'Collection Rate (%)'
            ],
            'Value': [
                total_invoiced,
                total_paid,
                total_balance,
                len(df),
                len(df[df['Payment Status'] == 'Paid']),
                len(df[df['Payment Status'] == 'Partial']),
                len(df[df['Payment Status'] == 'Unpaid']),
                f"{collection_rate:.2f}%"
            ]
        }
        summary_df = pd.DataFrame(summary_data)
        summary_df.to_excel(writer, sheet_name='Executive Summary', index=False)

        summary_sheet = writer.sheets['Executive Summary']
        summary_header = workbook.add_format({
            'bold': True,
            'bg_color': '#1b4332',
            'font_color': '#ffffff',
            'border': 1,
            'align': 'center'
        })
        summary_metric_format = workbook.add_format({
            'bold': True,
            'border': 1,
            'bg_color': '#f8f9fa'
        })
        summary_value_format = workbook.add_format({
            'border': 1,
            'align': 'right'
        })

        for col_num, value in enumerate(summary_df.columns):
            summary_sheet.write(0, col_num, value, summary_header)
            summary_sheet.set_column(col_num, col_num, 35)

        for row_num, row in enumerate(summary_df.values, start=1):
            summary_sheet.write(row_num, 0, row[0], summary_metric_format)
            summary_sheet.write(row_num, 1, row[1], summary_value_format)

        # ========== SHEET 4: DISTRICT ANALYSIS ==========
        district_summary = df.groupby('District').agg({
            'Invoice Amount': 'sum',
            'Amount Paid': 'sum',
            'Balance': 'sum',
            'Invoice Number': 'count'
        }).reset_index()
        district_summary.columns = ['District', 'Total Invoiced', 'Total Paid', 'Outstanding Balance', 'Invoice Count']
        district_summary['Collection Rate (%)'] = (
            district_summary['Total Paid'] / district_summary['Total Invoiced'] * 100
        ).round(2)
        district_summary['Collection Rate (%)'] = district_summary['Collection Rate (%)'].fillna(0)
        district_summary = district_summary.sort_values('Total Invoiced', ascending=False)
        district_summary.to_excel(writer, sheet_name='District Analysis', index=False)

        district_sheet = writer.sheets['District Analysis']
        district_header = workbook.add_format({
            'bold': True,
            'bg_color': '#2d6a4f',
            'font_color': '#ffffff',
            'border': 1,
            'align': 'center'
        })

        for col_num, value in enumerate(district_summary.columns):
            district_sheet.write(0, col_num, value, district_header)
            district_sheet.set_column(col_num, col_num, 20)

        for row_num, row in enumerate(district_summary.values, start=1):
            district_sheet.write(row_num, 0, row[0], text_format)
            district_sheet.write(row_num, 1, float(row[1]), money_format)
            district_sheet.write(row_num, 2, float(row[2]), money_format)
            district_sheet.write(row_num, 3, float(row[3]), money_format)
            district_sheet.write(row_num, 4, int(row[4]), text_format)
            district_sheet.write(row_num, 5, f"{row[5]:.2f}%", text_format)

        # ========== SHEET 5: MONTHLY TREND ==========
        df['Month'] = pd.to_datetime(df['Invoice Date']).dt.strftime('%Y-%m')
        monthly_trend = df.groupby('Month').agg({
            'Invoice Amount': 'sum',
            'Amount Paid': 'sum',
            'Balance': 'sum',
            'Invoice Number': 'count'
        }).reset_index()
        monthly_trend.columns = ['Month', 'Invoiced Amount', 'Paid Amount', 'Outstanding', 'Invoice Count']
        monthly_trend = monthly_trend.sort_values('Month')
        monthly_trend.to_excel(writer, sheet_name='Monthly Trend', index=False)

        trend_sheet = writer.sheets['Monthly Trend']
        trend_header = workbook.add_format({
            'bold': True,
            'bg_color': '#40916c',
            'font_color': '#ffffff',
            'border': 1,
            'align': 'center'
        })

        for col_num, value in enumerate(monthly_trend.columns):
            trend_sheet.write(0, col_num, value, trend_header)
            trend_sheet.set_column(col_num, col_num, 18)

        for row_num, row in enumerate(monthly_trend.values, start=1):
            trend_sheet.write(row_num, 0, row[0], text_format)
            trend_sheet.write(row_num, 1, float(row[1]), money_format)
            trend_sheet.write(row_num, 2, float(row[2]), money_format)
            trend_sheet.write(row_num, 3, float(row[3]), money_format)
            trend_sheet.write(row_num, 4, int(row[4]), text_format)

        # ========== SHEET 6: PAYMENT STATUS ANALYSIS ==========
        status_analysis = df['Payment Status'].value_counts().reset_index()
        status_analysis.columns = ['Payment Status', 'Count']
        status_analysis['Percentage (%)'] = (status_analysis['Count'] / len(df) * 100).round(2)
        status_analysis['Total Amount (TZS)'] = status_analysis['Payment Status'].apply(
            lambda x: df[df['Payment Status'] == x]['Invoice Amount'].sum()
        )
        status_analysis.to_excel(writer, sheet_name='Status Analysis', index=False)

        status_sheet = writer.sheets['Status Analysis']
        status_header = workbook.add_format({
            'bold': True,
            'bg_color': '#52b788',
            'font_color': '#ffffff',
            'border': 1,
            'align': 'center'
        })

        for col_num, value in enumerate(status_analysis.columns):
            status_sheet.write(0, col_num, value, status_header)
            status_sheet.set_column(col_num, col_num, 22)

    messages.success(request, f'Successfully exported {len(data)} referral invoice report(s).')
    return response


@login_required
def export_referral_invoices_pdf(request):
    """Export referral invoices to Premium Portrait PDF design"""
    invoice_ids = request.session.get('filtered_referral_invoice_ids', [])
    filter_params = request.session.get('referral_filter_parameters', {})
    
    if invoice_ids:
        invoices = ReferralInvoice.objects.filter(id__in=invoice_ids).select_related('referral_source')
        export_type = "Filtered"
    else:
        invoices = ReferralInvoice.objects.all().select_related('referral_source')
        export_type = "Full Report"
    
    invoices = invoices.order_by('-invoice_date')

    if not invoices.exists():
        messages.warning(request, "No data available to export.")
        return redirect('referral:dashboard')

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Referral_Financial_Statement_{datetime.now().strftime("%Y%m%d")}.pdf"'

    # Portrait A4 setup with elegant framing margins
    doc = SimpleDocTemplate(
        response, 
        pagesize=A4, 
        rightMargin=45, 
        leftMargin=45, 
        topMargin=50, 
        bottomMargin=50
    )
    
    available_width = doc.width
    
    # Premium Color Palette
    DEEP_GREEN = colors.HexColor('#14532D')
    EMERALD_HEADER = colors.HexColor('#064E3B')
    GOLD_ACCENT = colors.HexColor('#D4AF37')
    SOFT_GREY = colors.HexColor('#6B7280')
    LIGHT_GREY_BG = colors.HexColor('#F9FAFB')
    PALE_GREEN_BG = colors.HexColor('#ECFDF5') # Very faint green for alternating rows
    SUBTLE_BORDER = colors.HexColor('#E5E7EB')

    def add_page_elements(canvas, doc):
        canvas.saveState()
        page_num = canvas.getPageNumber()
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        text = f"Robby One Pharmacy • Page {page_num} • {now_str}"
        canvas.setFont('Helvetica-Oblique', 7)
        canvas.setFillColor(SOFT_GREY)
        canvas.drawCentredString(A4[0] / 2, 25, text)
        canvas.restoreState()

    story = []
    styles = getSampleStyleSheet()

    # --- Premium Typography Styles ---
    title_style = ParagraphStyle('Title', fontName='Times-Bold', alignment=TA_CENTER, fontSize=22, textColor=DEEP_GREEN, spaceAfter=2, leading=26)
    subtitle_style = ParagraphStyle('Subtitle', fontName='Helvetica', alignment=TA_CENTER, fontSize=11, textColor=SOFT_GREY, spaceAfter=4, letterSpacing=1)
    date_style = ParagraphStyle('DateStyle', fontName='Helvetica-Oblique', alignment=TA_CENTER, fontSize=9, textColor=SOFT_GREY)
    section_header_style = ParagraphStyle('SectionHeader', fontName='Times-Bold', fontSize=11, textColor=DEEP_GREEN, spaceBefore=12, spaceAfter=6)
    label_style = ParagraphStyle('Label', fontName='Helvetica-Bold', fontSize=8.5, textColor=colors.HexColor('#374151'))
    value_style = ParagraphStyle('Value', fontName='Helvetica', fontSize=8.5, textColor=colors.HexColor('#111827'))

    # 1. Premium Letterhead with Gold/Green Dual Border
    story.append(Paragraph("ROBBY ONE PHARMACY", title_style))
    story.append(Paragraph("REFERRAL SERVICES — FINANCIAL STATEMENT", subtitle_style))
    story.append(Paragraph(f"Report Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", date_style))
    story.append(Spacer(1, 6))
    
    # Elegant Double Line Separator
    line_data = [['', '']]
    line_table = Table(line_data, colWidths=[available_width * 0.5, available_width * 0.5])
    line_table.setStyle(TableStyle([
        ('LINEBELOW', (0, 0), (0, 0), 2.5, DEEP_GREEN),
        ('LINEBELOW', (1, 0), (1, 0), 0.8, GOLD_ACCENT),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(line_table)
    story.append(Spacer(1, 12))

    # 2. Calculate Metrics Safely in Python
    invoices_list = list(invoices)
    total_invoiced = sum(inv.purchase_amount for inv in invoices_list)
    total_paid = sum(inv.amount_paid for inv in invoices_list)
    total_balance = total_invoiced - total_paid
    collection_rate = (total_paid / total_invoiced * 100) if total_invoiced > 0 else 0
    
    paid_count = sum(1 for inv in invoices_list if inv.balance == 0)
    partial_count = sum(1 for inv in invoices_list if inv.balance > 0 and inv.amount_paid > 0)
    unpaid_count = sum(1 for inv in invoices_list if inv.amount_paid == 0)
    total_count = len(invoices_list)

    # 3. Report Parameters Box
    param_query = filter_params.get('query', 'None')
    param_start = filter_params.get('start_date', '')
    param_end = filter_params.get('end_date', '')
    param_user = request.user.get_full_name() or request.user.username
    now_formatted = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    param_content = [
        [Paragraph('<b>Report Parameters</b>', ParagraphStyle('BoxHead', fontName='Helvetica-Bold', fontSize=9, textColor=DEEP_GREEN)), ''],
        [Paragraph('Facility/Search:', label_style), Paragraph(param_query, value_style)],
        [Paragraph('Date Range:', label_style), Paragraph(f"{param_start} to {param_end}", value_style)],
        [Paragraph('Generated By:', label_style), Paragraph(param_user, value_style)],
        [Paragraph('Total Records:', label_style), Paragraph(str(total_count), value_style)],
    ]
    
    param_box = Table(param_content, colWidths=[1.5*inch, 4.5*inch])
    param_box.setStyle(TableStyle([
        ('SPAN', (0, 0), (1, 0)),
        ('BACKGROUND', (0, 0), (-1, -1), LIGHT_GREY_BG),
        ('BOX', (0, 0), (-1, -1), 0.5, SUBTLE_BORDER),
        ('LINEBELOW', (0, 0), (-1, 0), 0.5, SUBTLE_BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(param_box)

    # 4. Executive Summary Box
    paid_pct = (paid_count / total_count * 100) if total_count > 0 else 0
    partial_pct = (partial_count / total_count * 100) if total_count > 0 else 0
    unpaid_pct = (unpaid_count / total_count * 100) if total_count > 0 else 0

    summary_content = [
        [Paragraph('<b>Executive Summary</b>', ParagraphStyle('BoxHead2', fontName='Helvetica-Bold', fontSize=9, textColor=DEEP_GREEN)), '', '', ''],
        [Paragraph('Total Invoiced:', label_style), Paragraph(f"<b>TZS {total_invoiced:,.2f}</b>", value_style), 
         Paragraph('Paid Invoices:', label_style), Paragraph(f"{paid_count} ({paid_pct:.1f}%)", value_style)],
        [Paragraph('Total Paid:', label_style), Paragraph(f"<b>TZS {total_paid:,.2f}</b>", value_style), 
         Paragraph('Partial Payments:', label_style), Paragraph(f"{partial_count} ({partial_pct:.1f}%)", value_style)],
        [Paragraph('Outstanding Balance:', label_style), Paragraph(f"<b>TZS {total_balance:,.2f}</b>", value_style), 
         Paragraph('Unpaid Invoices:', label_style), Paragraph(f"{unpaid_count} ({unpaid_pct:.1f}%)", value_style)],
        [Paragraph('Collection Rate:', label_style), Paragraph(f"<b>{collection_rate:.1f}%</b>", value_style), 
         Paragraph('Total Invoices:', label_style), Paragraph(f"<b>{total_count}</b>", value_style)],
    ]
    
    summary_box = Table(summary_content, colWidths=[1.4*inch, 2.1*inch, 1.4*inch, 2.1*inch])
    summary_box.setStyle(TableStyle([
        ('SPAN', (0, 0), (-1, 0)),
        ('BACKGROUND', (0, 0), (-1, -1), LIGHT_GREY_BG),
        ('BOX', (0, 0), (-1, -1), 0.5, SUBTLE_BORDER),
        ('LINEBELOW', (0, 0), (-1, 0), 0.5, SUBTLE_BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(summary_box)
    story.append(Spacer(1, 12))

    # 5. Premium Invoice Table
    story.append(Paragraph("Invoice Details", section_header_style))
    
    table_headers = ['Invoice #', 'Facility', 'District', 'Date', 'Amount', 'Paid', 'Balance', 'Pay Date', 'Status']
    table_data = [table_headers]
    
    for inv in invoices_list:
        district = getattr(inv.referral_source, 'district', 'N/A')
        if hasattr(district, 'name'):
            district = district.name
            
        pay_date_str = inv.payment_date.strftime('%Y-%m-%d') if inv.payment_date else '-'
        status = 'Paid' if inv.balance == 0 else 'Partial' if inv.amount_paid > 0 else 'Unpaid'
        
        table_data.append([
            inv.invoice_number,
            inv.referral_source.name[:28],
            str(district)[:18],
            inv.invoice_date.strftime('%Y-%m-%d'),
            f"{inv.purchase_amount:,.0f}",
            f"{inv.amount_paid:,.0f}",
            f"{inv.balance:,.0f}",
            pay_date_str,
            status
        ])

    col_widths = [0.5*inch, 1.5*inch, 0.85*inch, 0.7*inch, 0.82*inch, 0.82*inch, 0.82*inch, 0.7*inch, 0.5*inch]
    
    details_table = Table(table_data, repeatRows=1, colWidths=col_widths)
    details_table.setStyle(TableStyle([
        # Premium Green Header
        ('BACKGROUND', (0, 0), (-1, 0), EMERALD_HEADER),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 7.5),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('TOPPADDING', (0, 0), (-1, 0), 6),
        
        # Ultra-clean Body Formatting
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 7.5),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#1F2937')),
        ('ALIGN', (0, 1), (0, -1), 'CENTER'), 
        ('ALIGN', (3, 1), (3, -1), 'CENTER'), 
        ('ALIGN', (4, 1), (7, -1), 'RIGHT'),  
        ('ALIGN', (8, 1), (8, -1), 'CENTER'), 
        
        # Expensive look: Soft hairline borders instead of harsh black grids
        ('GRID', (0, 0), (-1, -1), 0.25, SUBTLE_BORDER),
        ('BOX', (0, 0), (-1, -1), 1, DEEP_GREEN), # Deep green outer frame
        ('LINEBELOW', (0, 0), (-1, 0), 1.5, DEEP_GREEN), # Thicker line under header
        
        # Elegant Alternating Rows (White and Pale Green tint)
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, PALE_GREEN_BG]),
        
        # Generous but neat padding
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 1), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    
    story.append(details_table)
    story.append(Spacer(1, 15))

    # 6. Premium Bottom Summary Block
    bottom_summary_data = [
        [Paragraph('<b>FINANCIAL SUMMARY</b>', ParagraphStyle('SumHead', fontName='Helvetica-Bold', fontSize=8, textColor=colors.white))],
        [Paragraph(f'Total Invoiced:  <b>TZS {total_invoiced:,.2f}</b>', ParagraphStyle('SumVal', fontName='Helvetica', fontSize=8, textColor=colors.HexColor('#1F2937')))],
        [Paragraph(f'Total Paid:  <b>TZS {total_paid:,.2f}</b>', ParagraphStyle('SumVal2', fontName='Helvetica', fontSize=8, textColor=colors.HexColor('#1F2937')))],
        [Paragraph(f'Outstanding:  <b>TZS {total_balance:,.2f}</b>', ParagraphStyle('SumVal3', fontName='Helvetica-Bold', fontSize=8.5, textColor=DEEP_GREEN))],
    ]
    
    bottom_table = Table(bottom_summary_data, colWidths=[2.5*inch])
    bottom_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, 0), EMERALD_HEADER),
        ('BACKGROUND', (0, 1), (-1, -1), LIGHT_GREY_BG),
        ('BOX', (0, 0), (-1, -1), 1, DEEP_GREEN),
        ('LINEBELOW', (0, 0), (0, 0), 1, DEEP_GREEN),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
    ]))
    
    # Align wrapper to the right
    wrapper_table = Table([[bottom_table]], colWidths=[available_width])
    wrapper_table.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'RIGHT')]))
    story.append(wrapper_table)

    # Build PDF
    doc.build(story, onFirstPage=add_page_elements, onLaterPages=add_page_elements)
    return response

# ========== HELPER VIEWS ==========

@login_required
def clear_referral_filters(request):
    if 'filtered_referral_invoice_ids' in request.session:
        del request.session['filtered_referral_invoice_ids']
    if 'referral_filter_parameters' in request.session:
        del request.session['referral_filter_parameters']
    return redirect('referral:invoice_list')
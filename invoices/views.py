from django.shortcuts import render, get_object_or_404
from django.db.models import Sum
from .models import District, Facility, Invoice

def home(request):
    districts = District.objects.annotate(
        total_invoices=Sum('facilities__invoices__invoice_amount'),
        total_paid=Sum('facilities__invoices__amount_paid')
    )
    return render(request, 'invoices/home.html', {'districts': districts})

def district_detail(request, district_id):
    district = get_object_or_404(District, pk=district_id)
    facilities = district.facilities.annotate(
        total_invoices=Sum('invoices__invoice_amount'),
        total_paid=Sum('invoices__amount_paid')
    )
    return render(request, 'invoices/district_detail.html', {
        'district': district,
        'facilities': facilities
    })

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

def all_invoices(request):
    invoices = Invoice.objects.select_related('facility__district').all().order_by('-invoice_date')
    return render(request, 'invoices/all_invoices.html', {'invoices': invoices})

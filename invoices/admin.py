from django.contrib import admin
from .models import District, Facility, Invoice
from unfold.admin import ModelAdmin

@admin.register(District)
class DistrictAdmin(ModelAdmin):
    list_display = ('name', 'tin_number')
    search_fields = ('name',)

@admin.register(Facility)
class FacilityAdmin(ModelAdmin):
    list_display = ('name', 'district')
    list_filter = ('district',)
    search_fields = ('name',)

@admin.register(Invoice)
class InvoiceAdmin(ModelAdmin):
    list_display = ('invoice_number', 'facility', 'invoice_date', 'invoice_amount', 'amount_paid', 'balance')
    list_filter = ('facility__district', 'payment_date')
    search_fields = ('invoice_number', 'facility__name')

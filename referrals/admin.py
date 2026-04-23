from django.contrib import admin
from .models import ReferralSource, ReferralInvoice


@admin.register(ReferralSource)
class ReferralSourceAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'tin_number', 'created_at')  # Removed contact_person, phone, email
    list_filter = ('created_at',)
    search_fields = ('name', 'tin_number')
    ordering = ('name',)


@admin.register(ReferralInvoice)
class ReferralInvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'referral_source', 'invoice_date', 'purchase_amount', 'amount_paid', 'balance')
    list_filter = ('referral_source', 'invoice_date')
    search_fields = ('invoice_number', 'referral_source__name')
    list_select_related = ('referral_source',)
    
    def balance(self, obj):
        return obj.balance
    balance.short_description = 'Balance'
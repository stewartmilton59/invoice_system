from django.db import models
from django.core.validators import MinValueValidator
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from invoices.models import Facility  # if you want to link referral to facility
# Alternatively, you could define a separate ReferralSource model independent of Facility

class ReferralSource(models.Model):
    """Represents a referral hospital or clinic"""
    name = models.CharField(max_length=200, unique=True, verbose_name="Hospital Name")
    tin_number = models.CharField(max_length=50, blank=True, verbose_name="TIN Number")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

class ReferralInvoice(models.Model):
    """Invoice for a referral, tracking purchases and payments"""
    referral_source = models.ForeignKey(ReferralSource, on_delete=models.CASCADE, related_name='invoices')
    invoice_number = models.CharField(max_length=50, unique=True)
    invoice_date = models.DateField()
    purchase_amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    payment_date = models.DateField(null=True, blank=True)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    facility = models.ForeignKey(Facility, on_delete=models.SET_NULL, null=True, blank=True, related_name='referral_invoices')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-invoice_date']

    def __str__(self):
        return f"Referral Invoice #{self.invoice_number} - {self.referral_source.name}"

    @property
    def balance(self):
        return self.purchase_amount - self.amount_paid



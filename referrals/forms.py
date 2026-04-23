from django import forms
from .models import ReferralSource, ReferralInvoice
from django.core.exceptions import ValidationError


class ReferralSourceForm(forms.ModelForm):
    class Meta:
        model = ReferralSource
        fields = ['name', 'tin_number']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter hospital name'}),
            'tin_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter TIN number'}),
        }

    def clean_tin_number(self):
        tin_number = self.cleaned_data.get('tin_number')
        if tin_number:
            # You can add TIN validation logic here if needed
            # For example, check format or uniqueness
            if len(tin_number) < 5:
                raise forms.ValidationError('TIN number must be at least 5 characters.')
        return tin_number


class ReferralInvoiceForm(forms.ModelForm):
    class Meta:
        model = ReferralInvoice
        fields = ['referral_source', 'invoice_number', 'invoice_date', 'purchase_amount', 'payment_date', 'amount_paid', 'facility']
        widgets = {
            'referral_source': forms.Select(attrs={'class': 'form-control'}),
            'invoice_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Invoice number'}),
            'invoice_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'purchase_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'Purchase amount'}),
            'payment_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'amount_paid': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'Amount paid'}),
            'facility': forms.Select(attrs={'class': 'form-control'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        amount_paid = cleaned_data.get('amount_paid')
        purchase_amount = cleaned_data.get('purchase_amount')

        if amount_paid and purchase_amount and amount_paid > purchase_amount:
            raise ValidationError("Amount paid cannot exceed purchase amount.")
        return cleaned_data


class ReferralPaymentUpdateForm(forms.ModelForm):
    """Form for updating payment on an existing referral invoice"""
    class Meta:
        model = ReferralInvoice
        fields = ['payment_date', 'amount_paid']
        widgets = {
            'payment_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'amount_paid': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

    def clean_amount_paid(self):
        amount_paid = self.cleaned_data.get('amount_paid')
        if amount_paid and amount_paid > self.instance.purchase_amount:
            raise ValidationError(f'Amount paid cannot exceed purchase amount ({self.instance.purchase_amount})')
        return amount_paid
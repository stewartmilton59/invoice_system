from django import forms
from .models import Invoice

class PaymentUpdateForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = ['payment_date', 'amount_paid']
        widgets = {
            'payment_date': forms.DateInput(attrs={'type': 'date'}),
        }

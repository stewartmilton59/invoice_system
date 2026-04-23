from django import forms
from .models import District, Facility, Invoice
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User

#######################################################################
from django.contrib.auth.forms import UserCreationForm
from datetime import date
from .models import UserProfile

class UserUpdateForm(forms.ModelForm):
    """Form for updating user account information"""
    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Username'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First Name'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last Name'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email Address'}),
        }

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if username != self.instance.username and User.objects.filter(username=username).exists():
            raise forms.ValidationError('This username is already taken.')
        return username

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email != self.instance.email and User.objects.filter(email=email).exists():
            raise forms.ValidationError('This email is already registered.')
        return email

class ProfileUpdateForm(forms.ModelForm):
    """Form for updating user profile information"""
    class Meta:
        model = UserProfile
        fields = ['phone', 'address', 'job_title', 'department', 'bio', 'website',
                  'company', 'date_of_birth', 'preferred_language', 'theme_preference',
                  'email_notifications', 'sms_notifications']
        widgets = {
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone Number'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Your address'}),
            'job_title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Job Title'}),
            'department': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Department'}),
            'bio': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Tell us about yourself'}),
            'website': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://example.com'}),
            'company': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Company Name'}),
            'date_of_birth': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'preferred_language': forms.Select(attrs={'class': 'form-select'}),
            'theme_preference': forms.Select(attrs={'class': 'form-select'}),
            'email_notifications': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'sms_notifications': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['bio'].widget.attrs['rows'] = 4

class ProfilePictureForm(forms.ModelForm):
    """Form for updating profile picture"""
    class Meta:
        model = UserProfile
        fields = ['profile_picture']
        widgets = {
            'profile_picture': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
        }


class SearchForm(forms.Form):
    query = forms.CharField(
        required=False,
        label='Search',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search by invoice #, facility, or district...'
        })
    )

class DateRangeForm(forms.Form):
    start_date = forms.DateField(
        required=False,
        label='From Date',
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control datepicker',
            'placeholder': 'dd/mm/yyyy'
        }),
        input_formats=['%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y']
    )
    end_date = forms.DateField(
        required=False,
        label='To Date',
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control datepicker',
            'placeholder': 'dd/mm/yyyy'
        }),
        input_formats=['%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y']
    )

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')

        if start_date and end_date and start_date > end_date:
            raise forms.ValidationError("Start date cannot be after end date.")

        return cleaned_data

# Add this new form for advanced filtering
class AdvancedFilterForm(forms.Form):
    facility = forms.ModelChoiceField(
        queryset=Facility.objects.all(),
        required=False,
        label='Facility',
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    district = forms.ModelChoiceField(
        queryset=District.objects.all(),
        required=False,
        label='District',
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    payment_status = forms.ChoiceField(
        choices=[
            ('', 'All Status'),
            ('paid', 'Paid'),
            ('partial', 'Partial'),
            ('unpaid', 'Unpaid'),
        ],
        required=False,
        label='Payment Status',
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    min_amount = forms.DecimalField(
        required=False,
        label='Min Amount',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Min amount'})
    )
    max_amount = forms.DecimalField(
        required=False,
        label='Max Amount',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Max amount'})
    )
#####################################################################

# update Invoice, facility, District

class DistrictForm(forms.ModelForm):
    class Meta:
        model = District
        fields = ['name', 'tin_number']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter district name'}),
            'tin_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter TIN number'}),
        }

class FacilityForm(forms.ModelForm):
    class Meta:
        model = Facility
        fields = ['district', 'name']
        widgets = {
            'district': forms.Select(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter facility name'}),
        }

class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = ['facility', 'invoice_number', 'invoice_date', 'invoice_amount', 'payment_date', 'amount_paid']
        widgets = {
            'facility': forms.Select(attrs={'class': 'form-control'}),
            'invoice_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter invoice number'}),
            'invoice_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'invoice_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'Enter amount'}),
            'payment_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'amount_paid': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'Enter amount paid'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        amount_paid = cleaned_data.get('amount_paid')
        invoice_amount = cleaned_data.get('invoice_amount')

        if amount_paid and invoice_amount and amount_paid > invoice_amount:
            raise forms.ValidationError("Amount paid cannot exceed invoice amount.")

        return cleaned_data

# update Invoice, facility, District

class SignupForm(forms.ModelForm):
    full_name = forms.CharField(max_length=100, required=True, label="Full Name")
    email = forms.EmailField(required=True, label="Email")
    password = forms.CharField(widget=forms.PasswordInput, required=True, label="Password")
    confirm_password = forms.CharField(widget=forms.PasswordInput, required=True, label="Confirm Password")

    class Meta:
        model = User
        fields = ['username', 'email', 'password']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if User.objects.filter(username=username).exists():
            raise ValidationError("This username is already taken.")
        return username

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise ValidationError("This email is already registered.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm = cleaned_data.get('confirm_password')
        if password and confirm and password != confirm:
            self.add_error('confirm_password', "Passwords do not match.")
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        user.email = self.cleaned_data['email']
        # Optionally store full name in first_name/last_name
        full_name = self.cleaned_data['full_name'].split()
        user.first_name = full_name[0] if full_name else ''
        user.last_name = ' '.join(full_name[1:]) if len(full_name) > 1 else ''
        if commit:
            user.save()
        return user


##############################################################


class PaymentUpdateForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = ['payment_date', 'amount_paid']
        widgets = {
            'payment_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'amount_paid': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

    def clean_amount_paid(self):
        amount_paid = self.cleaned_data.get('amount_paid')
        if amount_paid and amount_paid > self.instance.invoice_amount:
            raise ValidationError(f'Amount paid cannot exceed invoice amount ({self.instance.invoice_amount})')
        return amount_paid

class DateRangeForm(forms.Form):
    start_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    end_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}))

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        if start_date and end_date and start_date > end_date:
            raise ValidationError('End date must be after start date')
        return cleaned_data

class SearchForm(forms.Form):
    query = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search by facility name, district, or invoice number...'
        })
    )
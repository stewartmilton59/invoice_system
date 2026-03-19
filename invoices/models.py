from django.db import models
from django.core.validators import MinValueValidator

class District(models.Model):
    name = models.CharField(max_length=100, unique=True)
    tin_number = models.CharField(max_length=50, blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

class Facility(models.Model):
    district = models.ForeignKey(District, on_delete=models.CASCADE, related_name='facilities')
    name = models.CharField(max_length=200)

    class Meta:
        ordering = ['name']
        unique_together = ['district', 'name']

    def __str__(self):
        return f"{self.name} ({self.district.name})"

class Invoice(models.Model):
    facility = models.ForeignKey(Facility, on_delete=models.CASCADE, related_name='invoices')
    invoice_number = models.CharField(max_length=50)
    invoice_date = models.DateField()
    invoice_amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    payment_date = models.DateField(null=True, blank=True)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])

    class Meta:
        ordering = ['-invoice_date']

    def __str__(self):
        return f"Invoice #{self.invoice_number} - {self.facility.name}"

    @property
    def balance(self):
        return self.invoice_amount - self.amount_paid

from django.core.management.base import BaseCommand
from django.utils import timezone
from invoices.models import Invoice, Notification
from datetime import timedelta

class Command(BaseCommand):
    help = 'Check for overdue invoices and create notifications'

    def handle(self, *args, **options):
        today = timezone.now().date()
        overdue_invoices = Invoice.objects.filter(
            balance__gt=0,
            invoice_date__lte=today - timedelta(days=30)
        )

        for invoice in overdue_invoices:
            # Check if notification already exists for this invoice
            existing_notification = Notification.objects.filter(
                user=invoice.facility.user_set.first(),  # You'll need to associate facilities with users
                title__icontains='Overdue',
                message__icontains=invoice.invoice_number
            ).exists()

            if not existing_notification:
                days_overdue = (today - invoice.invoice_date).days
                Notification.objects.create(
                    user=invoice.facility.user_set.first(),
                    title='Payment Overdue',
                    message=f'Invoice #{invoice.invoice_number} is overdue by {days_overdue} days. Balance: {invoice.balance:,.2f}',
                    notification_type='warning',
                    link=f'/update-payment/{invoice.id}/'
                )

        self.stdout.write(self.style.SUCCESS(f'Checked for overdue invoices. Created notifications for new overdue invoices.'))
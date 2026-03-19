import pandas as pd
from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_date
from invoices.models import District, Facility, Invoice
import os
from datetime import datetime

class Command(BaseCommand):
    help = 'Import districts, facilities and invoices from Excel file'

    def handle(self, *args, **options):
        file_path = 'MWANZA SECRETARIATE FINANCIAL STATEMENT.xlsx'
        if not os.path.exists(file_path):
            self.stderr.write(f"File {file_path} not found.")
            return

        xl = pd.ExcelFile(file_path)
        sheet_names = xl.sheet_names  # ['ILEMELA', 'BUCHOSA', ...]

        for sheet in sheet_names:
            self.stdout.write(f"Processing sheet: {sheet}")
            df = pd.read_excel(file_path, sheet_name=sheet, header=None)

            # Extract district name and TIN from first two rows
            district_name = str(df.iloc[0, 0]).strip()
            tin = str(df.iloc[1, 1]).strip() if pd.notna(df.iloc[1, 1]) else ''

            district, _ = District.objects.get_or_create(name=district_name, defaults={'tin_number': tin})

            # Header is always at row index 2
            header_row_idx = 2
            header = df.iloc[header_row_idx].tolist()

            # Data rows start after header
            data_rows = df.iloc[header_row_idx+1:].copy()
            # Set proper column names (first row of data becomes header)
            data_rows.columns = header

            # Rename columns to simplified names (handle possible variations)
            col_map = {
                'S/N': 'sn',
                'FACILITY': 'facility',
                'INVOICE NUMBER': 'invoice_no',
                'INVOINCE DATE': 'invoice_date',   # note typo in original
                'INVOICE AMOUNT': 'amount',
                'PAYMENT DATE': 'payment_date',
                'AMOUNT PAID': 'paid',
                'BALANCE': 'balance'   # ignored, computed
            }
            # Only rename columns that exist
            rename_dict = {old: new for old, new in col_map.items() if old in data_rows.columns}
            data_rows.rename(columns=rename_dict, inplace=True)

            # Process each row
            for idx, row in data_rows.iterrows():
                facility_name = row.get('facility')
                if pd.isna(facility_name) or str(facility_name).strip() == '':
                    continue  # skip empty rows

                invoice_no = row.get('invoice_no')
                if pd.isna(invoice_no):
                    continue

                # Parse dates (multiple formats)
                inv_date = self.parse_date(row.get('invoice_date'))
                pay_date = self.parse_date(row.get('payment_date'))

                # Parse amounts
                try:
                    amount = float(row.get('amount')) if pd.notna(row.get('amount')) else 0
                except:
                    amount = 0

                try:
                    paid = float(row.get('paid')) if pd.notna(row.get('paid')) else 0
                except:
                    paid = 0

                if amount == 0:
                    continue  # no invoice amount, skip

                # Get or create facility
                facility, _ = Facility.objects.get_or_create(
                    district=district,
                    name=str(facility_name).strip()
                )

                # Create invoice (avoid duplicates by invoice number and facility)
                Invoice.objects.get_or_create(
                    facility=facility,
                    invoice_number=str(invoice_no).strip(),
                    defaults={
                        'invoice_date': inv_date or datetime.now().date(),
                        'invoice_amount': amount,
                        'payment_date': pay_date,
                        'amount_paid': paid,
                    }
                )

            self.stdout.write(self.style.SUCCESS(f"Imported {sheet}"))

    def parse_date(self, val):
        if pd.isna(val):
            return None
        if isinstance(val, datetime):
            return val.date()
        if isinstance(val, pd.Timestamp):
            return val.date()
        # Try string parsing with different formats
        date_str = str(val).strip()
        for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%Y-%d-%m', '%d/%m/%y'):
            try:
                return datetime.strptime(date_str, fmt).date()
            except:
                continue
        return None

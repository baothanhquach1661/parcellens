import io
from datetime import datetime, timezone as dt_timezone
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase

from inventory.models import Location
from orders.models import FinancialStatus, Order

from .importers import OrdersImporter
from .models import ImportStatus

SAMPLE = Path(settings.BASE_DIR) / 'samples' / 'shopify_orders_sample.csv'


def run_import(content, name='orders.csv'):
    if isinstance(content, str):
        content = content.encode('utf-8')
    return OrdersImporter(io.BytesIO(content), file_name=name).run()


class OrdersImporterTests(TestCase):
    def setUp(self):
        Location.objects.create(code='LA', name='Los Angeles', is_default=True)
        Location.objects.create(code='NJ', name='New Jersey')

    def test_sample_file(self):
        log = run_import(SAMPLE.read_bytes())

        self.assertEqual(log.status, ImportStatus.SUCCEEDED)
        self.assertEqual((log.rows_total, log.rows_created, log.rows_failed), (9, 6, 3))
        failed = {error['record']: error['row'] for error in log.errors}
        # Line numbers match the spreadsheet: #2007's bad quantity is on its second row.
        self.assertEqual(failed, {'#2006': 10, '#2007': 12, '#2008': 13})

    def test_multi_row_order_keeps_every_line_item(self):
        run_import(SAMPLE.read_bytes())

        self.assertEqual(Order.objects.get(name='#2003').items.count(), 3)

    def test_values_are_parsed(self):
        run_import(SAMPLE.read_bytes())
        order = Order.objects.get(name='#2001')

        # "2026-10-08 09:15:40 -0700" is stored in UTC.
        self.assertEqual(order.placed_at, datetime(2026, 10, 8, 16, 15, 40, tzinfo=dt_timezone.utc))
        self.assertEqual(order.fulfillment_location.code, 'LA')  # empty column -> default
        self.assertEqual(Order.objects.get(name='#2002').fulfillment_location.code, 'NJ')
        self.assertIsNotNone(Order.objects.get(name='#2005').cancelled_at)
        # Bad-looking data is kept as is; the rules engine flags it later.
        self.assertEqual(Order.objects.get(name='#2004').ship_zip, '2108')
        self.assertEqual(Order.objects.get(name='#2009').items.get().sku, 'GEL-999')

    def test_one_bad_line_rejects_the_whole_order(self):
        run_import(SAMPLE.read_bytes())

        self.assertFalse(Order.objects.filter(name='#2007').exists())

    def test_reimport_updates_instead_of_duplicating(self):
        run_import(SAMPLE.read_bytes())
        log = run_import(SAMPLE.read_bytes())

        self.assertEqual((log.rows_created, log.rows_updated), (0, 6))
        self.assertEqual(Order.objects.count(), 6)
        self.assertEqual(Order.objects.get(name='#2003').items.count(), 3)

    def test_reimport_replaces_line_items(self):
        run_import(SAMPLE.read_bytes())
        changed = SAMPLE.read_text().replace('2,Gel Polish Shade 104', '5,Gel Polish Shade 104')
        run_import(changed)

        self.assertEqual(Order.objects.get(name='#2001').items.get(sku='GEL-104').quantity, 5)

    def test_excel_byte_order_mark_is_ignored(self):
        log = run_import(b'\xef\xbb\xbf' + SAMPLE.read_bytes())

        self.assertEqual(log.rows_created, 6)

    def test_missing_column_fails_the_whole_file(self):
        log = run_import('Name,Email\n#1,a@example.com\n')

        self.assertEqual(log.status, ImportStatus.FAILED)
        self.assertIn('lineitem sku', log.errors[0]['message'])
        self.assertFalse(Order.objects.exists())

    def test_without_a_default_location_nothing_is_imported(self):
        Location.objects.update(is_default=False)
        log = run_import(SAMPLE.read_bytes())

        self.assertEqual(log.status, ImportStatus.FAILED)
        self.assertFalse(Order.objects.exists())

    def test_financial_status_is_matched_case_insensitively(self):
        run_import(SAMPLE.read_text().replace(',paid,', ',Paid,', 1))

        self.assertEqual(Order.objects.get(name='#2001').financial_status, FinancialStatus.PAID)

    def test_command_prints_a_summary(self):
        out = io.StringIO()
        call_command('import_csv', 'orders', str(SAMPLE), stdout=out)

        self.assertIn('9 records, 6 created, 0 updated, 3 failed', out.getvalue())

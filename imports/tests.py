import io
from datetime import datetime, timezone as dt_timezone
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase

from inventory.models import InventoryItem, InventoryLevel, Location
from orders.models import Carrier, FinancialStatus, Order, Shipment, ShipmentStatus, TrackingEvent

from .importers import InventoryImporter, OrdersImporter, TrackingImporter
from .models import ImportLog, ImportStatus

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


INVENTORY_SAMPLE = Path(settings.BASE_DIR) / 'samples' / 'inventory_sample.csv'
TRACKING_SAMPLE = Path(settings.BASE_DIR) / 'samples' / 'tracking_sample.csv'


class InventoryImporterTests(TestCase):
    def setUp(self):
        # Demo data provides the two warehouses and the SKU catalog.
        call_command('seed_demo', orders=20, seed=3, stdout=io.StringIO())

    def run_file(self, content=None):
        content = content if content is not None else INVENTORY_SAMPLE.read_bytes()
        if isinstance(content, str):
            content = content.encode('utf-8')
        return InventoryImporter(io.BytesIO(content), file_name='inventory.csv').run()

    def test_sample_file(self):
        log = self.run_file()

        self.assertEqual(log.status, ImportStatus.SUCCEEDED)
        self.assertEqual((log.rows_total, log.rows_created, log.rows_updated, log.rows_failed), (10, 2, 4, 4))
        errors = {error['row']: error['message'] for error in log.errors}
        self.assertIn("unknown location 'Dallas warehouse'", errors[8])
        self.assertIn('must be 0 or more', errors[9])
        self.assertEqual(errors[10], 'SKU is empty')
        self.assertIn('Duplicate of line 2', errors[11])

    def test_location_matches_code_or_name(self):
        self.run_file()

        levels = InventoryLevel.objects.filter(item__sku='GEL-101')
        self.assertEqual({level.location.code: level.on_hand for level in levels}, {'LA': 120, 'NJ': 80})

    def test_new_sku_is_created_with_its_name(self):
        self.run_file()

        item = InventoryItem.objects.get(sku='GEL-121')
        self.assertEqual(item.name, 'Gel Polish Shade 121')
        self.assertEqual(item.levels.count(), 2)

    def test_reimport_changes_nothing(self):
        self.run_file()
        log = self.run_file()

        self.assertEqual((log.rows_created, log.rows_updated), (0, 6))
        self.assertEqual(InventoryLevel.objects.filter(item__sku='GEL-121').count(), 2)

    def test_simple_format_is_accepted(self):
        log = self.run_file('sku,name,location,on_hand\nGEL-101,Gel Polish Shade 101,LA,7\n')

        self.assertEqual(log.rows_updated, 1)
        self.assertEqual(InventoryLevel.objects.get(item__sku='GEL-101', location__code='LA').on_hand, 7)


class TrackingImporterTests(TestCase):
    def setUp(self):
        Location.objects.create(code='LA', name='Los Angeles', is_default=True)
        Location.objects.create(code='NJ', name='New Jersey')
        run_import(SAMPLE.read_bytes())  # orders #2001-#2009

    def run_file(self, content=None):
        content = content if content is not None else TRACKING_SAMPLE.read_bytes()
        if isinstance(content, str):
            content = content.encode('utf-8')
        return TrackingImporter(io.BytesIO(content), file_name='tracking.csv').run()

    def test_sample_file(self):
        log = self.run_file()

        self.assertEqual((log.rows_total, log.rows_created, log.rows_failed), (11, 6, 5))
        messages = {error['row']: error['message'] for error in log.errors}
        self.assertIn("no order named '#9999'", messages[8])
        self.assertIn("'ontrac' is not one of", messages[9])
        self.assertIn('in the future', messages[10])
        self.assertIn('already belongs to order #2002', messages[11])
        self.assertIn("'lost_in_space' is not one of", messages[12])

    def test_rows_in_any_order_give_the_newest_status(self):
        self.run_file()

        shipment = Shipment.objects.get(tracking_number='1Z999AA10123456784')
        self.assertEqual(shipment.order.name, '#2002')
        self.assertEqual(shipment.status, ShipmentStatus.DELIVERED)
        self.assertEqual(shipment.events.count(), 3)

    def test_tracking_numbers_are_normalised(self):
        self.run_file()

        # "1Z 999 AA1 01 2345 6784" and "1Z999AA10123456784" are the same package.
        self.assertEqual(Shipment.objects.filter(carrier=Carrier.UPS).count(), 1)

    def test_carrier_words_map_to_statuses(self):
        self.run_file()

        usps = Shipment.objects.get(carrier=Carrier.USPS)
        self.assertEqual(usps.status, ShipmentStatus.EXCEPTION)  # "Failed Attempt"
        self.assertEqual(
            list(usps.events.values_list('status', flat=True)),
            [ShipmentStatus.LABEL_CREATED, ShipmentStatus.EXCEPTION],  # "Pre-Transit" first
        )

    def test_reimport_adds_no_events(self):
        self.run_file()
        log = self.run_file()

        self.assertEqual((log.rows_created, log.rows_updated), (0, 6))
        self.assertEqual(TrackingEvent.objects.count(), 6)


class UploadPageTests(TestCase):
    def setUp(self):
        from accounts.models import User

        Location.objects.create(code='LA', name='Los Angeles', is_default=True)
        Location.objects.create(code='NJ', name='New Jersey')
        self.user = User.objects.create_superuser('ops', 'ops@example.com', 'x')
        self.client.force_login(self.user)
        self.url = '/admin/imports/importlog/upload/'

    def test_page_shows_the_form(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="file"')

    def test_upload_runs_the_import_and_opens_the_log(self):
        with SAMPLE.open('rb') as file:
            response = self.client.post(self.url, {'kind': 'orders', 'file': file})

        log = ImportLog.objects.get()
        self.assertRedirects(response, f'/admin/imports/importlog/{log.pk}/change/')
        self.assertEqual(log.uploaded_by, self.user)
        self.assertEqual(log.rows_created, 6)

    def test_non_csv_file_is_refused(self):
        upload = io.BytesIO(b'not a csv')
        upload.name = 'orders.xlsx'
        response = self.client.post(self.url, {'kind': 'orders', 'file': upload})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Choose a .csv file')
        self.assertFalse(ImportLog.objects.exists())


class ErrorTableTests(TestCase):
    def test_csv_content_is_escaped_in_the_admin(self):
        from accounts.models import User

        log = ImportLog.objects.create(kind='orders', file_name='x.csv')
        log.add_error(2, "Status: '<script>alert(1)</script>' is not valid", record='#1')
        log.save()
        self.client.force_login(User.objects.create_superuser('ops', 'ops@example.com', 'x'))

        response = self.client.get(f'/admin/imports/importlog/{log.pk}/change/')

        self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertContains(response, '&lt;script&gt;alert(1)&lt;/script&gt;')

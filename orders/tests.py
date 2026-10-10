from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from inventory.models import Location

from .models import (
    Carrier,
    FinancialStatus,
    Order,
    OrderItem,
    Shipment,
    ShipmentStatus,
    TrackingEvent,
)


def make_order(name='#1001', **kwargs):
    location = Location.objects.get_or_create(code='LA', defaults={'name': 'Los Angeles'})[0]
    defaults = {
        'fulfillment_location': location,
        'financial_status': FinancialStatus.PAID,
        'placed_at': timezone.now(),
        'total_price': Decimal('49.90'),
    }
    defaults.update(kwargs)
    return Order.objects.create(name=name, **defaults)


class OrderConstraintTests(TestCase):
    def test_order_name_is_unique(self):
        make_order('#1001')

        with self.assertRaises(IntegrityError), transaction.atomic():
            make_order('#1001')

    def test_unknown_financial_status_is_rejected_by_the_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_order(financial_status='lost')

    def test_order_item_quantity_must_be_at_least_one(self):
        order = make_order()

        with self.assertRaises(IntegrityError), transaction.atomic():
            OrderItem.objects.create(
                order=order, sku='GEL-102', title='Gel polish', quantity=0, unit_price=Decimal('9.95'),
            )


class ShipmentTests(TestCase):
    def setUp(self):
        self.order = make_order()
        self.shipment = Shipment.objects.create(
            order=self.order,
            carrier=Carrier.UPS,
            tracking_number='1Z999AA10123456784',
            shipped_at=timezone.now() - timedelta(days=3),
        )

    def add_event(self, status, hours_ago):
        return TrackingEvent.objects.create(
            shipment=self.shipment,
            status=status,
            occurred_at=timezone.now() - timedelta(hours=hours_ago),
        )

    def test_tracking_number_is_unique_per_carrier(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Shipment.objects.create(
                order=self.order,
                carrier=Carrier.UPS,
                tracking_number='1Z999AA10123456784',
                shipped_at=timezone.now(),
            )

    def test_same_event_cannot_be_imported_twice(self):
        event = self.add_event(ShipmentStatus.IN_TRANSIT, hours_ago=10)

        with self.assertRaises(IntegrityError), transaction.atomic():
            TrackingEvent.objects.create(
                shipment=self.shipment, status=event.status, occurred_at=event.occurred_at,
            )

    def test_sync_uses_the_newest_event_even_if_imported_last(self):
        delivered = self.add_event(ShipmentStatus.DELIVERED, hours_ago=1)
        # An older event arrives late from the carrier feed.
        self.add_event(ShipmentStatus.IN_TRANSIT, hours_ago=20)

        self.shipment.sync_from_latest_event()
        self.shipment.refresh_from_db()

        self.assertEqual(self.shipment.status, ShipmentStatus.DELIVERED)
        self.assertEqual(self.shipment.last_event_at, delivered.occurred_at)
        self.assertEqual(self.shipment.delivered_at, delivered.occurred_at)

    def test_sync_without_events_changes_nothing(self):
        self.shipment.sync_from_latest_event()
        self.shipment.refresh_from_db()

        self.assertEqual(self.shipment.status, ShipmentStatus.LABEL_CREATED)
        self.assertIsNone(self.shipment.last_event_at)

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from orders.models import Carrier, Order, Shipment, ShipmentStatus, TrackingEvent

from ..models import ImportKind
from ..parsing import clean, parse_choice, parse_date, parse_datetime
from .base import BaseImporter

# Words carriers and tracking tools use, mapped to ShipRadar statuses.
STATUS_ALIASES = {
    'pre_transit': ShipmentStatus.LABEL_CREATED,
    'info_received': ShipmentStatus.LABEL_CREATED,
    'label_printed': ShipmentStatus.LABEL_CREATED,
    'picked_up': ShipmentStatus.IN_TRANSIT,
    'failed_attempt': ShipmentStatus.EXCEPTION,
    'delivery_attempted': ShipmentStatus.EXCEPTION,
    'return_to_sender': ShipmentStatus.RETURNED_TO_SENDER,
    'returned': ShipmentStatus.RETURNED_TO_SENDER,
}

# Clocks on carrier systems drift a little; anything later than this is bad data.
FUTURE_TOLERANCE = timedelta(minutes=5)


class TrackingImporter(BaseImporter):
    """Imports carrier tracking events: one row per event.

    The first event for a tracking number creates the Shipment. Rows can come
    in any order: after the import, each touched shipment takes its status
    from its newest event (Shipment.sync_from_latest_event).
    """

    kind = ImportKind.TRACKING
    required_columns = ('order', 'carrier', 'tracking number', 'status', 'event time')
    column_aliases = {
        'order': ('order name', 'order number', 'name'),
        'tracking number': ('tracking_number', 'tracking', 'tracking no'),
        'event time': ('occurred at', 'event_time', 'timestamp', 'date'),
        'event location': ('location', 'city'),
        'expected delivery': ('expected delivery date', 'estimated delivery', 'eta'),
    }

    def process(self, rows):
        self.now = timezone.now()
        self.touched = set()

        for line, row in rows:
            self.log.rows_total += 1
            record = clean(row.get('tracking number'))
            try:
                with transaction.atomic():
                    created = self.save_row(row)
            except ValueError as error:
                self.log.add_error(line, str(error), record=record)
                continue
            if created:
                self.log.rows_created += 1
            else:
                self.log.rows_updated += 1

        for shipment in Shipment.objects.filter(pk__in=self.touched):
            shipment.sync_from_latest_event()

    def save_row(self, row):
        order_name = clean(row.get('order'))
        order = Order.objects.filter(name=order_name).first()
        if order is None:
            raise ValueError(f"Order: no order named '{order_name}'")

        carrier = parse_choice(row.get('carrier'), Carrier, 'Carrier')
        tracking_number = clean(row.get('tracking number')).upper().replace(' ', '')
        if not tracking_number:
            raise ValueError('Tracking number is empty')

        status = clean(row.get('status')).lower().replace(' ', '_').replace('-', '_')
        status = parse_choice(STATUS_ALIASES.get(status, status), ShipmentStatus, 'Status')

        occurred_at = parse_datetime(row.get('event time'), 'Event time')
        if occurred_at is None:
            raise ValueError('Event time is required')
        if occurred_at > self.now + FUTURE_TOLERANCE:
            raise ValueError(f'Event time {occurred_at:%Y-%m-%d %H:%M} is in the future')

        shipment = self.shipment(order, carrier, tracking_number, row, occurred_at)
        _, created = TrackingEvent.objects.update_or_create(
            shipment=shipment,
            occurred_at=occurred_at,
            status=status,
            defaults={
                'description': clean(row.get('description')),
                'location': clean(row.get('event location')),
            },
        )
        self.touched.add(shipment.pk)
        return created

    def shipment(self, order, carrier, tracking_number, row, occurred_at):
        expected = parse_date(row.get('expected delivery'), 'Expected delivery')
        shipment = Shipment.objects.filter(carrier=carrier, tracking_number=tracking_number).first()
        if shipment is None:
            return Shipment.objects.create(
                order=order,
                carrier=carrier,
                tracking_number=tracking_number,
                shipped_at=parse_datetime(row.get('shipped at'), 'Shipped at') or occurred_at,
                expected_delivery_date=expected,
            )
        if shipment.order_id != order.pk:
            raise ValueError(
                f'Tracking number already belongs to order {shipment.order.name}, not {order.name}'
            )
        if expected and expected != shipment.expected_delivery_date:
            # Carriers revise the estimate; keep the latest one.
            shipment.expected_delivery_date = expected
            shipment.save(update_fields=['expected_delivery_date', 'updated_at'])
        return shipment

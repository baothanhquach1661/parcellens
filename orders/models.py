from django.db import models
from django.db.models import Q

from core.models import TimeStampedModel, choices_constraint
from inventory.models import Location


class FinancialStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    AUTHORIZED = 'authorized', 'Authorized'
    PARTIALLY_PAID = 'partially_paid', 'Partially paid'
    PAID = 'paid', 'Paid'
    PARTIALLY_REFUNDED = 'partially_refunded', 'Partially refunded'
    REFUNDED = 'refunded', 'Refunded'
    VOIDED = 'voided', 'Voided'


class FulfillmentStatus(models.TextChoices):
    UNFULFILLED = 'unfulfilled', 'Unfulfilled'
    PARTIAL = 'partial', 'Partially fulfilled'
    FULFILLED = 'fulfilled', 'Fulfilled'


class Carrier(models.TextChoices):
    UPS = 'ups', 'UPS'
    USPS = 'usps', 'USPS'
    FEDEX = 'fedex', 'FedEx'
    DHL = 'dhl', 'DHL'
    OTHER = 'other', 'Other'


class ShipmentStatus(models.TextChoices):
    LABEL_CREATED = 'label_created', 'Label created'
    IN_TRANSIT = 'in_transit', 'In transit'
    OUT_FOR_DELIVERY = 'out_for_delivery', 'Out for delivery'
    DELIVERED = 'delivered', 'Delivered'
    EXCEPTION = 'exception', 'Exception'
    RETURNED_TO_SENDER = 'returned_to_sender', 'Returned to sender'


class Order(TimeStampedModel):
    """A customer order, imported from a Shopify-style CSV export."""

    # Shopify's order name, e.g. "#1001". Re-imports update the row with the same name.
    name = models.CharField(max_length=32, unique=True)
    fulfillment_location = models.ForeignKey(
        Location,
        on_delete=models.PROTECT,
        related_name='orders',
        help_text='Warehouse that ships this order.',
    )
    email = models.EmailField(blank=True)
    financial_status = models.CharField(max_length=20, choices=FinancialStatus.choices)
    fulfillment_status = models.CharField(
        max_length=20,
        choices=FulfillmentStatus.choices,
        default=FulfillmentStatus.UNFULFILLED,
    )

    # Source times from the imported file (stored in UTC), not ShipRadar's own
    # created_at / updated_at.
    placed_at = models.DateTimeField()
    paid_at = models.DateTimeField(null=True, blank=True)
    fulfilled_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Cancelled orders are ignored by every rule.',
    )

    currency = models.CharField(max_length=3, default='USD')
    total_price = models.DecimalField(max_digits=12, decimal_places=2)
    shipping_method = models.CharField(max_length=100, blank=True)

    # Shipping address, flat like the Shopify export. Empty text means "missing".
    ship_name = models.CharField(max_length=255, blank=True)
    ship_address1 = models.CharField(max_length=255, blank=True)
    ship_address2 = models.CharField(max_length=255, blank=True)
    ship_city = models.CharField(max_length=100, blank=True)
    ship_province = models.CharField(max_length=50, blank=True)
    # Text, not a number: "02108" must keep its leading zero.
    ship_zip = models.CharField(max_length=20, blank=True)
    ship_country = models.CharField(max_length=2, blank=True, help_text='ISO code, e.g. US.')

    class Meta:
        ordering = ['-placed_at']
        indexes = [
            # The overdue rule looks for paid orders that are still unfulfilled.
            models.Index(
                fields=['fulfillment_status', 'financial_status'],
                name='order_status_idx',
            ),
        ]
        constraints = [
            choices_constraint('financial_status', FinancialStatus, 'order_financial_status_valid'),
            choices_constraint('fulfillment_status', FulfillmentStatus, 'order_fulfillment_status_valid'),
            models.CheckConstraint(condition=Q(total_price__gte=0), name='order_total_price_non_negative'),
        ]

    def __str__(self):
        return self.name

    @property
    def is_cancelled(self):
        return self.cancelled_at is not None


class OrderItem(TimeStampedModel):
    """One line on an order."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    # Matched to InventoryItem.sku by text, not by foreign key, so an order
    # with an unknown SKU can still be imported and flagged (data model, decision 2).
    sku = models.CharField(max_length=64, db_index=True)
    title = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gte=1), name='order_item_quantity_positive'),
            models.CheckConstraint(condition=Q(unit_price__gte=0), name='order_item_unit_price_non_negative'),
        ]

    def __str__(self):
        return f'{self.quantity} × {self.sku}'


class Shipment(TimeStampedModel):
    """One package sent for an order, identified by its tracking number."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='shipments')
    carrier = models.CharField(max_length=10, choices=Carrier.choices)
    tracking_number = models.CharField(max_length=64)
    shipped_at = models.DateTimeField()
    expected_delivery_date = models.DateField(null=True, blank=True)

    # Copied from the latest TrackingEvent by sync_from_latest_event(),
    # so rules can read one row instead of scanning every event.
    status = models.CharField(
        max_length=20,
        choices=ShipmentStatus.choices,
        default=ShipmentStatus.LABEL_CREATED,
    )
    last_event_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-shipped_at']
        indexes = [
            # The stale tracking rule: in-transit shipments with an old last event.
            models.Index(fields=['status', 'last_event_at'], name='shipment_status_last_event_idx'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['carrier', 'tracking_number'],
                name='shipment_unique_carrier_tracking',
            ),
            choices_constraint('carrier', Carrier, 'shipment_carrier_valid'),
            choices_constraint('status', ShipmentStatus, 'shipment_status_valid'),
        ]

    def __str__(self):
        return f'{self.get_carrier_display()} {self.tracking_number}'

    def sync_from_latest_event(self):
        """Copy status and times from the newest tracking event.

        Uses the event time, not the import order: carrier feeds can deliver
        an older event after a newer one.
        """
        latest = self.events.order_by('-occurred_at', '-id').first()
        if latest is None:
            return
        self.status = latest.status
        self.last_event_at = latest.occurred_at
        self.delivered_at = (
            latest.occurred_at if latest.status == ShipmentStatus.DELIVERED else None
        )
        self.save(update_fields=['status', 'last_event_at', 'delivered_at', 'updated_at'])


class TrackingEvent(TimeStampedModel):
    """A status update from the carrier for one shipment."""

    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE, related_name='events')
    status = models.CharField(max_length=20, choices=ShipmentStatus.choices)
    description = models.CharField(max_length=255, blank=True)
    # Where the event happened (free text from the carrier), not an inventory Location.
    location = models.CharField(max_length=100, blank=True)
    occurred_at = models.DateTimeField()

    class Meta:
        ordering = ['occurred_at']
        constraints = [
            # Re-importing the same tracking file adds nothing twice.
            models.UniqueConstraint(
                fields=['shipment', 'occurred_at', 'status'],
                name='tracking_event_unique',
            ),
            choices_constraint('status', ShipmentStatus, 'tracking_event_status_valid'),
        ]

    def __str__(self):
        return f'{self.get_status_display()} at {self.occurred_at:%Y-%m-%d %H:%M}'

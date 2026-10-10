"""Counts shown next to sidebar items in the admin (Unfold "badge" callbacks).

Each function receives the request and returns a number, or None to hide the badge.
They run on every admin page, so each is a single COUNT query on indexed columns.
"""

from .models import FinancialStatus, FulfillmentStatus, Order, Shipment, ShipmentStatus


def orders_to_ship(request):
    """Paid, not cancelled, not fully fulfilled: the warehouse still has work to do."""
    count = Order.objects.filter(
        financial_status=FinancialStatus.PAID,
        fulfillment_status__in=[FulfillmentStatus.UNFULFILLED, FulfillmentStatus.PARTIAL],
        cancelled_at__isnull=True,
    ).count()
    return count or None


def shipment_problems(request):
    """Packages the carrier reported as failed or sent back."""
    count = Shipment.objects.filter(
        status__in=[ShipmentStatus.EXCEPTION, ShipmentStatus.RETURNED_TO_SENDER],
    ).count()
    return count or None

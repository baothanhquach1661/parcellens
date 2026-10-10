from django.db import transaction

from inventory.models import Location
from orders.models import FinancialStatus, FulfillmentStatus, Order, OrderItem

from ..models import ImportKind
from ..parsing import clean, parse_choice, parse_datetime, parse_decimal, parse_positive_int
from .base import BaseImporter, ImportFileError, RowError


class OrdersImporter(BaseImporter):
    """Imports a Shopify orders export.

    An order with several line items spans several rows that share the same
    "Name"; order-level columns are only filled on the first of those rows.
    Re-importing a file updates existing orders (matched by Name) and replaces
    their line items, so running the same file twice changes nothing.

    Shopify's "Location" column is the point-of-sale location, not the
    warehouse. ShipRadar reads an optional "Fulfillment Location" column
    (a Location code) and falls back to the default location.
    """

    kind = ImportKind.ORDERS
    required_columns = (
        'name', 'financial status', 'created at', 'total',
        'lineitem quantity', 'lineitem name', 'lineitem price', 'lineitem sku',
    )

    def process(self, rows):
        self.locations = {location.code.upper(): location for location in Location.objects.all()}
        self.default_location = next((loc for loc in self.locations.values() if loc.is_default), None)
        if self.default_location is None:
            raise ImportFileError('No default location is set. Mark one location as default first.')

        for name, group in self.group_by_order(rows):
            self.log.rows_total += 1
            first_line = group[0][0]
            try:
                with transaction.atomic():  # One bad order never leaves half its rows behind.
                    created = self.save_order(name, group)
            except ValueError as error:
                # RowError knows the exact line; other errors come from the order's first row.
                self.log.add_error(getattr(error, 'line', first_line), str(error), record=name)
                continue
            if created:
                self.log.rows_created += 1
            else:
                self.log.rows_updated += 1

    @staticmethod
    def group_by_order(rows):
        """Yield (order name, [(line, row), ...]) keeping the file's order."""
        groups = {}
        for line, row in rows:
            groups.setdefault(clean(row.get('name')), []).append((line, row))
        return groups.items()

    def save_order(self, name, group):
        if not name:
            raise ValueError('Name is empty')
        first = group[0][1]
        values = self.order_values(first)
        order, created = Order.objects.update_or_create(name=name, defaults=values)
        order.items.all().delete()
        OrderItem.objects.bulk_create([self.item(order, line, row) for line, row in group])
        return created

    def order_values(self, row):
        placed_at = parse_datetime(row.get('created at'), 'Created at')
        if placed_at is None:
            raise ValueError('Created at is required on the first row of an order')
        return {
            'fulfillment_location': self.location(row),
            'email': clean(row.get('email')),
            'financial_status': parse_choice(row.get('financial status'), FinancialStatus, 'Financial Status'),
            'fulfillment_status': parse_choice(
                row.get('fulfillment status'), FulfillmentStatus, 'Fulfillment Status',
                default=FulfillmentStatus.UNFULFILLED,
            ),
            'placed_at': placed_at,
            'paid_at': parse_datetime(row.get('paid at'), 'Paid at'),
            'fulfilled_at': parse_datetime(row.get('fulfilled at'), 'Fulfilled at'),
            # Shopify spells it "Canceled at"; accept both.
            'cancelled_at': parse_datetime(row.get('canceled at') or row.get('cancelled at'), 'Canceled at'),
            'currency': clean(row.get('currency')).upper() or 'USD',
            'total_price': parse_decimal(row.get('total'), 'Total'),
            'shipping_method': clean(row.get('shipping method')),
            # Addresses are stored as they are, even when they look wrong:
            # flagging them is the suspicious_address rule's job, not the importer's.
            'ship_name': clean(row.get('shipping name')),
            'ship_address1': clean(row.get('shipping address1')),
            'ship_address2': clean(row.get('shipping address2')),
            'ship_city': clean(row.get('shipping city')),
            'ship_province': clean(row.get('shipping province')),
            'ship_zip': clean(row.get('shipping zip')).lstrip("'"),  # Excel's "keep as text" quote.
            'ship_country': clean(row.get('shipping country')).upper()[:2],
        }

    def location(self, row):
        code = clean(row.get('fulfillment location')).upper()
        if not code:
            return self.default_location
        if code not in self.locations:
            raise ValueError(f"Fulfillment Location: unknown location code '{code}'")
        return self.locations[code]

    @staticmethod
    def item(order, line, row):
        try:
            return OrderItem(
                order=order,
                sku=clean(row.get('lineitem sku')),
                title=clean(row.get('lineitem name')),
                quantity=parse_positive_int(row.get('lineitem quantity'), 'Lineitem quantity'),
                unit_price=parse_decimal(row.get('lineitem price'), 'Lineitem price'),
            )
        except ValueError as error:
            raise RowError(line, str(error)) from None

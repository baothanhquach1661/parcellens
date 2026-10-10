from django.db import transaction

from inventory.models import InventoryItem, InventoryLevel, Location

from ..models import ImportKind
from ..parsing import clean, parse_datetime, parse_non_negative_int
from .base import BaseImporter


class InventoryImporter(BaseImporter):
    """Imports stock counts: one row per SKU per location.

    Accepts ShipRadar's simple format (sku, name, location, on_hand, counted_at)
    and the column names of Shopify's inventory export ("Title", "On hand (current)").
    SKUs that are not in the file keep their current stock, so a partial file is safe.
    """

    kind = ImportKind.INVENTORY
    required_columns = ('sku', 'location', 'on hand')
    column_aliases = {
        'name': ('title', 'product', 'product name'),
        'on hand': ('on hand (current)', 'on_hand', 'onhand', 'quantity'),
        'counted at': ('counted_at', 'as of'),
    }

    def process(self, rows):
        self.locations = {}
        for location in Location.objects.all():
            # Match either the code ("LA") or the name Shopify exports ("Los Angeles warehouse").
            self.locations[location.code.lower()] = location
            self.locations[location.name.lower()] = location
        self.seen = {}

        for line, row in rows:
            self.log.rows_total += 1
            sku = clean(row.get('sku'))
            try:
                with transaction.atomic():
                    created = self.save_row(line, row, sku)
            except ValueError as error:
                self.log.add_error(line, str(error), record=sku)
                continue
            if created:
                self.log.rows_created += 1
            else:
                self.log.rows_updated += 1

    def save_row(self, line, row, sku):
        if not sku:
            raise ValueError('SKU is empty')
        location_text = clean(row.get('location'))
        location = self.locations.get(location_text.lower())
        if location is None:
            raise ValueError(f"Location: unknown location '{location_text}'")

        key = (sku, location.pk)
        if key in self.seen:
            raise ValueError(f'Duplicate of line {self.seen[key]} (same SKU and location)')
        self.seen[key] = line

        try:
            on_hand = parse_non_negative_int(row.get('on hand'), 'On hand')
        except ValueError as error:
            if '-' in clean(row.get('on hand')):
                # Shopify allows negative stock; ShipRadar needs a real count.
                raise ValueError(f'{error}. Negative stock usually means a counting error') from None
            raise
        counted_at = parse_datetime(row.get('counted at'), 'Counted at') or self.log.started_at

        name = clean(row.get('name'))
        item, _ = InventoryItem.objects.get_or_create(sku=sku, defaults={'name': name or sku})
        if name and item.name != name:
            item.name = name
            item.save(update_fields=['name', 'updated_at'])

        _, created = InventoryLevel.objects.update_or_create(
            item=item,
            location=location,
            defaults={'on_hand': on_hand, 'counted_at': counted_at},
        )
        return created

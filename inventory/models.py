from django.db import models
from django.db.models import Q

from core.models import TimeStampedModel


class Location(TimeStampedModel):
    """A warehouse that stocks items and ships orders."""

    code = models.CharField(
        max_length=20,
        unique=True,
        help_text='Short code, e.g. LA or NJ.',
    )
    name = models.CharField(max_length=100)
    is_default = models.BooleanField(
        default=False,
        help_text='Used for imported orders that do not name a location.',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['code']
        constraints = [
            # At most one default location: a unique index that only covers
            # rows where is_default is true (PostgreSQL partial index).
            models.UniqueConstraint(
                fields=['is_default'],
                condition=Q(is_default=True),
                name='inventory_location_single_default',
                violation_error_message='Another location is already the default.',
            ),
        ]

    def __str__(self):
        return f'{self.code} – {self.name}'


class InventoryItem(TimeStampedModel):
    """A SKU in the catalog. Stock per location lives in InventoryLevel."""

    sku = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=255)

    class Meta:
        ordering = ['sku']

    def __str__(self):
        return self.sku


class InventoryLevel(TimeStampedModel):
    """Units of one SKU physically on hand at one location."""

    item = models.ForeignKey(
        InventoryItem,
        on_delete=models.CASCADE,
        related_name='levels',
    )
    location = models.ForeignKey(
        Location,
        # A location with stock history cannot be deleted; deactivate it.
        on_delete=models.PROTECT,
        related_name='inventory_levels',
    )
    # PositiveIntegerField also adds CHECK (on_hand >= 0) in PostgreSQL.
    on_hand = models.PositiveIntegerField(default=0)
    counted_at = models.DateTimeField(
        help_text='When this stock level was true, from the inventory file.',
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['item', 'location'],
                name='inventory_level_unique_item_location',
            ),
        ]

    def __str__(self):
        return f'{self.item.sku} @ {self.location.code}: {self.on_hand}'

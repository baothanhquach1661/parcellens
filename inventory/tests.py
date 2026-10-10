from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from .models import InventoryItem, InventoryLevel, Location


class LocationConstraintTests(TestCase):
    def test_only_one_default_location(self):
        Location.objects.create(code='LA', name='Los Angeles', is_default=True)

        with self.assertRaises(IntegrityError), transaction.atomic():
            Location.objects.create(code='NJ', name='New Jersey', is_default=True)

    def test_many_non_default_locations_are_allowed(self):
        Location.objects.create(code='LA', name='Los Angeles', is_default=True)
        Location.objects.create(code='NJ', name='New Jersey')
        Location.objects.create(code='TX', name='Dallas')

        self.assertEqual(Location.objects.count(), 3)


class InventoryLevelConstraintTests(TestCase):
    def setUp(self):
        self.location = Location.objects.create(code='LA', name='Los Angeles')
        self.item = InventoryItem.objects.create(sku='GEL-102', name='Gel polish 102')

    def test_one_level_per_item_and_location(self):
        InventoryLevel.objects.create(
            item=self.item, location=self.location, on_hand=5, counted_at=timezone.now(),
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            InventoryLevel.objects.create(
                item=self.item, location=self.location, on_hand=3, counted_at=timezone.now(),
            )

    def test_on_hand_cannot_be_negative(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            InventoryLevel.objects.create(
                item=self.item, location=self.location, on_hand=-1, counted_at=timezone.now(),
            )

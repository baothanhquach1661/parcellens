from django.contrib import admin
from django.db.models import Sum
from unfold.admin import ModelAdmin, TabularInline

from .models import InventoryItem, InventoryLevel, Location


@admin.register(Location)
class LocationAdmin(ModelAdmin):
    list_display = ('code', 'name', 'is_default', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('code', 'name')


class InventoryLevelInline(TabularInline):
    model = InventoryLevel
    extra = 0
    fields = ('location', 'on_hand', 'counted_at')


@admin.register(InventoryItem)
class InventoryItemAdmin(ModelAdmin):
    list_display = ('sku', 'name', 'total_on_hand')
    search_fields = ('sku', 'name')
    inlines = [InventoryLevelInline]

    def get_queryset(self, request):
        # One query with SUM ... GROUP BY instead of one query per row.
        # order_by again: Django ignores Meta.ordering in GROUP BY queries.
        return (
            super()
            .get_queryset(request)
            .annotate(_total_on_hand=Sum('levels__on_hand'))
            .order_by('sku')
        )

    @admin.display(description='Total on hand', ordering='_total_on_hand')
    def total_on_hand(self, obj):
        return obj._total_on_hand or 0


@admin.register(InventoryLevel)
class InventoryLevelAdmin(ModelAdmin):
    list_display = ('item', 'location', 'on_hand', 'counted_at')
    list_filter = ('location',)
    search_fields = ('item__sku', 'item__name')
    # __str__ uses item and location; load them in the same query (no N+1).
    list_select_related = ('item', 'location')
    autocomplete_fields = ('item',)

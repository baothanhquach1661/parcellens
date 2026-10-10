from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display

from .models import (
    FinancialStatus,
    FulfillmentStatus,
    Order,
    OrderItem,
    Shipment,
    ShipmentStatus,
    TrackingEvent,
)

# Badge colours for status columns (Unfold label variants).
FINANCIAL_STATUS_COLORS = {
    FinancialStatus.PAID: 'success',
    FinancialStatus.PENDING: 'warning',
    FinancialStatus.AUTHORIZED: 'warning',
    FinancialStatus.PARTIALLY_PAID: 'warning',
    FinancialStatus.PARTIALLY_REFUNDED: 'info',
    FinancialStatus.REFUNDED: 'info',
}
FULFILLMENT_STATUS_COLORS = {
    FulfillmentStatus.UNFULFILLED: 'warning',
    FulfillmentStatus.PARTIAL: 'info',
    FulfillmentStatus.FULFILLED: 'success',
}
SHIPMENT_STATUS_COLORS = {
    ShipmentStatus.LABEL_CREATED: 'info',
    ShipmentStatus.IN_TRANSIT: 'info',
    ShipmentStatus.OUT_FOR_DELIVERY: 'info',
    ShipmentStatus.DELIVERED: 'success',
    ShipmentStatus.EXCEPTION: 'danger',
    ShipmentStatus.RETURNED_TO_SENDER: 'danger',
}


class OrderItemInline(TabularInline):
    model = OrderItem
    extra = 0
    fields = ('sku', 'title', 'quantity', 'unit_price')


class ShipmentInline(TabularInline):
    model = Shipment
    extra = 0
    fields = ('carrier', 'tracking_number', 'shipped_at', 'status', 'last_event_at')
    readonly_fields = ('status', 'last_event_at')
    show_change_link = True


@admin.register(Order)
class OrderAdmin(ModelAdmin):
    list_display = (
        'name',
        'placed_at',
        'financial_status_badge',
        'fulfillment_status_badge',
        'fulfillment_location',
        'total_price',
    )
    list_filter = ('financial_status', 'fulfillment_status', 'fulfillment_location')
    search_fields = ('name', 'email', 'ship_name')
    date_hierarchy = 'placed_at'
    list_select_related = ('fulfillment_location',)
    readonly_fields = ('created_at', 'updated_at')
    inlines = [OrderItemInline, ShipmentInline]
    fieldsets = (
        (None, {'fields': ('name', 'email', 'fulfillment_location', 'total_price', 'currency')}),
        ('Status', {'fields': ('financial_status', 'fulfillment_status', 'shipping_method')}),
        ('Source times', {'fields': ('placed_at', 'paid_at', 'fulfilled_at', 'cancelled_at')}),
        ('Shipping address', {'fields': (
            'ship_name', 'ship_address1', 'ship_address2',
            'ship_city', 'ship_province', 'ship_zip', 'ship_country',
        )}),
        ('ShipRadar', {'fields': ('created_at', 'updated_at')}),
    )

    @display(description='Payment', ordering='financial_status', label=FINANCIAL_STATUS_COLORS)
    def financial_status_badge(self, obj):
        return obj.financial_status, obj.get_financial_status_display()

    @display(description='Fulfillment', ordering='fulfillment_status', label=FULFILLMENT_STATUS_COLORS)
    def fulfillment_status_badge(self, obj):
        return obj.fulfillment_status, obj.get_fulfillment_status_display()


class TrackingEventInline(TabularInline):
    model = TrackingEvent
    extra = 0
    fields = ('occurred_at', 'status', 'description', 'location')


@admin.register(Shipment)
class ShipmentAdmin(ModelAdmin):
    list_display = (
        'tracking_number',
        'carrier',
        'order',
        'status_badge',
        'last_event_at',
        'expected_delivery_date',
    )
    list_filter = ('carrier', 'status')
    search_fields = ('tracking_number', 'order__name')
    list_select_related = ('order',)
    autocomplete_fields = ('order',)
    readonly_fields = ('status', 'last_event_at', 'delivered_at', 'created_at', 'updated_at')
    inlines = [TrackingEventInline]

    @display(description='Status', ordering='status', label=SHIPMENT_STATUS_COLORS)
    def status_badge(self, obj):
        return obj.status, obj.get_status_display()

    def save_related(self, request, form, formsets, change):
        # Events edited in the inline are saved here; refresh the copied fields after.
        super().save_related(request, form, formsets, change)
        form.instance.sync_from_latest_event()

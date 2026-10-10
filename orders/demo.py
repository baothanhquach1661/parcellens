"""Demo data for ShipRadar: locations, inventory and Shopify-like orders.

About 15% of the orders are built on purpose to break one ShipRadar rule.
The summary printed by `manage.py seed_demo` lists them, so the rules engine
(week 2) has a known answer to check against.

Everything is fake (Faker). No real customer data is ever used.
"""

import random
from collections import Counter
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from faker import Faker

from inventory.models import InventoryItem, InventoryLevel, Location

from .models import (
    Carrier,
    FinancialStatus,
    FulfillmentStatus,
    Order,
    OrderItem,
    Shipment,
    ShipmentStatus,
    TrackingEvent,
)

# Scenario -> (share of all orders, rule that should flag it in week 2).
# "delivered" takes whatever is left so the shares always add up to 100%.
SCENARIOS = {
    'in_transit': (0.12, None),
    'unfulfilled_fresh': (0.06, None),
    'pending_payment': (0.03, None),
    'cancelled': (0.02, None),
    'overdue_unfulfilled': (0.03, 'overdue_unfulfilled'),
    'stockout': (0.02, 'stockout'),
    'missing_tracking': (0.02, 'missing_tracking'),
    'stale_tracking': (0.025, 'stale_tracking'),
    'delivery_exception': (0.025, 'delivery_exception'),
    'late_delivery': (0.025, 'late_delivery'),
    'suspicious_address': (0.02, 'suspicious_address'),
}
DELIVERED = 'delivered'

# SKUs the stockout scenario uses. They are almost empty at LA but stocked
# at NJ, so the issue can say "available elsewhere".
SCARCE_SKUS = {'GEL-118': 2, 'ACR-POW-NUDE': 1, 'TOP-NOWIPE': 2}
UNKNOWN_SKU = 'GEL-999'  # On some stockout orders; not in inventory at all.

CATALOG = [
    *[(f'GEL-{n}', f'Gel Polish Shade {n}', '9.95') for n in range(101, 121)],
    ('BASE-RUBBER', 'Rubber Base Coat 15ml', '12.50'),
    ('TOP-NOWIPE', 'No-Wipe Top Coat 15ml', '12.50'),
    ('ACR-POW-CLEAR', 'Acrylic Powder Clear 2oz', '18.00'),
    ('ACR-POW-NUDE', 'Acrylic Powder Nude 2oz', '18.00'),
    ('ACR-LIQ-8OZ', 'Acrylic Liquid Monomer 8oz', '24.00'),
    ('FILE-100-180', 'Nail File 100/180 (50 pack)', '15.00'),
    ('BUFF-4WAY', '4-Way Buffer Block (20 pack)', '11.00'),
    ('TIPS-COFFIN-500', 'Coffin Nail Tips (500)', '14.00'),
    ('DRILL-BIT-CB', 'Carbide Drill Bit Barrel', '16.50'),
    ('LAMP-UVLED-48W', 'UV/LED Nail Lamp 48W', '45.00'),
    ('CUTI-OIL-15', 'Cuticle Oil 15ml', '6.50'),
    ('DIP-SET-STARTER', 'Dip Powder Starter Kit', '39.00'),
    ('BRUSH-OVAL-8', 'Oval Acrylic Brush #8', '22.00'),
    ('PRIMER-ACID-FREE', 'Acid-Free Primer 15ml', '9.00'),
    ('REMOVER-1L', 'Gel Remover 1L', '13.50'),
]

CARRIER_SHARE = [(Carrier.USPS, 40), (Carrier.UPS, 35), (Carrier.FEDEX, 20), (Carrier.DHL, 5)]
HUBS = ['Ontario, CA', 'Phoenix, AZ', 'Dallas, TX', 'Memphis, TN', 'Louisville, KY', 'Secaucus, NJ']
EXCEPTION_EVENTS = [
    (ShipmentStatus.EXCEPTION, 'Delivery attempted - no access to building'),
    (ShipmentStatus.EXCEPTION, 'Address information incomplete'),
    (ShipmentStatus.EXCEPTION, 'Package damaged in transit'),
    (ShipmentStatus.RETURNED_TO_SENDER, 'Returned to sender - refused by recipient'),
]


@dataclass
class SeedSummary:
    locations: int = 0
    items: int = 0
    levels: int = 0
    orders: int = 0
    order_items: int = 0
    shipments: int = 0
    events: int = 0
    scenarios: Counter = field(default_factory=Counter)


class DemoDataBuilder:
    def __init__(self, order_count=500, seed=42, now=None):
        self.order_count = order_count
        self.rng = random.Random(seed)
        self.fake = Faker('en_US')
        self.fake.seed_instance(seed)
        # One minute in the past, so no generated time is ever in the future.
        self.now = (now or timezone.now()) - timedelta(minutes=1)
        self.tracking_numbers = set()
        self.summary = SeedSummary()

    # ----- public API -------------------------------------------------------

    @transaction.atomic
    def build(self):
        la, nj = self._create_locations()
        self._create_inventory(la, nj)
        orders = self._plan_orders()
        self._save_orders(orders, la, nj)
        return self.summary

    # ----- inventory --------------------------------------------------------

    def _create_locations(self):
        la = Location.objects.create(code='LA', name='Los Angeles warehouse', is_default=True)
        nj = Location.objects.create(code='NJ', name='New Jersey warehouse')
        self.summary.locations = 2
        return la, nj

    def _create_inventory(self, la, nj):
        items = InventoryItem.objects.bulk_create(
            [InventoryItem(sku=sku, name=name) for sku, name, _ in CATALOG]
        )
        counted_at = self.now - timedelta(hours=2)
        levels = []
        for item in items:
            if item.sku in SCARCE_SKUS:
                la_qty, nj_qty = SCARCE_SKUS[item.sku], self.rng.randint(15, 40)
            else:
                la_qty, nj_qty = self.rng.randint(60, 300), self.rng.randint(40, 200)
            levels.append(InventoryLevel(item=item, location=la, on_hand=la_qty, counted_at=counted_at))
            levels.append(InventoryLevel(item=item, location=nj, on_hand=nj_qty, counted_at=counted_at))
        InventoryLevel.objects.bulk_create(levels)
        self.summary.items = len(items)
        self.summary.levels = len(levels)

    # ----- orders -------------------------------------------------------

    def _scenario_list(self):
        counts = {name: round(share * self.order_count) for name, (share, _) in SCENARIOS.items()}
        counts[DELIVERED] = self.order_count - sum(counts.values())
        scenarios = [name for name, count in counts.items() for _ in range(count)]
        self.rng.shuffle(scenarios)
        return scenarios

    def _plan_orders(self):
        plans = [self._plan(scenario, index) for index, scenario in enumerate(self._scenario_list())]
        # Shopify order names grow with time, so number them in placed_at order.
        plans.sort(key=lambda plan: plan['order']['placed_at'])
        for number, plan in enumerate(plans, start=1001):
            plan['order']['name'] = f'#{number}'
        return plans

    def _plan(self, scenario, index):
        """Return a dict describing one order, its lines and its shipment."""
        self.summary.scenarios[scenario] += 1
        hours = self._hours_ago
        plan = {'scenario': scenario, 'order': self._customer(), 'lines': self._lines(), 'shipment': None}
        order = plan['order']
        order['financial_status'] = FinancialStatus.PAID
        order['fulfillment_status'] = FulfillmentStatus.UNFULFILLED
        order['location'] = 'LA' if self.rng.random() < 0.65 else 'NJ'

        if scenario == 'unfulfilled_fresh':
            self._placed(order, hours(1, 10))
        elif scenario == 'suspicious_address':
            self._placed(order, hours(1, 10))
            self._break_address(order)
        elif scenario == 'stockout':
            self._placed(order, hours(1, 20))
            order['location'] = 'LA'
            sku = UNKNOWN_SKU if index % 4 == 0 else self.rng.choice(sorted(SCARCE_SKUS))
            plan['lines'] = [self._line(sku, quantity=self.rng.randint(3, 5))] + plan['lines'][:1]
        elif scenario == 'pending_payment':
            self._placed(order, hours(24, 240))
            order['financial_status'] = FinancialStatus.PENDING
            order['paid_at'] = None
        elif scenario == 'cancelled':
            self._placed(order, hours(72, 360))
            order['financial_status'] = self.rng.choice([FinancialStatus.VOIDED, FinancialStatus.REFUNDED])
            order['cancelled_at'] = order['placed_at'] + timedelta(hours=self.rng.uniform(1, 20))
        elif scenario == 'overdue_unfulfilled':
            # At least 5 calendar days: always more than 2 business days, even over a weekend.
            self._placed(order, hours(120, 240))
        elif scenario == 'missing_tracking':
            self._placed(order, hours(72, 144))
            self._fulfilled(order, after_hours=(4, 20))
        else:
            plan['shipment'] = self._shipped_plan(scenario, order)
        return plan

    def _shipped_plan(self, scenario, order):
        """Orders that left the warehouse: delivered, in transit or in trouble."""
        hours = self._hours_ago
        if scenario == DELIVERED:
            self._placed(order, hours(120, 720))
        elif scenario == 'in_transit':
            self._placed(order, hours(30, 70))
        elif scenario == 'stale_tracking':
            self._placed(order, hours(200, 260))
        elif scenario == 'delivery_exception':
            self._placed(order, hours(60, 150))
        elif scenario == 'late_delivery':
            self._placed(order, hours(170, 230))
        self._fulfilled(order, after_hours=(4, 20))
        shipped_at = order['fulfilled_at']
        carrier = self._weighted(CARRIER_SHARE)
        shipment = {
            'carrier': carrier,
            'tracking_number': self._tracking_number(carrier),
            'shipped_at': shipped_at,
            'expected_delivery_date': (shipped_at + timedelta(days=4)).date(),
            'events': [(ShipmentStatus.LABEL_CREATED, 'Shipping label created', shipped_at)],
        }
        events = shipment['events']
        first_scan = shipped_at + timedelta(hours=self.rng.uniform(4, 10))
        events.append((ShipmentStatus.IN_TRANSIT, 'Departed origin facility', first_scan))
        destination = f"{order['ship_city']}, {order['ship_province']}"

        if scenario == DELIVERED:
            delivered = shipped_at + timedelta(hours=self.rng.uniform(40, 96))
            events.append((ShipmentStatus.OUT_FOR_DELIVERY, 'Out for delivery', delivered - timedelta(hours=5)))
            events.append((ShipmentStatus.DELIVERED, 'Delivered, front door', delivered, destination))
        elif scenario == 'in_transit':
            events.append((ShipmentStatus.IN_TRANSIT, 'Arrived at hub', self.now - timedelta(hours=self.rng.uniform(2, 20))))
        elif scenario == 'stale_tracking':
            # Last scan 4-7 days ago (rule: more than 3 days); estimate still in the future.
            events.append((ShipmentStatus.IN_TRANSIT, 'Arrived at hub', self.now - timedelta(days=self.rng.uniform(4, 7))))
            shipment['expected_delivery_date'] = (self.now + timedelta(days=2)).date()
        elif scenario == 'delivery_exception':
            status, text = self.rng.choice(EXCEPTION_EVENTS)
            events.append((status, text, self.now - timedelta(hours=self.rng.uniform(2, 30)), destination))
            shipment['expected_delivery_date'] = (self.now + timedelta(days=1)).date()
        elif scenario == 'late_delivery':
            # Past the expected date, still moving (scanned recently, so not stale).
            shipment['expected_delivery_date'] = (shipped_at + timedelta(days=3)).date()
            events.append((ShipmentStatus.IN_TRANSIT, 'In transit, running late', self.now - timedelta(hours=self.rng.uniform(4, 30))))

        order['fulfillment_status'] = FulfillmentStatus.FULFILLED
        return shipment

    # ----- small helpers ------------------------------------------------

    def _hours_ago(self, low, high):
        return self.now - timedelta(hours=self.rng.uniform(low, high))

    def _placed(self, order, placed_at):
        order['placed_at'] = placed_at
        if order['financial_status'] == FinancialStatus.PAID:
            order['paid_at'] = placed_at + timedelta(minutes=self.rng.uniform(0, 5))

    def _fulfilled(self, order, after_hours):
        order['fulfillment_status'] = FulfillmentStatus.FULFILLED
        fulfilled_at = order['placed_at'] + timedelta(hours=self.rng.uniform(*after_hours))
        order['fulfilled_at'] = min(fulfilled_at, self.now)

    def _customer(self):
        fake = self.fake
        state = fake.state_abbr(include_territories=False)
        return {
            'email': fake.safe_email(),
            'ship_name': fake.name(),
            'ship_address1': fake.street_address(),
            'ship_address2': fake.secondary_address() if self.rng.random() < 0.2 else '',
            'ship_city': fake.city(),
            'ship_province': state,
            'ship_zip': fake.zipcode_in_state(state),
            'ship_country': 'US',
            'shipping_method': self._weighted([('Standard', 70), ('Expedited', 20), ('Free shipping', 10)]),
            'paid_at': None,
            'fulfilled_at': None,
            'cancelled_at': None,
        }

    def _break_address(self, order):
        problem = self.rng.choice(['no_street', 'bad_zip', 'no_city'])
        if problem == 'no_street':
            order['ship_address1'] = ''
        elif problem == 'bad_zip':
            order['ship_zip'] = self.rng.choice(['9068', 'ABCDE', '906801'])
        else:
            order['ship_city'] = ''

    def _lines(self):
        regular = [sku for sku, _, _ in CATALOG if sku not in SCARCE_SKUS]
        skus = self.rng.sample(regular, k=self.rng.choice([1, 1, 2, 2, 3, 4]))
        return [self._line(sku, quantity=self.rng.choice([1, 1, 1, 2, 2, 3])) for sku in skus]

    def _line(self, sku, quantity):
        prices = {s: (name, price) for s, name, price in CATALOG}
        name, price = prices.get(sku, ('Gel Polish Shade 999 (discontinued)', '9.95'))
        return {'sku': sku, 'title': name, 'quantity': quantity, 'unit_price': Decimal(price)}

    def _weighted(self, options):
        values, weights = zip(*options)
        return self.rng.choices(values, weights=weights, k=1)[0]

    def _tracking_number(self, carrier):
        while True:
            if carrier == Carrier.UPS:
                number = '1Z' + ''.join(self.rng.choices('0123456789ABCDEFGHJKLMNPRSTUVWXYZ', k=16))
            elif carrier == Carrier.USPS:
                number = '9400' + ''.join(self.rng.choices('0123456789', k=18))
            elif carrier == Carrier.FEDEX:
                number = ''.join(self.rng.choices('0123456789', k=12))
            else:
                number = ''.join(self.rng.choices('0123456789', k=10))
            if (carrier, number) not in self.tracking_numbers:
                self.tracking_numbers.add((carrier, number))
                return number

    # ----- saving -------------------------------------------------------

    def _save_orders(self, plans, la, nj):
        locations = {'LA': la, 'NJ': nj}
        orders = []
        for plan in plans:
            data = dict(plan['order'])
            location = locations[data.pop('location')]
            lines = plan['lines']
            subtotal = sum(line['unit_price'] * line['quantity'] for line in lines)
            shipping = Decimal('0.00') if data['shipping_method'] == 'Free shipping' else Decimal('7.95')
            orders.append(Order(fulfillment_location=location, total_price=subtotal + shipping, **data))
        orders = Order.objects.bulk_create(orders)  # PostgreSQL returns the new ids.

        order_items, shipments, events_by_shipment = [], [], []
        for order, plan in zip(orders, plans):
            order_items += [OrderItem(order=order, **line) for line in plan['lines']]
            if plan['shipment']:
                data = dict(plan['shipment'])
                events_by_shipment.append(data.pop('events'))
                shipments.append(Shipment(order=order, **data))
        OrderItem.objects.bulk_create(order_items)
        shipments = Shipment.objects.bulk_create(shipments)

        events = []
        for shipment, planned in zip(shipments, events_by_shipment):
            for status, description, occurred_at, *where in planned:
                location = where[0] if where else self.rng.choice(HUBS)
                events.append(TrackingEvent(
                    shipment=shipment,
                    status=status,
                    description=description,
                    location=location,
                    occurred_at=min(occurred_at, self.now),
                ))
        TrackingEvent.objects.bulk_create(events)

        # Same code path the importer will use, so the copied fields stay correct.
        for shipment in shipments:
            shipment.sync_from_latest_event()

        self.summary.orders = len(orders)
        self.summary.order_items = len(order_items)
        self.summary.shipments = len(shipments)
        self.summary.events = len(events)

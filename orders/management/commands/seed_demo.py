from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from inventory.models import InventoryItem, Location
from orders.demo import DELIVERED, SCENARIOS, DemoDataBuilder
from orders.models import Order


class Command(BaseCommand):
    help = 'Fill the database with fake locations, inventory and orders for demos.'

    def add_arguments(self, parser):
        parser.add_argument('--orders', type=int, default=500, help='Number of orders (default 500).')
        parser.add_argument('--seed', type=int, default=42, help='Random seed, for repeatable data.')
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Delete all orders, inventory and locations first. Only allowed with DEBUG=True.',
        )

    def handle(self, *args, **options):
        if options['orders'] < 1:
            raise CommandError('--orders must be at least 1.')

        if options['reset']:
            if not settings.DEBUG:
                raise CommandError('--reset deletes data and is only allowed when DEBUG=True.')
            self._reset()
        elif Order.objects.exists() or Location.objects.exists():
            raise CommandError('The database already has data. Run again with --reset to replace it.')

        summary = DemoDataBuilder(order_count=options['orders'], seed=options['seed']).build()
        self._print_summary(summary)

    @transaction.atomic
    def _reset(self):
        Order.objects.all().delete()  # Cascades to items, shipments and events.
        InventoryItem.objects.all().delete()  # Cascades to inventory levels.
        Location.objects.all().delete()
        self.stdout.write('Deleted existing demo data.')

    def _print_summary(self, s):
        write = self.stdout.write
        write(self.style.SUCCESS(
            f'Created {s.locations} locations, {s.items} SKUs, {s.levels} stock levels, '
            f'{s.orders} orders, {s.order_items} order lines, {s.shipments} shipments, '
            f'{s.events} tracking events.'
        ))
        write('')
        write(f"{'Scenario':<22}{'Orders':>7}   Expected rule")
        problems = 0
        for name in [DELIVERED, *SCENARIOS]:
            rule = SCENARIOS.get(name, (0, None))[1]
            count = s.scenarios[name]
            if rule:
                problems += count
            write(f'{name:<22}{count:>7}   {rule or "-"}')
        write('')
        write(f'Orders built to break a rule: {problems} of {s.orders} ({problems / s.orders:.1%}).')

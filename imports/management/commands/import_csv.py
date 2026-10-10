from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from imports.importers import IMPORTERS
from imports.models import ImportStatus


class Command(BaseCommand):
    help = 'Import a CSV file (orders, inventory or tracking) and print what changed.'

    def add_arguments(self, parser):
        parser.add_argument('kind', choices=sorted(IMPORTERS), help='What the file contains.')
        parser.add_argument('path', help='Path to the CSV file.')
        parser.add_argument('--user', help='Username to record as the uploader.')

    def handle(self, *args, **options):
        path = Path(options['path'])
        if not path.is_file():
            raise CommandError(f'File not found: {path}')

        user = None
        if options['user']:
            try:
                user = get_user_model().objects.get(username=options['user'])
            except get_user_model().DoesNotExist:
                raise CommandError(f"No user named '{options['user']}'.") from None

        importer_class = IMPORTERS[options['kind']]
        with path.open('rb') as file:
            log = importer_class(file, file_name=path.name, user=user).run()

        style = self.style.SUCCESS if log.status == ImportStatus.SUCCEEDED and not log.rows_failed else self.style.WARNING
        self.stdout.write(style(
            f'{log}: {log.get_status_display().lower()}. '
            f'{log.rows_total} records, {log.rows_created} created, '
            f'{log.rows_updated} updated, {log.rows_failed} failed.'
        ))
        for error in log.errors[:20]:
            record = f" {error['record']}" if error['record'] else ''
            self.stdout.write(f"  line {error['row']}{record}: {error['message']}")
        if len(log.errors) > 20:
            self.stdout.write(f'  ... {len(log.errors) - 20} more in ImportLog #{log.pk}')
        if log.status == ImportStatus.FAILED:
            raise CommandError('Import failed.')

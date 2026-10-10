from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import TimeStampedModel, choices_constraint


class ImportKind(models.TextChoices):
    ORDERS = 'orders', 'Orders'
    INVENTORY = 'inventory', 'Inventory'
    TRACKING = 'tracking', 'Tracking'


class ImportStatus(models.TextChoices):
    RUNNING = 'running', 'Running'
    SUCCEEDED = 'succeeded', 'Succeeded'
    FAILED = 'failed', 'Failed'


class ImportLog(TimeStampedModel):
    """One CSV import: what was read, what changed and what went wrong.

    Counts are records: orders for an orders file (one order can span several
    CSV rows), rows for inventory and tracking files.
    """

    # Keep at most this many error entries; rows_failed still has the full count.
    MAX_ERRORS = 500

    kind = models.CharField(max_length=20, choices=ImportKind.choices)
    file_name = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=ImportStatus.choices, default=ImportStatus.RUNNING)
    rows_total = models.PositiveIntegerField(default=0)
    rows_created = models.PositiveIntegerField(default=0)
    rows_updated = models.PositiveIntegerField(default=0)
    rows_failed = models.PositiveIntegerField(default=0)
    # [{"row": 12, "record": "#1003", "message": "..."}], row = line number in the file.
    errors = models.JSONField(default=list, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='imports',
        help_text='Empty when the import ran from the command line.',
    )
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-started_at']
        constraints = [
            choices_constraint('kind', ImportKind, 'import_log_kind_valid'),
            choices_constraint('status', ImportStatus, 'import_log_status_valid'),
        ]

    def __str__(self):
        return f'{self.get_kind_display()} import of {self.file_name}'

    def add_error(self, row, message, record=''):
        self.rows_failed += 1
        if len(self.errors) < self.MAX_ERRORS:
            self.errors.append({'row': row, 'record': record, 'message': message})

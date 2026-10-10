from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from core.models import TimeStampedModel, choices_constraint
from orders.models import Order, Shipment


class RuleCode(models.TextChoices):
    OVERDUE_UNFULFILLED = 'overdue_unfulfilled', 'Overdue unfulfilled'
    STOCKOUT = 'stockout', 'Stockout'
    DELIVERY_EXCEPTION = 'delivery_exception', 'Delivery exception'
    MISSING_TRACKING = 'missing_tracking', 'Missing tracking'
    STALE_TRACKING = 'stale_tracking', 'Stale tracking'
    LATE_DELIVERY = 'late_delivery', 'Late delivery'
    SUSPICIOUS_ADDRESS = 'suspicious_address', 'Suspicious address'


# Rules about one package create one issue per shipment; the others one per order.
SHIPMENT_RULES = [RuleCode.DELIVERY_EXCEPTION, RuleCode.STALE_TRACKING, RuleCode.LATE_DELIVERY]


class Severity(models.IntegerChoices):
    """Stored as a number so "most urgent first" is a plain ORDER BY severity."""

    HIGH = 1, 'High'
    MEDIUM = 2, 'Medium'
    LOW = 3, 'Low'


class IssueStatus(models.TextChoices):
    OPEN = 'open', 'Open'
    ACKNOWLEDGED = 'acknowledged', 'Acknowledged'
    SNOOZED = 'snoozed', 'Snoozed'
    RESOLVED = 'resolved', 'Resolved'


# An issue in one of these states blocks a duplicate for the same order/shipment/rule.
ACTIVE_STATUSES = [IssueStatus.OPEN, IssueStatus.ACKNOWLEDGED, IssueStatus.SNOOZED]


class Resolution(models.TextChoices):
    AUTO = 'auto', 'Auto (problem cleared)'
    MANUAL = 'manual', 'Manual (closed by a person)'


class ThresholdUnit(models.TextChoices):
    HOURS = 'hours', 'Hours'
    DAYS = 'days', 'Days'
    BUSINESS_DAYS = 'business_days', 'Business days'


class IssueQuerySet(models.QuerySet):
    def active(self):
        return self.filter(status__in=ACTIVE_STATUSES)


class Issue(TimeStampedModel):
    """One problem found by a rule, from detection until it is resolved."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='issues')
    shipment = models.ForeignKey(
        Shipment,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='issues',
        help_text='Set for shipment-level rules, empty for order-level rules.',
    )
    rule_code = models.CharField(max_length=30, choices=RuleCode.choices)
    # Copied from the rule when the issue is created, so later setting changes
    # do not rewrite history.
    severity = models.PositiveSmallIntegerField(choices=Severity.choices)
    status = models.CharField(max_length=20, choices=IssueStatus.choices, default=IssueStatus.OPEN)
    snoozed_until = models.DateTimeField(null=True, blank=True)
    resolution = models.CharField(max_length=10, choices=Resolution.choices, blank=True)
    details = models.JSONField(default=dict, blank=True, help_text='Facts found by the rule.')

    first_detected_at = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(default=timezone.now)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='resolved_issues',
    )

    objects = IssueQuerySet.as_manager()

    class Meta:
        verbose_name = 'exception'
        ordering = ['severity', 'first_detected_at']
        indexes = [
            models.Index(fields=['status', 'severity'], name='issue_status_severity_idx'),
        ]
        constraints = [
            # Idempotent rules: at most one active issue per order (+ shipment) and rule.
            # nulls_distinct=False: order-level issues have shipment = NULL, and
            # PostgreSQL would otherwise treat every NULL as different.
            models.UniqueConstraint(
                fields=['order', 'shipment', 'rule_code'],
                condition=Q(status__in=ACTIVE_STATUSES),
                nulls_distinct=False,
                name='issue_one_active_per_target',
            ),
            choices_constraint('rule_code', RuleCode, 'issue_rule_code_valid'),
            choices_constraint('status', IssueStatus, 'issue_status_valid'),
            models.CheckConstraint(condition=Q(severity__in=Severity.values), name='issue_severity_valid'),
            models.CheckConstraint(
                condition=Q(resolution='') | Q(resolution__in=Resolution.values),
                name='issue_resolution_valid',
            ),
            # Shipment-level rules need a shipment; order-level rules must not have one.
            models.CheckConstraint(
                condition=(
                    Q(rule_code__in=SHIPMENT_RULES, shipment__isnull=False)
                    | (~Q(rule_code__in=SHIPMENT_RULES) & Q(shipment__isnull=True))
                ),
                name='issue_shipment_matches_rule',
            ),
            models.CheckConstraint(
                condition=~Q(status=IssueStatus.SNOOZED) | Q(snoozed_until__isnull=False),
                name='issue_snoozed_has_until',
            ),
            models.CheckConstraint(
                condition=~Q(status=IssueStatus.RESOLVED) | (Q(resolved_at__isnull=False) & ~Q(resolution='')),
                name='issue_resolved_has_resolution',
            ),
        ]

    def __str__(self):
        target = f'{self.order.name}'
        if self.shipment_id:
            target += f' / {self.shipment.tracking_number}'
        return f'{self.get_rule_code_display()} – {target}'

    @property
    def is_active(self):
        return self.status in ACTIVE_STATUSES

    # ----- state changes ------------------------------------------------
    # One place that knows the allowed moves, used by the admin, the future
    # queue page and the rules engine.

    def acknowledge(self, user):
        self._require_active()
        self.status = IssueStatus.ACKNOWLEDGED
        self.acknowledged_at = self.acknowledged_at or timezone.now()
        self.save(update_fields=['status', 'acknowledged_at', 'updated_at'])
        self._log(user, 'Acknowledged')

    def snooze(self, user, until):
        self._require_active()
        if until <= timezone.now():
            raise ValueError('Snooze time must be in the future.')
        self.status = IssueStatus.SNOOZED
        self.snoozed_until = until
        self.acknowledged_at = self.acknowledged_at or timezone.now()
        self.save(update_fields=['status', 'snoozed_until', 'acknowledged_at', 'updated_at'])
        self._log(user, f'Snoozed until {timezone.localtime(until):%Y-%m-%d %H:%M}')

    def resolve(self, user):
        """Closed by a person, e.g. after calling the carrier."""
        self._close(Resolution.MANUAL, user)
        self._log(user, 'Resolved')

    def auto_resolve(self):
        """Closed by the rules engine because the problem is gone."""
        self._close(Resolution.AUTO, None)
        self._log(None, 'Resolved automatically: the problem is no longer detected')

    def wake_up(self):
        """A snooze ran out and the problem is still there."""
        self.status = IssueStatus.OPEN
        self.snoozed_until = None
        self.save(update_fields=['status', 'snoozed_until', 'updated_at'])
        self._log(None, 'Snooze ended; the problem is still detected')

    def _close(self, resolution, user):
        self._require_active()
        self.status = IssueStatus.RESOLVED
        self.resolution = resolution
        self.resolved_at = timezone.now()
        self.resolved_by = user
        self.snoozed_until = None
        self.save(update_fields=['status', 'resolution', 'resolved_at', 'resolved_by', 'snoozed_until', 'updated_at'])

    def _require_active(self):
        if not self.is_active:
            raise ValueError(f'This exception is already {self.get_status_display().lower()}.')

    def _log(self, user, text):
        IssueNote.objects.create(issue=self, author=user, body=text, is_system=True)


class IssueNote(TimeStampedModel):
    """A comment by a person, or a status change recorded by ShipRadar."""

    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name='notes')
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,  # Deactivate users instead of deleting them.
        null=True,
        blank=True,
        related_name='issue_notes',
        help_text='Empty for changes made by the rules engine.',
    )
    body = models.TextField()
    is_system = models.BooleanField(default=False, help_text='Status change, not a typed comment.')

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return self.body[:60]


class RuleSetting(TimeStampedModel):
    """Thresholds for one rule, editable in the admin instead of hard-coded."""

    rule_code = models.CharField(max_length=30, choices=RuleCode.choices, unique=True)
    enabled = models.BooleanField(default=True)
    severity = models.PositiveSmallIntegerField(choices=Severity.choices)
    threshold = models.PositiveIntegerField(null=True, blank=True, help_text='For example 2 (business days).')
    threshold_unit = models.CharField(max_length=20, choices=ThresholdUnit.choices, blank=True)
    cutoff_time = models.TimeField(
        null=True,
        blank=True,
        help_text='Overdue rule only: orders paid after this local time count from the next business day.',
    )

    class Meta:
        ordering = ['severity', 'rule_code']
        constraints = [
            choices_constraint('rule_code', RuleCode, 'rule_setting_rule_code_valid'),
            models.CheckConstraint(condition=Q(severity__in=Severity.values), name='rule_setting_severity_valid'),
            models.CheckConstraint(
                condition=Q(threshold_unit='') | Q(threshold_unit__in=ThresholdUnit.values),
                name='rule_setting_unit_valid',
            ),
            # A threshold needs a unit, and a unit needs a threshold.
            models.CheckConstraint(
                condition=Q(threshold__isnull=True, threshold_unit='') | (Q(threshold__isnull=False) & ~Q(threshold_unit='')),
                name='rule_setting_threshold_has_unit',
            ),
        ]

    def __str__(self):
        return self.get_rule_code_display()


class Holiday(TimeStampedModel):
    """A day the warehouse does not ship; skipped when counting business days."""

    date = models.DateField(unique=True)
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ['date']

    def __str__(self):
        return f'{self.date:%Y-%m-%d} {self.name}'

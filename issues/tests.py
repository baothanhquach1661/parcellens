from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from orders.models import Carrier, Shipment
from orders.tests import make_order

from .business_days import sla_due_day, sla_start_day
from .models import Holiday, Issue, IssueNote, IssueStatus, Resolution, RuleCode, RuleSetting, Severity

LA = ZoneInfo('America/Los_Angeles')


def local(year, month, day, hour=10, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=LA)


class BusinessDayTests(SimpleTestCase):
    """2026-10-12 is a Monday."""

    def test_paid_before_cutoff_counts_today(self):
        self.assertEqual(sla_due_day(local(2026, 10, 12, 10), 2, set(), time(14)), date(2026, 10, 13))

    def test_paid_after_cutoff_starts_tomorrow(self):
        self.assertEqual(sla_due_day(local(2026, 10, 12, 15), 2, set(), time(14)), date(2026, 10, 14))

    def test_weekend_is_skipped(self):
        # Friday after the cut-off -> starts Monday -> due Tuesday.
        self.assertEqual(sla_due_day(local(2026, 10, 16, 15), 2, set(), time(14)), date(2026, 10, 20))

    def test_order_paid_on_saturday_starts_monday(self):
        self.assertEqual(sla_start_day(local(2026, 10, 17), set()), date(2026, 10, 19))

    def test_holidays_are_skipped(self):
        # Wednesday before Thanksgiving: Thursday is a holiday, so due Friday.
        thanksgiving = {date(2026, 11, 26)}
        self.assertEqual(sla_due_day(local(2026, 11, 25, 9), 2, thanksgiving, time(14)), date(2026, 11, 27))


class DefaultDataTests(TestCase):
    def test_every_rule_has_a_setting(self):
        self.assertEqual(set(RuleSetting.objects.values_list('rule_code', flat=True)), set(RuleCode.values))

    def test_overdue_rule_defaults(self):
        setting = RuleSetting.objects.get(rule_code=RuleCode.OVERDUE_UNFULFILLED)
        self.assertEqual((setting.threshold, setting.threshold_unit, setting.cutoff_time), (2, 'business_days', time(14)))

    def test_holidays_are_loaded(self):
        self.assertTrue(Holiday.objects.filter(date=date(2026, 11, 26), name='Thanksgiving').exists())


class IssueConstraintTests(TestCase):
    def setUp(self):
        self.order = make_order()
        self.shipment = Shipment.objects.create(
            order=self.order, carrier=Carrier.UPS, tracking_number='1Z1', shipped_at=timezone.now(),
        )

    def make_issue(self, rule=RuleCode.OVERDUE_UNFULFILLED, shipment=None, **kwargs):
        return Issue.objects.create(order=self.order, shipment=shipment, rule_code=rule, severity=Severity.HIGH, **kwargs)

    def test_only_one_active_issue_per_order_and_rule(self):
        self.make_issue()

        # shipment is NULL on both rows; nulls_distinct=False still catches it.
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_issue()

    def test_a_resolved_issue_does_not_block_a_new_one(self):
        self.make_issue().auto_resolve()

        self.make_issue()  # The problem came back: a new issue is fine.
        self.assertEqual(Issue.objects.count(), 2)

    def test_shipment_rules_need_a_shipment(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_issue(rule=RuleCode.STALE_TRACKING)

    def test_order_rules_must_not_have_a_shipment(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_issue(rule=RuleCode.OVERDUE_UNFULFILLED, shipment=self.shipment)

    def test_one_issue_per_package(self):
        other = Shipment.objects.create(order=self.order, carrier=Carrier.UPS, tracking_number='1Z2', shipped_at=timezone.now())
        self.make_issue(rule=RuleCode.STALE_TRACKING, shipment=self.shipment)
        self.make_issue(rule=RuleCode.STALE_TRACKING, shipment=other)

        self.assertEqual(Issue.objects.active().count(), 2)

    def test_snoozed_needs_an_end_time(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_issue(status=IssueStatus.SNOOZED)


class IssueStateTests(TestCase):
    def setUp(self):
        self.issue = Issue.objects.create(order=make_order(), rule_code=RuleCode.OVERDUE_UNFULFILLED, severity=Severity.HIGH)

    def test_acknowledge_keeps_it_active_and_logs_it(self):
        self.issue.acknowledge(user=None)

        self.assertEqual(self.issue.status, IssueStatus.ACKNOWLEDGED)
        self.assertIsNotNone(self.issue.acknowledged_at)
        self.assertTrue(self.issue.is_active)
        self.assertEqual(IssueNote.objects.get().body, 'Acknowledged')

    def test_snooze_must_end_in_the_future(self):
        with self.assertRaises(ValueError):
            self.issue.snooze(user=None, until=timezone.now() - timedelta(hours=1))

    def test_manual_resolve(self):
        self.issue.resolve(user=None)

        self.assertEqual((self.issue.status, self.issue.resolution), (IssueStatus.RESOLVED, Resolution.MANUAL))
        self.assertIsNotNone(self.issue.resolved_at)

    def test_a_resolved_issue_cannot_change_again(self):
        self.issue.resolve(user=None)

        with self.assertRaises(ValueError):
            self.issue.acknowledge(user=None)

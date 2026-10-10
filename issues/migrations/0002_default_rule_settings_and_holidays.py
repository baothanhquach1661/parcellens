"""Data migration: default rule thresholds and 2026-2027 warehouse holidays.

Written by hand (not generated). It uses apps.get_model(), the model as it was
at this point in the migration history, never `from issues.models import ...`:
the real class may gain fields later that this table does not have yet.
"""

import datetime

from django.db import migrations

# rule_code, severity (1 high, 2 medium, 3 low), threshold, unit, cutoff
DEFAULT_RULES = [
    ('overdue_unfulfilled', 1, 2, 'business_days', datetime.time(14, 0)),
    ('stockout', 1, None, '', None),
    ('delivery_exception', 1, None, '', None),
    ('missing_tracking', 2, 24, 'hours', None),
    ('stale_tracking', 2, 3, 'days', None),
    ('late_delivery', 2, None, '', None),
    ('suspicious_address', 3, None, '', None),
]

# Days most US carriers do not pick up. Weekend holidays use the observed weekday.
HOLIDAYS = [
    ('2026-01-01', "New Year's Day"),
    ('2026-05-25', 'Memorial Day'),
    ('2026-07-03', 'Independence Day (observed)'),
    ('2026-09-07', 'Labor Day'),
    ('2026-11-26', 'Thanksgiving'),
    ('2026-12-25', 'Christmas Day'),
    ('2027-01-01', "New Year's Day"),
    ('2027-05-31', 'Memorial Day'),
    ('2027-07-05', 'Independence Day (observed)'),
    ('2027-09-06', 'Labor Day'),
    ('2027-11-25', 'Thanksgiving'),
    ('2027-12-24', 'Christmas Day (observed)'),
]


def add_defaults(apps, schema_editor):
    RuleSetting = apps.get_model('issues', 'RuleSetting')
    Holiday = apps.get_model('issues', 'Holiday')
    for code, severity, threshold, unit, cutoff in DEFAULT_RULES:
        RuleSetting.objects.get_or_create(
            rule_code=code,
            defaults={'severity': severity, 'threshold': threshold, 'threshold_unit': unit, 'cutoff_time': cutoff},
        )
    for day, name in HOLIDAYS:
        Holiday.objects.get_or_create(date=datetime.date.fromisoformat(day), defaults={'name': name})


def remove_defaults(apps, schema_editor):
    apps.get_model('issues', 'RuleSetting').objects.filter(rule_code__in=[r[0] for r in DEFAULT_RULES]).delete()
    apps.get_model('issues', 'Holiday').objects.filter(date__in=[d for d, _ in HOLIDAYS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('issues', '0001_initial'),
    ]

    operations = [
        # The reverse function makes `migrate issues 0001` possible.
        migrations.RunPython(add_defaults, remove_defaults),
    ]

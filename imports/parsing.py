"""Turn raw CSV text into Python values, or raise ValueError with a clear message."""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

# Shopify exports look like "2026-10-01 14:23:45 -0700". ISO 8601 is accepted too.
DATETIME_FORMATS = (
    '%Y-%m-%d %H:%M:%S %z',
    '%Y-%m-%d %H:%M %z',
    '%Y-%m-%d %H:%M:%S',
    '%Y-%m-%d %H:%M',
)


def clean(value):
    """Strip whitespace; treat a missing cell as an empty string."""
    return (value or '').strip()


def parse_datetime(value, label):
    """Return an aware datetime, or None for an empty cell.

    A time without an offset is read in the store's time zone (settings.TIME_ZONE).
    """
    value = clean(value)
    if not value:
        return None
    parsed = None
    for fmt in DATETIME_FORMATS:
        try:
            parsed = datetime.strptime(value, fmt)
            break
        except ValueError:
            continue
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            raise ValueError(f"{label}: '{value}' is not a date and time") from None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, ZoneInfo(settings.TIME_ZONE))
    return parsed


def parse_decimal(value, label, required=True):
    """Money as Decimal. Accepts "1,234.50" and "$12.00"; never uses float."""
    value = clean(value).replace('$', '').replace(',', '')
    if not value:
        if required:
            raise ValueError(f'{label} is required')
        return None
    try:
        amount = Decimal(value)
    except InvalidOperation:
        raise ValueError(f"{label}: '{value}' is not a number") from None
    if amount < 0:
        raise ValueError(f'{label} cannot be negative')
    return amount.quantize(Decimal('0.01'))


def parse_positive_int(value, label):
    value = clean(value)
    try:
        number = int(value)
    except ValueError:
        raise ValueError(f"{label}: '{value}' is not a whole number") from None
    if number < 1:
        raise ValueError(f'{label} must be at least 1')
    return number


def parse_non_negative_int(value, label):
    value = clean(value)
    try:
        number = int(value)
    except ValueError:
        raise ValueError(f"{label}: '{value}' is not a whole number") from None
    if number < 0:
        raise ValueError(f'{label} is {number}; it must be 0 or more')
    return number


def parse_date(value, label):
    """A calendar date ("2026-10-12"); a date and time is cut down to its date."""
    value = clean(value)
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        pass
    return parse_datetime(value, label).date()


def parse_choice(value, choices, label, default=None):
    """Match a TextChoices value, ignoring case and spaces ("Partially Paid" -> partially_paid)."""
    value = clean(value).lower().replace(' ', '_').replace('-', '_')
    if not value and default is not None:
        return default
    if value not in choices.values:
        allowed = ', '.join(choices.values)
        raise ValueError(f"{label}: '{value}' is not one of: {allowed}")
    return value

"""Business-day arithmetic for SLA rules.

Pure functions (no database), so they are easy to test. Callers pass the
holiday dates and the store's time zone.
"""

from datetime import timedelta


def is_business_day(day, holidays):
    """Monday to Friday and not a holiday."""
    return day.weekday() < 5 and day not in holidays


def next_business_day(day, holidays):
    day += timedelta(days=1)
    while not is_business_day(day, holidays):
        day += timedelta(days=1)
    return day


def sla_start_day(paid_at_local, holidays, cutoff=None):
    """The first business day that counts towards the SLA.

    The day of payment counts if it is a business day and payment came before
    the cut-off time; otherwise the clock starts on the next business day.
    """
    day = paid_at_local.date()
    if not is_business_day(day, holidays):
        return next_business_day(day, holidays)
    if cutoff is not None and paid_at_local.time() >= cutoff:
        return next_business_day(day, holidays)
    return day


def sla_due_day(paid_at_local, business_days, holidays, cutoff=None):
    """Last day an order may ship and still meet an N-business-day SLA.

    The start day is day 1. Example with N=2 and a 14:00 cut-off:
    paid Monday 10:00 -> due Tuesday; paid Monday 15:00 -> due Wednesday;
    paid Friday 15:00 -> due Tuesday.
    """
    day = sla_start_day(paid_at_local, holidays, cutoff)
    for _ in range(business_days - 1):
        day = next_business_day(day, holidays)
    return day

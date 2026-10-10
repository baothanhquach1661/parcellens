from django.db import models


class TimeStampedModel(models.Model):
    """Adds created_at / updated_at, set by ShipRadar itself.

    These are not source times from imported files (such as Order.placed_at).
    Note: auto_now is not applied by QuerySet.update() or bulk_update().
    """

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


def choices_constraint(field_name, choices, name):
    """CheckConstraint that only allows the values of a TextChoices class.

    `choices` on a field is only checked by forms and full_clean();
    this makes PostgreSQL reject any other value too (imports, raw SQL).
    """
    return models.CheckConstraint(
        condition=models.Q(**{f'{field_name}__in': choices.values}),
        name=name,
    )

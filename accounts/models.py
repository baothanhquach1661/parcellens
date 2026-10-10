from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import UserManager as DjangoUserManager
from django.db import models


class UserRole(models.TextChoices):
    """What a user may do inside the ShipRadar app.

    Not the same as Django's built-in flags:
    - is_staff: may log in to Django's /admin site.
    - is_superuser: has every Django permission.
    A STAFF user normally has is_staff=False and only uses the ShipRadar UI.
    """

    ADMIN = 'admin', 'Admin'
    STAFF = 'staff', 'Staff'


class UserManager(DjangoUserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        # `createsuperuser` should produce an app admin, not a staff user.
        extra_fields.setdefault('role', UserRole.ADMIN)
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    """ShipRadar user.

    Defined at project start (before the first migrate) so fields can be
    added later without moving every auth foreign key off auth.User.
    """

    role = models.CharField(
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.STAFF,  # least privilege by default
    )

    objects = UserManager()

    class Meta:
        constraints = [
            # `choices` is only checked by forms; this enforces it in PostgreSQL too.
            models.CheckConstraint(
                condition=models.Q(role__in=UserRole.values),
                name='accounts_user_role_valid',
            ),
        ]

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ('username', 'email', 'role', 'is_active', 'is_staff')
    list_filter = ('role', 'is_active', 'is_staff')

    # Show the role field on the edit form and on the "add user" form.
    fieldsets = DjangoUserAdmin.fieldsets + (
        ('ShipRadar', {'fields': ('role',)}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ('ShipRadar', {'fields': ('role',)}),
    )

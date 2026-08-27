from django.contrib.admin import register
from django.contrib.auth.admin import UserAdmin

from apps.accounts.models import User


@register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ['username', 'first_name', 'last_name', 'role', 'language', 'is_active']
    list_filter = ['role', 'language', 'is_active', 'is_staff']
    fieldsets = UserAdmin.fieldsets + (
        ("Qo'shimcha", {'fields': ('role', 'phone', 'language')}),
    )

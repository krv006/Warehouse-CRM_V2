from django.contrib.admin import ModelAdmin, register

from apps.clients.models import Client


@register(Client)
class ClientAdmin(ModelAdmin):
    list_display = ['display_name', 'type', 'phone', 'inn', 'created_at']
    list_filter = ['type']
    search_fields = ['full_name', 'company_name', 'phone', 'inn']

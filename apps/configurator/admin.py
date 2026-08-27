from django.contrib.admin import ModelAdmin, TabularInline, register

from apps.configurator.models import Act, Configuration, ConfigurationItem


class ConfigurationItemInline(TabularInline):
    model = ConfigurationItem
    extra = 1


@register(Act)
class ActAdmin(ModelAdmin):
    list_display = ['number', 'title', 'issued_at', 'is_active']
    search_fields = ['number', 'title']


@register(Configuration)
class ConfigurationAdmin(ModelAdmin):
    list_display = ['number', 'client', 'base_product', 'status', 'created_at']
    list_filter = ['status']
    search_fields = ['number']
    inlines = [ConfigurationItemInline]

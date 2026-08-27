from django.contrib.admin import ModelAdmin, TabularInline, register

from apps.configurator.models import (
    Act,
    Configuration,
    ConfigurationItem,
    ConfigurationRemoval,
    ConfigurationRequest,
)


class ConfigurationItemInline(TabularInline):
    model = ConfigurationItem
    extra = 1


class ConfigurationRemovalInline(TabularInline):
    model = ConfigurationRemoval
    extra = 0


@register(Act)
class ActAdmin(ModelAdmin):
    list_display = ['number', 'title', 'issued_at', 'is_active']
    search_fields = ['number', 'title']


@register(Configuration)
class ConfigurationAdmin(ModelAdmin):
    list_display = ['number', 'client', 'base_product', 'mode', 'status', 'created_at']
    list_filter = ['mode', 'status']
    search_fields = ['number']
    inlines = [ConfigurationItemInline, ConfigurationRemovalInline]


@register(ConfigurationRequest)
class ConfigurationRequestAdmin(ModelAdmin):
    list_display = ['number', 'client', 'status', 'taken_by', 'created_by', 'created_at']
    list_filter = ['status']
    search_fields = ['number', 'text']

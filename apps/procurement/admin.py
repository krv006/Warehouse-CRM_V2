from django.contrib.admin import ModelAdmin, TabularInline, register

from apps.procurement.models import (
    Replenishment,
    ReplenishmentApproval,
    ReplenishmentEvent,
    ReplenishmentItem,
)


class ReplenishmentItemInline(TabularInline):
    model = ReplenishmentItem
    extra = 1


class ReplenishmentEventInline(TabularInline):
    model = ReplenishmentEvent
    extra = 0


class ReplenishmentApprovalInline(TabularInline):
    model = ReplenishmentApproval
    extra = 0


@register(Replenishment)
class ReplenishmentAdmin(ModelAdmin):
    list_display = ['number', 'warehouse', 'supplier', 'status', 'delivered_at', 'created_at']
    list_filter = ['status', 'warehouse', 'currency']
    search_fields = ['number', 'supplier']
    inlines = [ReplenishmentItemInline, ReplenishmentEventInline, ReplenishmentApprovalInline]

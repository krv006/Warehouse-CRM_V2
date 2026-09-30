from django.contrib.admin import ModelAdmin, TabularInline, register

from apps.procurement.models import (
    ImportCostSheet,
    PriceRequest,
    PriceRequestLine,
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


@register(ImportCostSheet)
class ImportCostSheetAdmin(ModelAdmin):
    list_display = ['number', 'product', 'status', 'quantity', 'created_at']
    list_filter = ['status']
    search_fields = ['number', 'product__name', 'product__sku']


class PriceRequestLineInline(TabularInline):
    model = PriceRequestLine
    extra = 0


@register(PriceRequest)
class PriceRequestAdmin(ModelAdmin):
    list_display = ['number', 'configuration', 'status', 'created_at']
    list_filter = ['status']
    search_fields = ['number', 'configuration__number']
    inlines = [PriceRequestLineInline]

from django.contrib.admin import ModelAdmin, TabularInline, register

from apps.inventory.models import (
    Warehouse,
    Product,
    ProductSpec,
    Stock,
    StockMovement,
)


class ProductSpecInline(TabularInline):
    model = ProductSpec
    fk_name = 'product'
    extra = 1


@register(Warehouse)
class WarehouseAdmin(ModelAdmin):
    list_display = ['name', 'is_active']


@register(Product)
class ProductAdmin(ModelAdmin):
    list_display = ['name', 'sku', 'kind', 'sale_price', 'reorder_level', 'is_active']
    list_filter = ['kind', 'is_active']
    search_fields = ['name', 'sku']
    inlines = [ProductSpecInline]


@register(Stock)
class StockAdmin(ModelAdmin):
    list_display = ['product', 'warehouse', 'quantity']
    list_filter = ['warehouse']


@register(StockMovement)
class StockMovementAdmin(ModelAdmin):
    list_display = ['product', 'warehouse', 'type', 'reason', 'quantity', 'created_at']
    list_filter = ['type', 'reason', 'warehouse']

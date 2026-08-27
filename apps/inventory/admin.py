from django.contrib.admin import ModelAdmin, TabularInline, register

from apps.inventory.models import (
    Category,
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


@register(Category)
class CategoryAdmin(ModelAdmin):
    list_display = ['name', 'parent']
    search_fields = ['name']


@register(Warehouse)
class WarehouseAdmin(ModelAdmin):
    list_display = ['name', 'is_active']


@register(Product)
class ProductAdmin(ModelAdmin):
    list_display = ['name', 'sku', 'kind', 'category', 'unit', 'sale_price', 'is_active']
    list_filter = ['kind', 'category', 'is_active', 'unit']
    search_fields = ['name', 'sku', 'barcode']
    inlines = [ProductSpecInline]


@register(Stock)
class StockAdmin(ModelAdmin):
    list_display = ['product', 'warehouse', 'quantity']
    list_filter = ['warehouse']


@register(StockMovement)
class StockMovementAdmin(ModelAdmin):
    list_display = ['product', 'warehouse', 'type', 'reason', 'quantity', 'created_at']
    list_filter = ['type', 'reason', 'warehouse']

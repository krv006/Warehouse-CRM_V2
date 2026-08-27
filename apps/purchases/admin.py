from django.contrib.admin import ModelAdmin, TabularInline, register

from apps.purchases.models import Purchase, PurchaseItem, PurchaseDocument


class PurchaseItemInline(TabularInline):
    model = PurchaseItem
    extra = 1


class PurchaseDocumentInline(TabularInline):
    model = PurchaseDocument
    extra = 0


@register(Purchase)
class PurchaseAdmin(ModelAdmin):
    list_display = ['number', 'type', 'status', 'supplier', 'ordered_at', 'expected_at']
    list_filter = ['type', 'status', 'warehouse']
    search_fields = ['number', 'supplier', 'invoice_number']
    inlines = [PurchaseItemInline, PurchaseDocumentInline]

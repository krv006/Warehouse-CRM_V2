from rest_framework.serializers import (
    ModelSerializer,
    PrimaryKeyRelatedField,
    ReadOnlyField,
)

from apps.inventory.models import Warehouse
from apps.inventory.services import main_warehouse
from apps.purchases.models import Purchase, PurchaseItem, PurchaseDocument


class PurchaseItemSerializer(ModelSerializer):
    product_name = ReadOnlyField(source='product.name')
    subtotal = ReadOnlyField()

    class Meta:
        model = PurchaseItem
        fields = [
            'id', 'product', 'product_name', 'quantity',
            'unit_price', 'subtotal', 'note',
        ]


class PurchaseDocumentSerializer(ModelSerializer):
    """Kirimga biriktirilgan hujjat (TZ 2.2)."""

    kind_display = ReadOnlyField(source='get_kind_display')
    uploaded_by_name = ReadOnlyField(source='uploaded_by.username')

    class Meta:
        model = PurchaseDocument
        fields = [
            'id', 'purchase', 'kind', 'kind_display', 'title', 'file',
            'uploaded_by', 'uploaded_by_name', 'created_at',
        ]
        read_only_fields = ['uploaded_by']


class PurchaseSerializer(ModelSerializer):
    """Biznesda bitta ombor — `warehouse` yuborilmasa yagona ombor olinadi."""

    warehouse = PrimaryKeyRelatedField(
        queryset=Warehouse.objects.all(), required=False,
    )
    items = PurchaseItemSerializer(many=True)
    documents = PurchaseDocumentSerializer(many=True, read_only=True)
    type_display = ReadOnlyField(source='get_type_display')
    status_display = ReadOnlyField(source='get_status_display')
    warehouse_name = ReadOnlyField(source='warehouse.name')
    items_total = ReadOnlyField()
    total_amount = ReadOnlyField()
    days_left = ReadOnlyField()
    color = ReadOnlyField()

    class Meta:
        model = Purchase
        fields = [
            'id', 'number', 'type', 'type_display', 'status', 'status_display',
            'supplier', 'warehouse', 'warehouse_name', 'contract', 'currency',
            'exchange_rate', 'lead_days', 'ordered_at', 'expected_at', 'received_at',
            'customs_duty', 'tax_amount', 'invoice_number', 'note', 'items', 'documents',
            'items_total', 'total_amount', 'days_left', 'color',
            'created_by', 'created_at',
        ]
        read_only_fields = ['number', 'created_by', 'received_at']

    def create(self, validated_data):
        items = validated_data.pop('items', [])
        if not validated_data.get('warehouse'):
            validated_data['warehouse'] = main_warehouse()
        purchase = Purchase.objects.create(**validated_data)
        for item in items:
            PurchaseItem.objects.create(purchase=purchase, **item)
        return purchase

    def update(self, instance, validated_data):
        items = validated_data.pop('items', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if items is not None:
            instance.items.all().delete()
            for item in items:
                PurchaseItem.objects.create(purchase=instance, **item)
        return instance

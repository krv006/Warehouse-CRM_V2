from rest_framework.serializers import (
    ModelSerializer,
    ReadOnlyField,
    SerializerMethodField,
)

from apps.inventory.models import (
    Warehouse,
    Product,
    ProductSpec,
    Stock,
    StockMovement,
)


class WarehouseSerializer(ModelSerializer):
    class Meta:
        model = Warehouse
        fields = ['id', 'name', 'address', 'is_active']


class ProductSpecSerializer(ModelSerializer):
    """Bazaviy modelning zavod tarkibi (TZ 6.1)."""

    component_name = ReadOnlyField(source='component.name')
    component_stock = SerializerMethodField()

    class Meta:
        model = ProductSpec
        fields = [
            'id', 'product', 'component', 'component_name',
            'component_stock', 'label', 'quantity',
        ]

    def get_component_stock(self, obj):
        return obj.component.total_stock


class ProductSerializer(ModelSerializer):
    kind_display = ReadOnlyField(source='get_kind_display')
    stock_price = ReadOnlyField()
    total_stock = ReadOnlyField()
    is_low_stock = ReadOnlyField()
    is_variant = ReadOnlyField()
    specs = ProductSpecSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'sku', 'name', 'kind', 'kind_display', 'description',
            'cost_price', 'sale_price', 'stock_price', 'reorder_level',
            'is_active', 'base_model', 'is_variant', 'signature',
            'total_stock', 'is_low_stock', 'specs',
        ]


class StockSerializer(ModelSerializer):
    product_name = ReadOnlyField(source='product.name')
    warehouse_name = ReadOnlyField(source='warehouse.name')

    class Meta:
        model = Stock
        fields = ['id', 'product', 'product_name', 'warehouse', 'warehouse_name', 'quantity']


class StockMovementSerializer(ModelSerializer):
    product_name = ReadOnlyField(source='product.name')
    warehouse_name = ReadOnlyField(source='warehouse.name')
    type_display = ReadOnlyField(source='get_type_display')
    reason_display = ReadOnlyField(source='get_reason_display')

    class Meta:
        model = StockMovement
        fields = [
            'id', 'product', 'product_name', 'warehouse', 'warehouse_name',
            'type', 'type_display', 'reason', 'reason_display', 'quantity',
            'reference', 'note', 'created_by', 'created_at',
        ]

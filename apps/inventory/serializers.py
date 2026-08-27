from rest_framework.serializers import (
    ModelSerializer,
    ReadOnlyField,
    SerializerMethodField,
)

from apps.inventory.models import (
    Category,
    Warehouse,
    Product,
    ProductSpec,
    Stock,
    StockMovement,
)


class CategorySerializer(ModelSerializer):
    parent_name = ReadOnlyField(source='parent.name')
    product_count = SerializerMethodField()

    class Meta:
        model = Category
        fields = ['id', 'name', 'parent', 'parent_name', 'product_count']

    def get_product_count(self, obj):
        return obj.products.count()


class WarehouseSerializer(ModelSerializer):
    class Meta:
        model = Warehouse
        fields = ['id', 'name', 'address', 'is_active']


class ProductSpecSerializer(ModelSerializer):
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
    category_name = ReadOnlyField(source='category.name')
    unit_display = ReadOnlyField(source='get_unit_display')
    kind_display = ReadOnlyField(source='get_kind_display')
    total_stock = ReadOnlyField()
    is_low_stock = ReadOnlyField()
    specs = ProductSpecSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'sku', 'barcode', 'name', 'kind', 'kind_display', 'description',
            'category', 'category_name', 'unit', 'unit_display', 'cost_price',
            'sale_price', 'reorder_level', 'image', 'is_active',
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
        read_only_fields = ['created_by']

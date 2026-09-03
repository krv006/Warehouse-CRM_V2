from rest_framework.serializers import (
    CharField,
    ModelSerializer,
    PrimaryKeyRelatedField,
    ReadOnlyField,
    SerializerMethodField,
    ValidationError,
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
    """Bazaviy modelning zavod tarkibi (TZ 6.1).

    Yozish — engineer (admin): tayyor model kirim qilinganda uning ichidagi
    butlovchilar shu yerda kiritiladi. Bazada yo'q butlovchi uchun
    `new_component_name` yuboriladi — u katalogga qo'shiladi.
    """

    component = PrimaryKeyRelatedField(
        queryset=Product.objects.all(), required=False, allow_null=True,
    )
    component_name = ReadOnlyField(source='component.name')
    component_stock = SerializerMethodField()
    new_component_name = CharField(write_only=True, required=False, allow_blank=True)
    new_component_sku = CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = ProductSpec
        fields = [
            'id', 'product', 'component', 'component_name',
            'new_component_name', 'new_component_sku',
            'component_stock', 'label', 'quantity',
        ]
        # unique(product, component) avto-validatori component'ni majburiy qiladi —
        # yangi butlovchi nom bilan kelganda xalaqit beradi; takrorni o'zimiz tekshiramiz
        validators = []

    def get_component_stock(self, obj):
        return obj.component.total_stock

    def validate_product(self, product):
        if product.kind != Product.Kind.MACHINE:
            raise ValidationError(
                "Tarkib faqat tayyor modelga qo'shiladi — bu mahsulot butlovchi.",
            )
        return product

    def validate(self, attrs):
        component = attrs.get('component') or (self.instance and self.instance.component)
        if not component and not (
            attrs.get('new_component_name') or attrs.get('new_component_sku')
        ):
            raise ValidationError({
                'component': 'Butlovchini tanlang yoki yangi butlovchi nomini kiriting.',
            })

        # unique(product, component) — takror qatorni o'zimiz tekshiramiz
        product = attrs.get('product') or (self.instance and self.instance.product)
        if product and component:
            duplicate = ProductSpec.objects.filter(product=product, component=component)
            if self.instance:
                duplicate = duplicate.exclude(pk=self.instance.pk)
            if duplicate.exists():
                raise ValidationError({
                    'component': 'Bu butlovchi tarkibda allaqachon bor.',
                })
        return attrs

    def _resolve_component(self, validated_data):
        from apps.inventory.services import create_product_from_order

        name = validated_data.pop('new_component_name', '')
        sku = validated_data.pop('new_component_sku', '')
        if validated_data.get('component') or not (name or sku):
            return validated_data
        validated_data['component'] = create_product_from_order(
            name=name, sku=sku, kind=Product.Kind.COMPONENT,
        )
        return validated_data

    def create(self, validated_data):
        return super().create(self._resolve_component(validated_data))

    def update(self, instance, validated_data):
        validated_data.pop('new_component_name', None)
        validated_data.pop('new_component_sku', None)
        return super().update(instance, validated_data)


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

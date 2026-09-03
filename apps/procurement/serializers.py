from rest_framework.serializers import (
    CharField,
    ChoiceField,
    ModelSerializer,
    PrimaryKeyRelatedField,
    ReadOnlyField,
    ValidationError,
)

from apps.inventory.models import Product, Warehouse
from apps.inventory.services import create_product_from_order, main_warehouse
from apps.procurement.models import (
    Replenishment,
    ReplenishmentApproval,
    ReplenishmentEvent,
    ReplenishmentItem,
)


class ReplenishmentItemSerializer(ModelSerializer):
    """To'ldirish qatori.

    TZ 7: buyurtma qilishning o'zi mahsulot qo'shish hisoblanadi. Shuning uchun
    bazada hali yo'q tovar uchun `product` o'rniga `product_name` yuboriladi —
    mahsulot shu qator bilan birga katalogga tushadi.
    """

    product = PrimaryKeyRelatedField(
        queryset=Product.objects.all(), required=False, allow_null=True,
    )
    product_name = CharField(write_only=True, required=False, allow_blank=True)
    product_sku = CharField(write_only=True, required=False, allow_blank=True)
    # Ikki xil kirim: 'component' (Butlovchi, default) yoki 'machine' (Tayyor model)
    product_kind = ChoiceField(
        choices=Product.Kind.choices, write_only=True, required=False,
    )

    product_display = ReadOnlyField(source='product.name')
    product_code = ReadOnlyField(source='product.sku')
    product_kind_display = ReadOnlyField(source='product.get_kind_display')
    subtotal = ReadOnlyField()
    needs_price = ReadOnlyField()

    class Meta:
        model = ReplenishmentItem
        fields = [
            'id', 'replenishment', 'product', 'product_name', 'product_sku',
            'product_kind', 'product_kind_display',
            'product_display', 'product_code', 'quantity', 'unit_price',
            'subtotal', 'needs_price', 'supplier', 'note',
        ]

    def validate(self, attrs):
        has_product = attrs.get('product') or (self.instance and self.instance.product_id)
        if not has_product and not (attrs.get('product_name') or attrs.get('product_sku')):
            raise ValidationError({
                'product': 'Mahsulotni tanlang yoki yangi mahsulot nomini kiriting.',
            })
        return attrs

    def _resolve_product(self, validated_data):
        name = validated_data.pop('product_name', '')
        sku = validated_data.pop('product_sku', '')
        kind = validated_data.pop('product_kind', None)
        if validated_data.get('product'):
            return validated_data
        validated_data['product'] = create_product_from_order(
            name=name, sku=sku, kind=kind,
            cost_price=validated_data.get('unit_price') or 0,
        )
        return validated_data

    def create(self, validated_data):
        return super().create(self._resolve_product(validated_data))

    def update(self, instance, validated_data):
        validated_data.pop('product_name', None)
        validated_data.pop('product_sku', None)
        validated_data.pop('product_kind', None)
        return super().update(instance, validated_data)


class ReplenishmentApprovalSerializer(ModelSerializer):
    step_display = ReadOnlyField(source='get_step_display')
    decision_display = ReadOnlyField(source='get_decision_display')
    decided_by_name = ReadOnlyField(source='decided_by.username')

    class Meta:
        model = ReplenishmentApproval
        fields = [
            'id', 'replenishment', 'step', 'step_display', 'decision',
            'decision_display', 'comment', 'decided_by', 'decided_by_name', 'created_at',
        ]
        read_only_fields = fields


class ReplenishmentEventSerializer(ModelSerializer):
    stage_display = ReadOnlyField(source='get_stage_display')
    created_by_name = ReadOnlyField(source='created_by.username')

    class Meta:
        model = ReplenishmentEvent
        fields = [
            'id', 'replenishment', 'stage', 'stage_display', 'comment',
            'happened_at', 'created_by', 'created_by_name', 'created_at',
        ]
        read_only_fields = ['created_by']


class ReplenishmentSerializer(ModelSerializer):
    """Biznesda bitta ombor — `warehouse` yuborilmasa yagona ombor olinadi."""

    warehouse = PrimaryKeyRelatedField(
        queryset=Warehouse.objects.all(), required=False,
    )
    items = ReplenishmentItemSerializer(many=True, read_only=True)
    approvals = ReplenishmentApprovalSerializer(many=True, read_only=True)
    events = ReplenishmentEventSerializer(many=True, read_only=True)
    status_display = ReadOnlyField(source='get_status_display')
    warehouse_name = ReadOnlyField(source='warehouse.name')
    configuration_number = ReadOnlyField(source='configuration.number')
    items_total = ReadOnlyField()
    total_amount = ReadOnlyField()
    cash_available = ReadOnlyField()
    shortfall = ReadOnlyField()
    debt_days_left = ReadOnlyField()
    debt_color = ReadOnlyField()

    class Meta:
        model = Replenishment
        fields = [
            'id', 'number', 'warehouse', 'warehouse_name', 'supplier',
            'configuration', 'configuration_number', 'status',
            'status_display', 'currency', 'logistics_cost', 'other_cost',
            'items_total', 'total_amount', 'cash_available', 'shortfall',
            'paid_amount', 'debt', 'debt_days_left', 'debt_color',
            'expected_at', 'delivered_at', 'note', 'items', 'approvals', 'events',
            'created_by', 'created_at',
        ]
        read_only_fields = [
            'number', 'status', 'created_by', 'paid_amount', 'debt', 'delivered_at',
        ]

    def create(self, validated_data):
        if not validated_data.get('warehouse'):
            validated_data['warehouse'] = main_warehouse()
        return super().create(validated_data)

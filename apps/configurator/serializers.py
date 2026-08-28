from rest_framework.serializers import (
    CharField,
    ModelSerializer,
    PrimaryKeyRelatedField,
    ReadOnlyField,
    SerializerMethodField,
    ValidationError,
)

from apps.configurator.models import (
    Act,
    Configuration,
    ConfigurationItem,
    ConfigurationRemoval,
    ConfigurationRequest,
)
from apps.configurator.services import copy_factory_spec
from apps.inventory.models import Product


class ActSerializer(ModelSerializer):
    class Meta:
        model = Act
        fields = [
            'id', 'number', 'title', 'description', 'issued_at',
            'file', 'is_active', 'created_by', 'created_at',
        ]
        read_only_fields = ['created_by']


def resolve_component(validated_data):
    """Bazada yo'q tovarni engineer configuratordan qo'shishi (TZ 7 uslubida).

    `new_component_name` (ixtiyoriy `new_component_sku`) yuborilsa va
    `component` tanlanmagan bo'lsa — mahsulot katalogga butlovchi sifatida
    yaratiladi. Xuddi to'ldirish buyurtmasidagi kabi: buyurtma qilishning
    o'zi mahsulot qo'shishdir.
    """
    from apps.inventory.models import Product
    from apps.inventory.services import create_product_from_order

    name = validated_data.pop('new_component_name', '')
    sku = validated_data.pop('new_component_sku', '')
    if validated_data.get('component') or not (name or sku):
        return validated_data
    validated_data['component'] = create_product_from_order(
        name=name, sku=sku, kind=Product.Kind.COMPONENT,
        cost_price=validated_data.get('unit_price') or 0,
    )
    return validated_data


class ConfigurationItemSerializer(ModelSerializer):
    configuration = PrimaryKeyRelatedField(
        queryset=Configuration.objects.all(), required=False,
    )
    component = PrimaryKeyRelatedField(
        queryset=Product.objects.all(), required=False, allow_null=True,
    )
    new_component_name = CharField(write_only=True, required=False, allow_blank=True)
    new_component_sku = CharField(write_only=True, required=False, allow_blank=True)
    component_name = ReadOnlyField(source='component.name')
    subtotal = ReadOnlyField()
    available = ReadOnlyField()
    shortage = ReadOnlyField()
    source = ReadOnlyField()
    stock_price = ReadOnlyField()
    needs_price = ReadOnlyField()

    class Meta:
        model = ConfigurationItem
        fields = [
            'id', 'configuration', 'component', 'new_component_name',
            'new_component_sku', 'component_name', 'label', 'quantity',
            'unit_price', 'stock_price', 'needs_price', 'subtotal',
            'available', 'shortage', 'source',
        ]

    def validate(self, attrs):
        has_component = attrs.get('component') or (self.instance and self.instance.component_id)
        if not has_component and not (
            attrs.get('new_component_name') or attrs.get('new_component_sku')
        ):
            raise ValidationError({
                'component': 'Butlovchini tanlang yoki yangi tovar nomini kiriting.',
            })
        return attrs

    def create(self, validated_data):
        return super().create(resolve_component(validated_data))

    def update(self, instance, validated_data):
        validated_data.pop('new_component_name', None)
        validated_data.pop('new_component_sku', None)
        return super().update(instance, validated_data)


class ConfigurationRemovalSerializer(ModelSerializer):
    """Yechib olingan butlovchi — omborga qaytgan, narxi bilan."""

    component_name = ReadOnlyField(source='component.name')
    subtotal = ReadOnlyField()

    class Meta:
        model = ConfigurationRemoval
        fields = [
            'id', 'configuration', 'component', 'component_name',
            'quantity', 'unit_price', 'subtotal', 'note', 'created_at',
        ]
        read_only_fields = fields


class ConfigurationSerializer(ModelSerializer):
    items = ConfigurationItemSerializer(many=True, required=False)
    removals = ConfigurationRemovalSerializer(many=True, read_only=True)
    mode_display = ReadOnlyField(source='get_mode_display')
    client_name = ReadOnlyField(source='client.display_name')
    base_product_name = ReadOnlyField(source='base_product.name')
    status_display = ReadOnlyField(source='get_status_display')
    act_number = ReadOnlyField(source='act.number')
    total_price = ReadOnlyField()
    items_total = ReadOnlyField()
    variant_sku = ReadOnlyField(source='variant.sku')
    missing_count = SerializerMethodField()
    ready_variant = SerializerMethodField()

    class Meta:
        model = Configuration
        fields = [
            'id', 'number', 'client', 'client_name', 'base_product', 'base_product_name',
            'warehouse', 'act', 'act_number', 'purchase', 'mode', 'mode_display',
            'status', 'status_display',
            'note', 'items', 'items_total', 'total_price', 'variant', 'variant_sku',
            'ready_variant', 'missing_count', 'removals',
            'created_by', 'created_at',
        ]
        read_only_fields = ['number', 'created_by', 'purchase', 'variant']

    def get_missing_count(self, obj):
        return len(obj.missing_items)

    def get_ready_variant(self, obj):
        """Xuddi shu tarkib omborda tayyor pozitsiya sifatida bormi (TZ 6.2)."""
        variant = obj.variant or obj.matching_variant
        if not variant:
            return None
        return {
            'id': variant.id,
            'sku': variant.sku,
            'name': variant.name,
            'price': variant.stock_price,
            'stock': variant.total_stock,
            'is_base_model': variant.pk == obj.base_product_id,
        }

    def create(self, validated_data):
        from apps.inventory.services import main_warehouse

        items = validated_data.pop('items', [])
        if not validated_data.get('warehouse'):
            # Biznesda bitta ombor — tanlash shart emas, yagona ombor olinadi
            validated_data['warehouse'] = main_warehouse()
        configuration = Configuration.objects.create(**validated_data)
        if items:
            for item in items:
                item.pop('configuration', None)
                ConfigurationItem.objects.create(
                    configuration=configuration, **resolve_component(item),
                )
        else:
            # TZ 6.1: model tanlanganda uning ichidagi barcha narsa tayyor keladi
            copy_factory_spec(configuration)
        return configuration

    def update(self, instance, validated_data):
        items = validated_data.pop('items', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if items is not None:
            instance.items.all().delete()
            for item in items:
                item.pop('configuration', None)
                ConfigurationItem.objects.create(
                    configuration=instance, **resolve_component(item),
                )
        return instance


class ConfigurationRequestSerializer(ModelSerializer):
    """Sales'dan Engineerga boradigan matnli zayavka."""

    status_display = ReadOnlyField(source='get_status_display')
    client_name = ReadOnlyField(source='client.display_name')
    base_product_name = ReadOnlyField(source='base_product.name')
    configuration_number = ReadOnlyField(source='configuration.number')
    taken_by_name = ReadOnlyField(source='taken_by.username')
    created_by_name = ReadOnlyField(source='created_by.username')

    class Meta:
        model = ConfigurationRequest
        fields = [
            'id', 'number', 'client', 'client_name', 'text',
            'base_product', 'base_product_name', 'warehouse', 'status',
            'status_display', 'configuration', 'configuration_number',
            'taken_by', 'taken_by_name', 'created_by', 'created_by_name',
            'created_at',
        ]
        read_only_fields = ['number', 'status', 'configuration', 'taken_by', 'created_by']

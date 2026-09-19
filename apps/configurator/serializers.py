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
    ConfigurationApproval,
    ConfigurationItem,
    ConfigurationRemoval,
    ConfigurationRequest,
    ConfigurationRequestEvent,
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
    overbooked = ReadOnlyField()
    stock_total = ReadOnlyField()
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
            'available', 'overbooked', 'stock_total', 'shortage', 'source',
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


class ConfigurationApprovalSerializer(ModelSerializer):
    """Texnik tasdiq tarixi (#4) — sales qarorlari izohi bilan."""

    step_display = ReadOnlyField(source='get_step_display')
    decision_display = ReadOnlyField(source='get_decision_display')
    decided_by_name = ReadOnlyField(source='decided_by.display_name')

    class Meta:
        model = ConfigurationApproval
        fields = [
            'id', 'configuration', 'step', 'step_display', 'decision',
            'decision_display', 'comment', 'decided_by', 'decided_by_name',
            'created_at',
        ]
        read_only_fields = fields


class ConfigurationSerializer(ModelSerializer):
    items = ConfigurationItemSerializer(many=True, required=False)
    removals = ConfigurationRemovalSerializer(many=True, read_only=True)
    approvals = ConfigurationApprovalSerializer(many=True, read_only=True)
    mode_display = ReadOnlyField(source='get_mode_display')
    client_name = ReadOnlyField(source='client.display_name')
    base_product_name = ReadOnlyField(source='base_product.name')
    status_display = ReadOnlyField(source='get_status_display')
    # EGALIK §5: "Xodim" ustuni uchun — qaysi engineer ishlayapti
    created_by_name = ReadOnlyField(source='created_by.display_name')
    act_number = ReadOnlyField(source='act.number')
    total_price = ReadOnlyField()
    items_total = ReadOnlyField()
    variant_sku = ReadOnlyField(source='variant.sku')
    missing = SerializerMethodField()
    missing_count = SerializerMethodField()
    contract = SerializerMethodField()
    ready_variant = SerializerMethodField()
    procurement = SerializerMethodField()
    sent_to_procurement = SerializerMethodField()

    class Meta:
        model = Configuration
        fields = [
            'id', 'number', 'client', 'client_name', 'base_product', 'base_product_name',
            'warehouse', 'act', 'act_number', 'mode', 'mode_display',
            'quantity', 'status', 'status_display',
            'note', 'items', 'items_total', 'total_price', 'variant', 'variant_sku',
            'ready_variant', 'missing', 'missing_count', 'contract',
            'procurement', 'sent_to_procurement', 'cancel_reason',
            'assembled_at', 'removals', 'approvals',
            'created_by', 'created_by_name', 'created_at',
        ]
        read_only_fields = [
            'number', 'created_by', 'variant', 'assembled_at', 'cancel_reason',
        ]

    def get_missing(self, obj):
        """Ombordan olinishi kerak-u, yetishmayotganlar (3-to'plam §2).

        Front qoidasi bitta qator: ro'yxat bo'sh — "Yig'ish" tugmasi,
        bo'sh emas — "Buyurtmachiga yuborish · N". `required_from_stock`
        dan quriladi: modify'da bazaviy model ham shu yerda (`kind` orqali
        tayyor model va butlovchi farqlanadi).
        """
        return [
            {
                'product': row['product'].pk,
                'name': row['product'].name,
                'kind': row['product'].kind,
                'needed': row['needed'],
                'available': row['available'],
                'overbooked': row['overbooked'],
                'shortage': row['shortage'],
            }
            for row in obj.missing_items
        ]

    def get_missing_count(self, obj):
        return len(obj.missing_items)

    def get_contract(self, obj):
        """Zanjirdagi shartnoma (YANGI-OQIM B9) — "to'lov keldimi?" javobi.

        Front 13–16 qadamlarni (ta'minot, yig'ish) `is_paid` bilan qulflaydi:
        tugmalar boshlang'ich to'lovdan keyingina chiqadi.
        """
        contract = obj.active_contract
        if not contract:
            return None
        return {
            'id': contract.id,
            'number': contract.number,
            'status': contract.status,
            'status_display': contract.get_status_display(),
            'total_amount': contract.total_amount,
            'prepayment_amount': contract.prepayment_amount,
            'paid': contract.paid,
            'is_paid': contract.status in ('active', 'completed'),
        }

    def get_procurement(self, obj):
        """Buyurtmachiga yuborilgan oxirgi TLD hisobi — front badge shu yerdan.

        None — hech qachon yuborilmagan; is_open=False — jarayon tugagan
        (bekor qilingan yoki omborga kirim bo'lgan).
        """
        replenishment = obj.last_replenishment
        if not replenishment:
            return None
        return {
            'id': replenishment.id,
            'number': replenishment.number,
            'status': replenishment.status,
            'status_display': replenishment.get_status_display(),
            'is_open': replenishment.is_open,
            'created_at': replenishment.created_at,
        }

    def get_sent_to_procurement(self, obj):
        """Yetishmayotganlar buyurtmachida va jarayon hali tugamagan — qisqa flag."""
        return obj.open_replenishment is not None

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
        from apps.inventory.services import main_warehouse, sync_configuration_reservations

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
        sync_configuration_reservations(configuration)
        return configuration

    def update(self, instance, validated_data):
        from apps.inventory.services import sync_configuration_reservations

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
        # §11.4: qatorlar yoki holat o'zgardi — yumshoq bron moslashadi
        sync_configuration_reservations(instance)
        return instance


class ConfigurationRequestEventSerializer(ModelSerializer):
    """Zayavka tarixi qadami (B15) — TLD timeline'i bilan bir xil shakl."""

    stage_display = ReadOnlyField(source='get_stage_display')
    created_by_name = ReadOnlyField(source='created_by.display_name')

    class Meta:
        model = ConfigurationRequestEvent
        fields = [
            'id', 'request', 'stage', 'stage_display', 'comment',
            'created_by', 'created_by_name', 'created_at',
        ]
        read_only_fields = fields


class ConfigurationRequestSerializer(ModelSerializer):
    """Sales'dan Engineerga boradigan matnli zayavka."""

    events = ConfigurationRequestEventSerializer(many=True, read_only=True)
    status_display = ReadOnlyField(source='get_status_display')
    client_name = ReadOnlyField(source='client.display_name')
    base_product_name = ReadOnlyField(source='base_product.name')
    configuration_number = ReadOnlyField(source='configuration.number')
    # Ikki xodim: kim so'radi (sales) va kim bajaryapti (engineer) — EGALIK §5.5
    taken_by_name = ReadOnlyField(source='taken_by.display_name')
    created_by_name = ReadOnlyField(source='created_by.display_name')

    class Meta:
        model = ConfigurationRequest
        fields = [
            'id', 'number', 'client', 'client_name', 'text', 'quantity',
            'base_product', 'base_product_name', 'warehouse', 'status',
            'status_display', 'configuration', 'configuration_number',
            'taken_by', 'taken_by_name', 'created_by', 'created_by_name',
            'events', 'created_at',
        ]
        read_only_fields = ['number', 'status', 'configuration', 'taken_by', 'created_by']

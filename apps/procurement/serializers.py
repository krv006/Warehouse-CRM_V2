from rest_framework.serializers import (
    CharField,
    ChoiceField,
    ModelSerializer,
    PrimaryKeyRelatedField,
    ReadOnlyField,
    SerializerMethodField,
    ValidationError,
)

from apps.inventory.models import Product, Warehouse
from apps.inventory.services import create_product_from_order, main_warehouse
from apps.procurement.models import (
    ImportCostSheet,
    PriceRequest,
    PriceRequestLine,
    Replenishment,
    ReplenishmentApproval,
    ReplenishmentEvent,
    ReplenishmentItem,
)

# 28-§2: uch rol bir-birining raqamini ko'rmaydi.
_PRICE_REQUEST_SUPPLIER_FIELDS = [
    'currency', 'goods_price', 'exchange_rate', 'extra_costs', 'cost_price',
]
_PRICE_REQUEST_LOGISTICS_FIELDS = ['logistics_total', 'freight_to_border', 'logistics_note']
_PRICE_REQUEST_CUSTOMS_FIELDS = [
    'tnved_code', 'duty_percent', 'duty_amount', 'excise_amount', 'customs_fee',
    'certificate_cost', 'laboratory_cost', 'declarant_fee', 'customs_note',
]
# 30-§3: eski goods_uzs/customs_value/duty/vat/customs_total/landed_total
# o'rnini bosdi — declarant_unit tovar narxini o'zida oshkor qiladi,
# logistics_unit/extra_unit esa quantity bilan birga jami summani orqaga
# hisoblashga imkon beradi, shuning uchun barchasi xuddi eskisidek
# logist/deklarantdan yashiriladi
_PRICE_REQUEST_MONEY_TOTALS = [
    'declarant_unit', 'logistics_unit', 'extra_unit', 'suggested_cost',
]


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
    vat_amount = ReadOnlyField()
    total_with_vat = ReadOnlyField()
    needs_price = ReadOnlyField()
    # 14-§6: ko'p modelli savdoda bitta TLD — bu qator qaysi model uchun
    configuration_number = ReadOnlyField(source='configuration.number')
    configuration_product_name = ReadOnlyField(source='configuration.base_product.name')

    class Meta:
        model = ReplenishmentItem
        fields = [
            'id', 'replenishment', 'product', 'product_name', 'product_sku',
            'product_kind', 'product_kind_display',
            'product_display', 'product_code', 'quantity', 'unit_price',
            'subtotal', 'vat_percent', 'vat_amount', 'total_with_vat',
            'needs_price', 'supplier', 'note',
            'configuration', 'configuration_number', 'configuration_product_name',
        ]
        read_only_fields = ['configuration']

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
    contract_number = ReadOnlyField(source='contract.number')
    owner_sales_name = ReadOnlyField(source='owner_sales.display_name')
    items_total = ReadOnlyField()
    vat_total = ReadOnlyField()
    items_total_with_vat = ReadOnlyField()
    total_amount = ReadOnlyField()
    cash_available = SerializerMethodField()
    shortfall = SerializerMethodField()
    debt_days_left = ReadOnlyField()
    debt_color = ReadOnlyField()
    purchase = SerializerMethodField()

    class Meta:
        model = Replenishment
        fields = [
            'id', 'number', 'warehouse', 'warehouse_name', 'supplier',
            'configuration', 'configuration_number',
            'contract', 'contract_number',
            'owner_sales', 'owner_sales_name', 'status',
            'status_display', 'currency', 'exchange_rate',
            'logistics_cost', 'other_cost',
            'items_total', 'vat_total', 'items_total_with_vat',
            'total_amount', 'cash_available', 'shortfall',
            'paid_amount', 'debt', 'debt_days_left', 'debt_color',
            'purchase', 'expected_at', 'delivered_at', 'note',
            'items', 'approvals', 'events',
            'created_by', 'created_at',
        ]
        read_only_fields = [
            'number', 'status', 'created_by', 'paid_amount', 'debt', 'delivered_at',
            'owner_sales', 'contract',
        ]

    def _is_finance_user(self):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        return bool(
            user and user.is_authenticated and (user.is_admin or user.is_bugalter)
        )

    def get_cash_available(self, obj):
        """Kassa qoldig'i — faqat admin va bugalterga (TZ 8.2 sizmasin)."""
        return obj.cash_available if self._is_finance_user() else None

    def get_shortfall(self, obj):
        return obj.shortfall if self._is_finance_user() else None

    def get_purchase(self, obj):
        """receive'da avtomatik ochilgan KIR hujjati — invoys/bojxona shu yerda."""
        purchase = obj.purchases.first()
        if not purchase:
            return None
        return {'id': purchase.id, 'number': purchase.number, 'status': purchase.status}

    def create(self, validated_data):
        if not validated_data.get('warehouse'):
            validated_data['warehouse'] = main_warehouse()
        return super().create(validated_data)


class ImportCostSheetSerializer(ModelSerializer):
    """24-to'plam: import tannarx varaqasi.

    §4.1: hisob (BQ, boj, QQS bazasi, jami, dona tannarx) kartada
    ko'rinib turishi kerak — deklarant o'z raqamini tekshira olsin.
    Bo'lim maydonlari to'g'ridan-to'g'ri yoziladi (`goods_price`,
    `logistics_total`, `tnved_code` va h.k.) — har bo'limni to'ldirish
    o'z servis funksiyasi (`fill_goods_section`/...) orqali, bu
    serializer faqat KO'RSATISH va ro'yxat/filtr uchun.
    """

    status_display = ReadOnlyField(source='get_status_display')
    product_name = ReadOnlyField(source='product.name')
    configuration_number = ReadOnlyField(source='configuration.number')
    goods_filled_by_name = ReadOnlyField(source='goods_filled_by.display_name')
    logistics_filled_by_name = ReadOnlyField(source='logistics_filled_by.display_name')
    customs_filled_by_name = ReadOnlyField(source='customs_filled_by.display_name')
    created_by_name = ReadOnlyField(source='created_by.display_name')
    # §5.3: hisoblangan — bazada saqlanmaydi, har o'qishda qayta chiqadi
    goods_uzs = ReadOnlyField()
    customs_value = ReadOnlyField()
    duty = ReadOnlyField()
    vat = ReadOnlyField()
    vat_in_cost = ReadOnlyField()
    customs_total = ReadOnlyField()
    landed_total = ReadOnlyField()
    unit_cost = ReadOnlyField()

    class Meta:
        model = ImportCostSheet
        fields = [
            'id', 'number', 'status', 'status_display', 'product', 'product_name',
            'quantity', 'vat_recoverable', 'configuration', 'configuration_number',
            'currency', 'goods_price', 'exchange_rate', 'origin_country',
            'goods_filled_by', 'goods_filled_by_name', 'goods_filled_at',
            'logistics_total', 'logistics_note',
            'logistics_filled_by', 'logistics_filled_by_name', 'logistics_filled_at',
            'tnved_code', 'freight_to_border', 'duty_percent', 'duty_amount',
            'excise_amount', 'vat_percent', 'customs_fee', 'certificate_cost',
            'laboratory_cost', 'declarant_fee', 'customs_note',
            'customs_filled_by', 'customs_filled_by_name', 'customs_filled_at',
            'goods_uzs', 'customs_value', 'duty', 'vat', 'vat_in_cost',
            'customs_total', 'landed_total', 'unit_cost',
            'created_by', 'created_by_name', 'created_at',
        ]
        read_only_fields = [
            'id', 'number', 'status', 'status_display', 'product_name',
            'configuration', 'configuration_number', 'vat_recoverable',
            'goods_price', 'exchange_rate', 'origin_country', 'currency',
            'goods_filled_by', 'goods_filled_by_name', 'goods_filled_at',
            'logistics_total', 'logistics_note',
            'logistics_filled_by', 'logistics_filled_by_name', 'logistics_filled_at',
            'tnved_code', 'freight_to_border', 'duty_percent', 'duty_amount',
            'excise_amount', 'vat_percent', 'customs_fee', 'certificate_cost',
            'laboratory_cost', 'declarant_fee', 'customs_note',
            'customs_filled_by', 'customs_filled_by_name', 'customs_filled_at',
            'created_by', 'created_by_name', 'created_at',
        ]


class PriceRequestLineSerializer(ModelSerializer):
    """28-§1/§2: bitta mahsulot. Yozish faqat servis amallari orqali
    (`fill-logistics`/`fill-customs`/`answer`/...) — bu serializer KO'RSATISH
    uchun, shuning uchun barcha maydon `read_only`.

    28-§2: uch rol bir-birining raqamini ko'rmaydi — `to_representation`
    joriy foydalanuvchi roliga qarab tegishli maydonlarni kesib tashlaydi.
    """

    product_name = ReadOnlyField(source='product.name')
    status = ReadOnlyField()
    status_display = SerializerMethodField()
    # 29-§5: qadam kimda turganini aytsin (tooltip uchun) — pul emas, shuning
    # uchun uch rol izolyatsiyasiga kirmaydi
    logistics_filled_by_name = ReadOnlyField(source='logistics_filled_by.display_name')
    customs_filled_by_name = ReadOnlyField(source='customs_filled_by.display_name')
    # 30-§3: yangi hisob — eski goods_uzs/customs_value/duty/vat/
    # customs_total/landed_total o'rniga
    declarant_unit = ReadOnlyField()
    logistics_unit = ReadOnlyField()
    extra_unit = ReadOnlyField()
    suggested_cost = ReadOnlyField()

    class Meta:
        model = PriceRequestLine
        fields = [
            'id', 'request', 'product', 'product_name', 'quantity',
            'is_imported', 'status', 'status_display',
            'logistics_total', 'freight_to_border', 'logistics_note', 'logistics_filled_at',
            'logistics_filled_by', 'logistics_filled_by_name',
            'tnved_code', 'duty_percent', 'duty_amount', 'excise_amount', 'customs_fee',
            'certificate_cost', 'laboratory_cost', 'declarant_fee', 'customs_note',
            'customs_filled_at', 'customs_auto_filled', 'customs_filled_by', 'customs_filled_by_name',
            'currency', 'goods_price', 'exchange_rate', 'extra_costs', 'cost_price', 'answered_at',
            'declarant_unit', 'logistics_unit', 'extra_unit', 'suggested_cost', 'created_at',
        ]
        read_only_fields = fields

    def get_status_display(self, obj):
        return PriceRequest.Status(obj.status).label

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if not (user and user.is_authenticated) or user.is_admin:
            return data
        if user.is_bugalter or user.is_supplier:
            return data
        hidden = []
        if user.is_logist:
            hidden = (
                _PRICE_REQUEST_SUPPLIER_FIELDS + _PRICE_REQUEST_CUSTOMS_FIELDS
                + _PRICE_REQUEST_MONEY_TOTALS
            )
        elif user.is_declarant:
            hidden = (
                _PRICE_REQUEST_SUPPLIER_FIELDS + _PRICE_REQUEST_LOGISTICS_FIELDS
                + _PRICE_REQUEST_MONEY_TOTALS
            )
        else:
            hidden = (
                _PRICE_REQUEST_SUPPLIER_FIELDS + _PRICE_REQUEST_LOGISTICS_FIELDS
                + _PRICE_REQUEST_CUSTOMS_FIELDS + _PRICE_REQUEST_MONEY_TOTALS
            )
        for field in hidden:
            data.pop(field, None)
        return data


class PriceRequestSerializer(ModelSerializer):
    """28-§1: narx so'rovi hujjati — buyurtmachining (va import bo'lsa
    logist/deklarantning) ish joyi."""

    number = ReadOnlyField()
    status_display = ReadOnlyField(source='get_status_display')
    configuration_number = ReadOnlyField(source='configuration.number')
    created_by_name = ReadOnlyField(source='created_by.display_name')
    lines = PriceRequestLineSerializer(many=True, read_only=True)

    class Meta:
        model = PriceRequest
        fields = [
            'id', 'number', 'status', 'status_display', 'configuration',
            'configuration_number', 'lines', 'created_by', 'created_by_name', 'created_at',
        ]
        read_only_fields = ['number', 'status', 'configuration', 'created_by']

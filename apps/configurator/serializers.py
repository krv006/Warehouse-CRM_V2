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
    ActApproval,
    Configuration,
    ConfigurationApproval,
    ConfigurationItem,
    ConfigurationRemoval,
    ConfigurationRequest,
    ConfigurationRequestEvent,
    ConfigurationRequestLine,
)
from apps.configurator.services import copy_factory_spec
from apps.inventory.models import Product


class ActApprovalSerializer(ModelSerializer):
    """20-§3.2: ACT tasdig'i tarixi — kim, qachon, nima qilgani."""

    decision_display = ReadOnlyField(source='get_decision_display')
    decided_by_name = ReadOnlyField(source='decided_by.display_name')

    class Meta:
        model = ActApproval
        fields = [
            'id', 'act', 'decision', 'decision_display', 'comment',
            'decided_by', 'decided_by_name', 'created_at',
        ]
        read_only_fields = fields


class ActSerializer(ModelSerializer):
    status_display = ReadOnlyField(source='get_status_display')
    approvals = ActApprovalSerializer(many=True, read_only=True)

    class Meta:
        model = Act
        fields = [
            'id', 'number', 'title', 'description', 'issued_at',
            'file', 'status', 'status_display', 'approvals', 'is_active',
            'created_by', 'created_at',
        ]
        read_only_fields = ['status', 'created_by']


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
    approvals = SerializerMethodField()
    mode_display = ReadOnlyField(source='get_mode_display')
    client_name = ReadOnlyField(source='client.display_name')
    base_product_name = ReadOnlyField(source='base_product.name')
    status_display = ReadOnlyField(source='get_status_display')
    # EGALIK §5: "Xodim" ustuni uchun — qaysi engineer ishlayapti
    created_by_name = ReadOnlyField(source='created_by.display_name')
    act_number = ReadOnlyField(source='act.number')
    act_status = SerializerMethodField()
    total_price = ReadOnlyField()
    items_total = ReadOnlyField()
    variant_sku = ReadOnlyField(source='variant.sku')
    missing = SerializerMethodField()
    missing_count = SerializerMethodField()
    contract = SerializerMethodField()
    ready_variant = SerializerMethodField()
    procurement = SerializerMethodField()
    sent_to_procurement = SerializerMethodField()
    deal = SerializerMethodField()
    price_requested_at = SerializerMethodField()

    class Meta:
        model = Configuration
        fields = [
            'id', 'number', 'client', 'client_name', 'base_product', 'base_product_name',
            'warehouse', 'act', 'act_number', 'act_status', 'mode', 'mode_display',
            'quantity', 'status', 'status_display',
            'note', 'items', 'items_total', 'total_price', 'variant', 'variant_sku',
            'ready_variant', 'missing', 'missing_count', 'contract', 'deal',
            'procurement', 'sent_to_procurement', 'price_requested_at', 'cancel_reason',
            'assembled_at', 'removals', 'approvals',
            'created_by', 'created_by_name', 'created_at',
        ]
        read_only_fields = [
            'number', 'created_by', 'variant', 'assembled_at', 'cancel_reason',
        ]

    def get_act_status(self, obj):
        """21-§5: ACT holati — ACT yo'q bo'lsa `null`."""
        return obj.act.status if obj.act_id else None

    def get_missing(self, obj):
        """Ombordan olinishi kerak-u, yetishmayotganlar (3-to'plam §2).

        Front qoidasi bitta qator: ro'yxat bo'sh — "Yig'ish" tugmasi,
        bo'sh emas — "Buyurtmachiga yuborish · N". `required_from_stock`
        dan quriladi: modify'da bazaviy model ham shu yerda (`kind` orqali
        tayyor model va butlovchi farqlanadi).
        """
        from apps.configurator.services import _missing_rows

        return _missing_rows(obj)

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
        """Buyurtmachiga yuborilgan TLD hisobi — front badge shu yerdan.

        18-§2: TLD savdoda BITTA (14-§6) — asosiy bo'lmagan model o'zining
        `obj.last_replenishment`iga qarasa har doim bo'sh chiqadi (TLD
        asosiy modelga bog'langan). `chain_open_replenishment` butun
        savdo bo'yicha qidiradi; bitta modelli zanjirda xulq o'zgarmaydi
        (o'sha modelning o'z hisobini qaytaradi). `opened_for` — hisob
        qaysi model orqali ochilgani (uning `Replenishment.configuration`
        — savdoning asosiy modeli).

        None — hech qachon yuborilmagan; is_open=False — jarayon tugagan
        (bekor qilingan yoki omborga kirim bo'lgan).
        """
        from apps.configurator.services import chain_open_replenishment

        replenishment = chain_open_replenishment(configuration=obj) or obj.last_replenishment
        if not replenishment:
            return None
        return {
            'id': replenishment.id,
            'number': replenishment.number,
            'status': replenishment.status,
            'status_display': replenishment.get_status_display(),
            'is_open': replenishment.is_open,
            'created_at': replenishment.created_at,
            'opened_for': (
                replenishment.configuration.number if replenishment.configuration_id else None
            ),
        }

    def get_sent_to_procurement(self, obj):
        """Yetishmayotganlar buyurtmachida va jarayon hali tugamagan — qisqa flag.

        18-§2: `chain_open_replenishment` orqali — savdodagi BOSHQA model
        ochgan TLD ham shu modelni "yuborilgan" deb belgilaydi (aks holda
        tugma yana ko'rinib, engineer ikkinchi marta bosardi).
        """
        from apps.configurator.services import chain_open_replenishment

        return chain_open_replenishment(configuration=obj) is not None

    def get_price_requested_at(self, obj):
        """QOLGAN-ISHLAR-2 §7: oxirgi narx so'rovi qachon bo'lgani — tugma
        "Narx so'raldi · <vaqt>" holatiga o'tsin, qayta bosish ochiq qoladi.
        Ko'p modelli savdoda — savdo (ZVK) bo'yicha oxirgisi.
        """
        from apps.configurator.models import ConfigurationRequestEvent
        from apps.configurator.services import _owning_request

        request_obj = _owning_request(obj)
        if request_obj is None:
            return None
        event = (
            request_obj.events
            .filter(stage=ConfigurationRequestEvent.Stage.PRICE_ASKED)
            .order_by('-created_at')
            .first()
        )
        return event.created_at if event else None

    def get_deal(self, obj):
        """14-§2: savdo bloki — ko'p modelli zayavkada N model + M tovar,
        bitta shartnoma/TLD/ACT. Bitta modelli zayavkada `None`.
        """
        from apps.configurator.services import _owning_request, build_deal

        return build_deal(_owning_request(obj))

    def get_approvals(self, obj):
        """16-§A3: savdoning yozishmasi = ASOSIY modelning yozishmasi.

        Ko'p modelli savdoda qaysi model sahifasida tursangiz ham bitta
        suhbat ko'rinsin — bitta modelli zayavkada asosiy model yagona
        model bo'lgani uchun xulq so'zma-so'z o'zgarmaydi.
        """
        from apps.configurator.services import _owning_request, deal_has_multiple_models

        request_obj = _owning_request(obj)
        target = obj
        if deal_has_multiple_models(request_obj) and request_obj.configuration_id:
            target = request_obj.configuration
        return ConfigurationApprovalSerializer(target.approvals.all(), many=True).data

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


def resolve_base_product(validated_data):
    """Sales zayavkada katalogda yo'q modelni to'g'ridan so'rashi (21-§2).

    `new_base_product_name` (ixtiyoriy `new_base_product_sku`,
    `new_base_product_description`) yuborilsa va `base_product`
    tanlanmagan bo'lsa — mahsulot katalogga bazaviy MODEL sifatida
    yaratiladi: narxsiz, qoldiqsiz — buyurtmachi keyin to'ldiradi.
    `base_product` ham berilgan bo'lsa — tanlangan yutadi (§2.5).
    """
    from apps.inventory.models import Product
    from apps.inventory.services import create_product_from_order

    name = validated_data.pop('new_base_product_name', '')
    sku = validated_data.pop('new_base_product_sku', '')
    description = validated_data.pop('new_base_product_description', '')
    if validated_data.get('base_product') or not (name or sku):
        return validated_data
    validated_data['base_product'] = create_product_from_order(
        name=name, sku=sku, kind=Product.Kind.MACHINE, description=description,
    )
    return validated_data


class ConfigurationRequestLineSerializer(ModelSerializer):
    """12-§2 (B): zayavkadagi QO'SHIMCHA talab — model yoki tovar."""

    base_product = PrimaryKeyRelatedField(
        queryset=Product.objects.all(), required=False,
    )
    base_product_name = ReadOnlyField(source='base_product.name')
    configuration_number = ReadOnlyField(source='configuration.number')
    is_complete = ReadOnlyField()
    new_base_product_name = CharField(write_only=True, required=False, allow_blank=True)
    new_base_product_sku = CharField(write_only=True, required=False, allow_blank=True)
    new_base_product_description = CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = ConfigurationRequestLine
        fields = [
            'id', 'kind', 'base_product', 'base_product_name', 'quantity', 'text',
            'new_base_product_name', 'new_base_product_sku', 'new_base_product_description',
            'configuration', 'configuration_number', 'contract_item', 'is_complete',
        ]
        read_only_fields = ['configuration', 'contract_item']

    def validate(self, attrs):
        has_base_product = attrs.get('base_product') or (
            self.instance and self.instance.base_product_id
        )
        if not has_base_product and not (
            attrs.get('new_base_product_name') or attrs.get('new_base_product_sku')
        ):
            raise ValidationError({
                'base_product': 'Modelni tanlang yoki yangi model nomini kiriting.',
            })
        return attrs

    def create(self, validated_data):
        return super().create(resolve_base_product(validated_data))

    def update(self, instance, validated_data):
        validated_data.pop('new_base_product_name', None)
        validated_data.pop('new_base_product_sku', None)
        validated_data.pop('new_base_product_description', None)
        return super().update(instance, validated_data)


class ConfigurationRequestSerializer(ModelSerializer):
    """Sales'dan Engineerga boradigan matnli zayavka.

    12-§2 (B): "birinchi model" — `base_product`/`quantity` maydonlarida
    (orqaga mos); mijoz yana narsa so'rasa, `lines[]` orqali qo'shiladi —
    har biri `kind: "model"` (yig'iladigan) yoki `kind: "item"` (tayyor
    tovar, konfiguratorsiz to'g'ridan shartnoma qatoriga aylanadi).
    """

    events = ConfigurationRequestEventSerializer(many=True, read_only=True)
    lines = ConfigurationRequestLineSerializer(many=True, required=False)
    status_display = ReadOnlyField(source='get_status_display')
    client_name = ReadOnlyField(source='client.display_name')
    base_product_name = ReadOnlyField(source='base_product.name')
    configuration_number = ReadOnlyField(source='configuration.number')
    # Ikki xodim: kim so'radi (sales) va kim bajaryapti (engineer) — EGALIK §5.5
    taken_by_name = ReadOnlyField(source='taken_by.display_name')
    created_by_name = ReadOnlyField(source='created_by.display_name')
    deal = SerializerMethodField()
    new_base_product_name = CharField(write_only=True, required=False, allow_blank=True)
    new_base_product_sku = CharField(write_only=True, required=False, allow_blank=True)
    new_base_product_description = CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = ConfigurationRequest
        fields = [
            'id', 'number', 'client', 'client_name', 'text', 'quantity',
            'base_product', 'base_product_name',
            'new_base_product_name', 'new_base_product_sku', 'new_base_product_description',
            'warehouse', 'status',
            'status_display', 'configuration', 'configuration_number', 'deal',
            'taken_by', 'taken_by_name', 'created_by', 'created_by_name',
            'events', 'lines', 'created_at',
        ]
        read_only_fields = ['number', 'status', 'configuration', 'taken_by', 'created_by']

    def get_deal(self, obj):
        """14-§2: xuddi shu shakl — front bitta komponent yozadi."""
        from apps.configurator.services import build_deal

        return build_deal(obj)

    def create(self, validated_data):
        lines_data = validated_data.pop('lines', [])
        validated_data = resolve_base_product(validated_data)
        request_obj = super().create(validated_data)
        for line_data in lines_data:
            line_data = resolve_base_product(line_data)
            ConfigurationRequestLine.objects.create(request=request_obj, **line_data)
        return request_obj

    def update(self, instance, validated_data):
        # 21-§2.2: faqat yaratishda — tahrirlashda katalogga yozuv
        # qo'shish kutilmagan yon ta'sir bo'lardi
        validated_data.pop('new_base_product_name', None)
        validated_data.pop('new_base_product_sku', None)
        validated_data.pop('new_base_product_description', None)
        return super().update(instance, validated_data)

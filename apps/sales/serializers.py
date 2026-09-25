from rest_framework.serializers import (
    DateTimeField,
    ModelSerializer,
    PrimaryKeyRelatedField,
    ReadOnlyField,
    SerializerMethodField,
    ValidationError,
)

from apps.sales.models import (
    Contract,
    ContractItem,
    ContractApproval,
    ContractPayment,
    ContractDocument,
    ContractDocumentVersion,
    ContractTemplate,
    Lead,
)

PRICE_FIELDS = ['unit_price', 'subtotal', 'vat_percent', 'vat_amount', 'total_with_vat']


class ContractItemSerializer(ModelSerializer):
    """Qator: `unit_price` — QQS'siz narx, `vat_percent` default 12%."""

    product_name = ReadOnlyField(source='product.name')
    subtotal = ReadOnlyField()
    vat_amount = ReadOnlyField()
    total_with_vat = ReadOnlyField()
    # QOLGAN-ISHLAR #4: raqami ham kerak — aks holda front ikkita modelli
    # shartnomada qatorlarni ajratish uchun har konfiguratsiyaga alohida
    # so'rov yuborishga majbur bo'lardi
    configuration_number = ReadOnlyField(source='configuration.number')

    contract = PrimaryKeyRelatedField(
        queryset=Contract.objects.all(), required=False,
    )

    class Meta:
        model = ContractItem
        fields = [
            'id', 'contract', 'product', 'product_name', 'quantity', 'unit_price',
            'subtotal', 'vat_percent', 'vat_amount', 'total_with_vat',
            # 12-§2 (C): qator qaysi modeldan kelgani — bitta shartnomada
            # bir nechta model bo'lsa front shu bilan ajratadi
            'configuration', 'configuration_number',
        ]
        read_only_fields = ['configuration']

    def validate(self, attrs):
        # contract faqat alohida /contract-items/ orqali yaratishda majburiy;
        # shartnoma ichida nested kelganda ota-serializer o'zi bog'laydi
        if self.parent is None and self.instance is None and not attrs.get('contract'):
            raise ValidationError({'contract': 'Shartnoma ko\'rsatilishi shart.'})
        return attrs

    def to_representation(self, instance):
        """TZ: qator bo'yicha sotuv narxi faqat sales va adminga ko'rinadi."""
        data = super().to_representation(instance)
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if user and user.is_authenticated and not (user.is_admin or user.is_sales):
            for field in PRICE_FIELDS:
                data.pop(field, None)
        return data


class ContractApprovalSerializer(ModelSerializer):
    step_display = ReadOnlyField(source='get_step_display')
    decision_display = ReadOnlyField(source='get_decision_display')
    decided_by_name = ReadOnlyField(source='decided_by.display_name')

    class Meta:
        model = ContractApproval
        fields = [
            'id', 'contract', 'step', 'step_display', 'decision', 'decision_display',
            'comment', 'decided_by', 'decided_by_name', 'created_at',
        ]
        read_only_fields = fields


class ContractPaymentSerializer(ModelSerializer):
    """To'lov. `paid_at` ixtiyoriy — yuborilmasa hozirgi vaqt olinadi."""

    paid_at = DateTimeField(required=False)
    method_display = ReadOnlyField(source='get_method_display')
    contract_number = ReadOnlyField(source='contract.number')

    class Meta:
        model = ContractPayment
        fields = [
            'id', 'contract', 'contract_number', 'amount', 'method', 'method_display',
            'paid_at', 'is_prepayment', 'created_by', 'approved_by', 'created_at',
        ]
        read_only_fields = ['created_by', 'approved_by']


class ContractSerializer(ModelSerializer):
    items = ContractItemSerializer(many=True)
    approvals = ContractApprovalSerializer(many=True, read_only=True)
    payments = ContractPaymentSerializer(many=True, read_only=True)
    client_name = ReadOnlyField(source='client.display_name')
    # EGALIK §6: bosqich chizig'ining birinchi qadami — tuzgan sales ismi
    created_by_name = ReadOnlyField(source='created_by.display_name')
    status_display = ReadOnlyField(source='get_status_display')
    items_total = ReadOnlyField()
    vat_total = ReadOnlyField()
    items_total_with_vat = ReadOnlyField()
    prepayment_amount = ReadOnlyField()
    paid = ReadOnlyField()
    balance = ReadOnlyField()
    days_left = ReadOnlyField()
    color = ReadOnlyField()
    acts_approved = SerializerMethodField()

    class Meta:
        model = Contract
        fields = [
            'id', 'number', 'client', 'client_name', 'configuration', 'status',
            'status_display', 'created_by_name', 'currency', 'items_total', 'vat_total',
            'items_total_with_vat', 'total_amount', 'prepayment_percent',
            'prepayment_amount', 'term_days', 'delivery_days', 'signed_at', 'start_date',
            'delivered_at', 'delivered_by',
            'didox_number', 'didox_sent_at', 'didox_accepted_at', 'note',
            'items', 'approvals', 'payments', 'paid', 'balance', 'days_left', 'color',
            'acts_approved', 'created_by', 'created_at',
        ]
        # Didox maydonlari faqat bugalter bosqichlarida yoziladi (§11.2/B3)
        read_only_fields = [
            'number', 'created_by', 'status', 'start_date',
            'delivered_at', 'delivered_by',
            'didox_number', 'didox_sent_at', 'didox_accepted_at',
        ]

    def validate(self, attrs):
        # 8-to'plam §3: bitta konfiguratsiyaga BITTA shartnoma — qo'lda POST
        # bilan ikkinchisi ochilsa roadmap adashadi, bron ikki marta qo'yiladi
        # va is_paid noto'g'ri hisoblanadi. Bekor qilingani hisobga olinmaydi.
        configuration = attrs.get('configuration')
        if configuration is not None:
            existing = Contract.objects.filter(
                configuration=configuration,
            ).exclude(status=Contract.Status.CANCELLED)
            if self.instance is not None:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise ValidationError({
                    'configuration': (
                        'Bu konfiguratsiyaning shartnomasi allaqachon bor — '
                        'yangi oqimda u tasdiq paytida avtomatik ochiladi.'
                    ),
                })
        return attrs

    def get_acts_approved(self, obj):
        """20-§3.4: front yetkazish tugmasini qo'shimcha so'rovsiz o'chira oladi."""
        from apps.sales.services import _unapproved_acts

        return not _unapproved_acts(obj)

    def _sync_total(self, contract):
        """Summa berilmagan bo'lsa qatorlardan olinadi — QQS bilan (mijoz to'laydigan real summa)."""
        if not contract.total_amount:
            contract.total_amount = contract.items_total_with_vat
            contract.prepayment_percent = None
            contract.save()
        return contract

    def create(self, validated_data):
        items = validated_data.pop('items', [])
        contract = Contract.objects.create(**validated_data)
        for item in items:
            item.pop('contract', None)
            ContractItem.objects.create(contract=contract, **item)
        return self._sync_total(contract)

    def update(self, instance, validated_data):
        # B14: oldindan to'lov foizi faqat `draft` oynasida tuziladi —
        # bugalterga ketgandan keyin (admin ham) o'zgartira olmaydi
        if 'prepayment_percent' in validated_data:
            new_percent = validated_data['prepayment_percent']
            if (
                new_percent != instance.prepayment_percent
                and instance.status not in {
                    Contract.Status.DRAFT, Contract.Status.REJECTED,
                }
            ):
                raise ValidationError({
                    'prepayment_percent': (
                        "Oldindan to'lov foizi faqat qoralamada o'zgartiriladi — "
                        'shartnoma tasdiqqa ketgan.'
                    ),
                })
        items = validated_data.pop('items', None)
        manual_total = 'total_amount' in validated_data
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if items is not None:
            instance.items.all().delete()
            for item in items:
                item.pop('contract', None)
                ContractItem.objects.create(contract=instance, **item)
            # Qatorlar o'zgardi — summa ham yangilanadi (qo'lda berilmagan bo'lsa),
            # aks holda prepayment_amount va balance eski summadan hisoblanardi
            if not manual_total:
                instance.total_amount = instance.items_total_with_vat
                instance.save(update_fields=['total_amount'])
        return instance


class ContractDocumentVersionSerializer(ModelSerializer):
    """13-§1: tarix — kim, qachon saqlagani."""

    created_by_name = ReadOnlyField(source='created_by.display_name')

    class Meta:
        model = ContractDocumentVersion
        fields = ['id', 'body', 'created_by', 'created_by_name', 'created_at']


class ContractTemplateSerializer(ModelSerializer):
    """21-§3.1: sotuv shabloni — sales/admin yozadi, bugalter ham o'qiydi."""

    created_by_name = ReadOnlyField(source='created_by.display_name')

    class Meta:
        model = ContractTemplate
        fields = [
            'id', 'name', 'language', 'body', 'note', 'is_active', 'is_default',
            'has_specification', 'has_requisites',
            'created_by', 'created_by_name', 'created_at',
        ]
        read_only_fields = ['created_by']

    def validate_body(self, value):
        """21-§3.3: noma'lum kalit jimgina yo'qolmasin — 400 + ro'yxat."""
        from apps.sales.services import unknown_placeholder_keys

        unknown = unknown_placeholder_keys(value)
        if unknown:
            raise ValidationError(
                f"Noma'lum kalitlar: {', '.join(unknown)}",
            )
        return value


class ContractDocumentSerializer(ModelSerializer):
    """21-§3.2: shartnoma matni — shablon + avtomatik bloklar.

    `body` — KO'RSATISH uchun (o'rin egallovchilar to'ldirilgan),
    `body_raw` — bazadagi XOM matn (`{{ key }}` saqlanган holda) —
    front shu ustida tahrirlaydi.
    """

    body = SerializerMethodField()
    body_raw = ReadOnlyField(source='body')
    template_name = ReadOnlyField(source='template.name')
    versions_count = ReadOnlyField(source='versions.count')
    updated_by_name = ReadOnlyField(source='updated_by.display_name')
    can_edit = SerializerMethodField()

    class Meta:
        model = ContractDocument
        fields = [
            'id', 'contract', 'template', 'template_name', 'body', 'body_raw',
            'has_specification', 'has_requisites', 'versions_count',
            'updated_by', 'updated_by_name', 'updated_at', 'can_edit',
        ]
        read_only_fields = [
            'id', 'contract', 'template', 'template_name', 'body_raw',
            'has_specification', 'has_requisites', 'versions_count',
            'updated_by', 'updated_by_name', 'updated_at', 'can_edit',
        ]

    def get_body(self, obj):
        from apps.sales.services import render_contract_document

        return render_contract_document(obj.contract, obj.body)

    def get_can_edit(self, obj):
        """21-§3.6: sales (egasi)/bugalter/admin tahrirlaydi — ilgari
        faqat bugalter edi."""
        from apps.sales.services import CONTRACT_DOCUMENT_EDITABLE_STATUSES

        user = getattr(self.context.get('request'), 'user', None)
        if not (user and user.is_authenticated):
            return False
        is_owner_sales = user.is_sales and obj.contract.created_by_id == user.id
        return bool(
            (user.is_bugalter or user.is_admin or is_owner_sales)
            and obj.contract.status in CONTRACT_DOCUMENT_EDITABLE_STATUSES
        )


class LeadSerializer(ModelSerializer):
    client_name = ReadOnlyField(source='client.display_name')
    stage_display = ReadOnlyField(source='get_stage_display')

    class Meta:
        model = Lead
        fields = [
            'id', 'client', 'client_name', 'title', 'stage', 'stage_display',
            'expected_amount', 'next_contact_at', 'note', 'contract',
            'created_by', 'created_at',
        ]
        read_only_fields = ['created_by']

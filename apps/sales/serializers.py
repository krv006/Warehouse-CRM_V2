from rest_framework.serializers import (
    DateTimeField,
    ModelSerializer,
    PrimaryKeyRelatedField,
    ReadOnlyField,
    ValidationError,
)

from apps.sales.models import (
    Contract,
    ContractItem,
    ContractApproval,
    ContractPayment,
    Lead,
)

PRICE_FIELDS = ['unit_price', 'subtotal', 'vat_percent', 'vat_amount', 'total_with_vat']


class ContractItemSerializer(ModelSerializer):
    """Qator: `unit_price` — QQS'siz narx, `vat_percent` default 12%."""

    product_name = ReadOnlyField(source='product.name')
    subtotal = ReadOnlyField()
    vat_amount = ReadOnlyField()
    total_with_vat = ReadOnlyField()

    contract = PrimaryKeyRelatedField(
        queryset=Contract.objects.all(), required=False,
    )

    class Meta:
        model = ContractItem
        fields = [
            'id', 'contract', 'product', 'product_name', 'quantity', 'unit_price',
            'subtotal', 'vat_percent', 'vat_amount', 'total_with_vat',
        ]

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

    class Meta:
        model = Contract
        fields = [
            'id', 'number', 'client', 'client_name', 'configuration', 'status',
            'status_display', 'created_by_name', 'currency', 'items_total', 'vat_total',
            'items_total_with_vat', 'total_amount', 'prepayment_percent',
            'prepayment_amount', 'term_days', 'signed_at', 'start_date',
            'delivered_at', 'didox_number', 'didox_sent_at', 'didox_accepted_at', 'note',
            'items', 'approvals', 'payments', 'paid', 'balance', 'days_left', 'color',
            'created_by', 'created_at',
        ]
        # Didox maydonlari faqat bugalter bosqichlarida yoziladi (§11.2/B3)
        read_only_fields = [
            'number', 'created_by', 'status', 'start_date',
            'delivered_at', 'didox_number', 'didox_sent_at', 'didox_accepted_at',
        ]

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

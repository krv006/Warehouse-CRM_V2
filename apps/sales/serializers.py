from rest_framework.serializers import ModelSerializer, ReadOnlyField

from apps.sales.models import (
    Contract,
    ContractItem,
    ContractApproval,
    ContractPayment,
    Lead,
)

PRICE_FIELDS = ['unit_price', 'subtotal']


class ContractItemSerializer(ModelSerializer):
    product_name = ReadOnlyField(source='product.name')
    subtotal = ReadOnlyField()

    class Meta:
        model = ContractItem
        fields = ['id', 'product', 'product_name', 'quantity', 'unit_price', 'subtotal']

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
    decided_by_name = ReadOnlyField(source='decided_by.username')

    class Meta:
        model = ContractApproval
        fields = [
            'id', 'contract', 'step', 'step_display', 'decision', 'decision_display',
            'comment', 'decided_by', 'decided_by_name', 'created_at',
        ]
        read_only_fields = fields


class ContractPaymentSerializer(ModelSerializer):
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
    status_display = ReadOnlyField(source='get_status_display')
    prepayment_amount = ReadOnlyField()
    paid = ReadOnlyField()
    balance = ReadOnlyField()
    days_left = ReadOnlyField()
    color = ReadOnlyField()

    class Meta:
        model = Contract
        fields = [
            'id', 'number', 'client', 'client_name', 'configuration', 'status',
            'status_display', 'currency', 'total_amount', 'prepayment_percent',
            'prepayment_amount', 'term_days', 'signed_at', 'start_date', 'note',
            'items', 'approvals', 'payments', 'paid', 'balance', 'days_left', 'color',
            'created_by', 'created_at',
        ]
        read_only_fields = ['number', 'created_by', 'status', 'start_date']

    def _sync_total(self, contract):
        if not contract.total_amount:
            contract.total_amount = contract.items_total
            contract.prepayment_percent = None
            contract.save()
        return contract

    def create(self, validated_data):
        items = validated_data.pop('items', [])
        contract = Contract.objects.create(**validated_data)
        for item in items:
            ContractItem.objects.create(contract=contract, **item)
        return self._sync_total(contract)

    def update(self, instance, validated_data):
        items = validated_data.pop('items', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if items is not None:
            instance.items.all().delete()
            for item in items:
                ContractItem.objects.create(contract=instance, **item)
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

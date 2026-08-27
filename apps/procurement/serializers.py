from rest_framework.serializers import ModelSerializer, ReadOnlyField

from apps.procurement.models import (
    Replenishment,
    ReplenishmentApproval,
    ReplenishmentEvent,
    ReplenishmentItem,
)


class ReplenishmentItemSerializer(ModelSerializer):
    product_name = ReadOnlyField(source='product.name')
    product_sku = ReadOnlyField(source='product.sku')
    subtotal = ReadOnlyField()
    needs_price = ReadOnlyField()

    class Meta:
        model = ReplenishmentItem
        fields = [
            'id', 'replenishment', 'product', 'product_name', 'product_sku',
            'quantity', 'unit_price', 'subtotal', 'needs_price', 'supplier', 'note',
        ]


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
    items = ReplenishmentItemSerializer(many=True, read_only=True)
    approvals = ReplenishmentApprovalSerializer(many=True, read_only=True)
    events = ReplenishmentEventSerializer(many=True, read_only=True)
    status_display = ReadOnlyField(source='get_status_display')
    warehouse_name = ReadOnlyField(source='warehouse.name')
    items_total = ReadOnlyField()
    total_amount = ReadOnlyField()
    cash_available = ReadOnlyField()
    shortfall = ReadOnlyField()
    debt_days_left = ReadOnlyField()
    debt_color = ReadOnlyField()

    class Meta:
        model = Replenishment
        fields = [
            'id', 'number', 'warehouse', 'warehouse_name', 'supplier', 'status',
            'status_display', 'currency', 'logistics_cost', 'other_cost',
            'items_total', 'total_amount', 'cash_available', 'shortfall',
            'paid_amount', 'debt', 'debt_days_left', 'debt_color',
            'expected_at', 'delivered_at', 'note', 'items', 'approvals', 'events',
            'created_by', 'created_at',
        ]
        read_only_fields = [
            'number', 'status', 'created_by', 'paid_amount', 'debt', 'delivered_at',
        ]
